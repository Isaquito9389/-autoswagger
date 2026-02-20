import io
import os
from collections import defaultdict
from datetime import datetime
from functools import wraps

import pandas as pd
from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from flask_sqlalchemy import SQLAlchemy
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "school.db")

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-me")
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{DB_PATH}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="teacher")
    full_name = db.Column(db.String(150), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    subjects = db.relationship("Subject", backref="teacher", lazy=True)


class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    matricule = db.Column(db.String(30), unique=True, nullable=False)
    first_name = db.Column(db.String(120), nullable=False)
    last_name = db.Column(db.String(120), nullable=False)
    sex = db.Column(db.String(1), nullable=False)
    serie = db.Column(db.String(1), nullable=False)
    lv2_choice = db.Column(db.String(20), nullable=True)


class Subject(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    serie = db.Column(db.String(1), nullable=False)
    coefficient = db.Column(db.Float, nullable=False, default=1.0)
    teacher_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)


class GradeEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("student.id"), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey("subject.id"), nullable=False)
    semester = db.Column(db.Integer, nullable=False, default=1)
    interrogations = db.Column(db.String(100), nullable=True)
    devoir1 = db.Column(db.Float, nullable=True)
    devoir2 = db.Column(db.Float, nullable=True)
    updated_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    student = db.relationship("Student")
    subject = db.relationship("Subject")

    __table_args__ = (
        db.UniqueConstraint("student_id", "subject_id", "semester", name="uq_grade_line"),
    )


class SemesterValidation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    semester = db.Column(db.Integer, unique=True, nullable=False)
    validated_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    validated_at = db.Column(db.DateTime, default=datetime.utcnow)


def login_required(role=None):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if "user_id" not in session:
                return redirect(url_for("login"))
            if role and session.get("role") != role:
                flash("Accès interdit.", "danger")
                return redirect(url_for("dashboard"))
            return func(*args, **kwargs)

        return wrapper

    return decorator


def parse_interrogations(raw_value: str):
    if not raw_value:
        return [], None
    notes = []
    for part in str(raw_value).replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            notes.append(float(part))
        except ValueError:
            return None, f"Note d'interrogation invalide: '{part}'."
    return notes, None


def compute_subject_average(grade: GradeEntry):
    notes, parse_error = parse_interrogations(grade.interrogations)
    if parse_error:
        return None, parse_error
    if len(notes) < 2 or len(notes) > 4:
        return None, "Interrogations invalides (2 à 4 requises)."
    if grade.devoir1 is None or grade.devoir2 is None:
        return None, "Deux devoirs obligatoires."
    mi = sum(notes) / len(notes)
    moyenne = round((mi + grade.devoir1 + grade.devoir2) / 3, 2)
    weighted = round(moyenne * grade.subject.coefficient, 2)
    return {
        "mi": round(mi, 2),
        "moyenne_matiere": moyenne,
        "coefficient": grade.subject.coefficient,
        "ponderee": weighted,
    }, None


def compute_semester_results(semester: int):
    students = Student.query.order_by(Student.last_name, Student.first_name).all()
    all_grades = GradeEntry.query.filter_by(semester=semester).all()
    grades_by_student = defaultdict(list)
    for grade in all_grades:
        grades_by_student[grade.student_id].append(grade)

    rows = []
    for student in students:
        weighted_sum = 0
        coeff_sum = 0
        subjects_details = {}
        for grade in grades_by_student.get(student.id, []):
            computed, _ = compute_subject_average(grade)
            if not computed:
                continue
            weighted_sum += computed["ponderee"]
            coeff_sum += computed["coefficient"]
            subjects_details[grade.subject.name] = computed["moyenne_matiere"]

        moyenne_generale = round(weighted_sum / coeff_sum, 2) if coeff_sum else 0
        rows.append(
            {
                "matricule": student.matricule,
                "nom": student.last_name,
                "prenom": student.first_name,
                "sexe": student.sex,
                "serie": student.serie,
                "moyenne_generale": moyenne_generale,
                "details": subjects_details,
            }
        )

    rows = sorted(rows, key=lambda item: item["moyenne_generale"], reverse=True)
    rank = 0
    previous_score = None
    for idx, row in enumerate(rows, 1):
        if previous_score is None or row["moyenne_generale"] < previous_score:
            rank = idx
        row["rang"] = rank
        previous_score = row["moyenne_generale"]
    return rows


def bootstrap_data():
    if User.query.count() == 0:
        admin = User(
            username="pp",
            full_name="Professeur Principal",
            role="admin",
            password_hash=generate_password_hash("pp12345"),
        )
        db.session.add(admin)
        db.session.commit()


@app.route("/")
def home():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"].strip()
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            session["user_id"] = user.id
            session["role"] = user.role
            session["full_name"] = user.full_name
            return redirect(url_for("dashboard"))
        flash("Identifiants invalides.", "danger")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required()
def dashboard():
    if session.get("role") == "admin":
        teachers = User.query.filter_by(role="teacher").all()
        subjects = Subject.query.order_by(Subject.serie, Subject.name).all()
        students_count = Student.query.count()
        return render_template(
            "dashboard_admin.html",
            teachers=teachers,
            subjects=subjects,
            students_count=students_count,
        )

    teacher_subjects = Subject.query.filter_by(teacher_id=session["user_id"]).all()
    return render_template("dashboard_teacher.html", teacher_subjects=teacher_subjects)


@app.route("/admin/teacher/create", methods=["POST"])
@login_required(role="admin")
def create_teacher():
    user = User(
        username=request.form["username"].strip(),
        full_name=request.form["full_name"].strip(),
        role="teacher",
        password_hash=generate_password_hash(request.form["password"]),
    )
    db.session.add(user)
    db.session.commit()
    flash("Compte professeur créé.", "success")
    return redirect(url_for("dashboard"))


@app.route("/admin/subject/create", methods=["POST"])
@login_required(role="admin")
def create_subject():
    subject = Subject(
        name=request.form["name"].strip(),
        serie=request.form["serie"],
        coefficient=float(request.form["coefficient"]),
        teacher_id=int(request.form["teacher_id"]) if request.form.get("teacher_id") else None,
    )
    db.session.add(subject)
    db.session.commit()
    flash("Matière ajoutée.", "success")
    return redirect(url_for("dashboard"))


@app.route("/admin/students/import", methods=["POST"])
@login_required(role="admin")
def import_students():
    file = request.files.get("excel_file")
    if not file:
        flash("Fichier Excel manquant.", "danger")
        return redirect(url_for("dashboard"))

    df = pd.read_excel(file)
    expected = {"matricule", "nom", "prenom", "sexe", "serie", "lv2"}
    if not expected.issubset(set(c.lower() for c in df.columns)):
        flash("Colonnes Excel attendues: matricule, nom, prenom, sexe, serie, lv2", "danger")
        return redirect(url_for("dashboard"))

    lowered = {c.lower(): c for c in df.columns}
    imported = 0
    for _, row in df.iterrows():
        matricule = str(row[lowered["matricule"]]).strip()
        if not matricule or Student.query.filter_by(matricule=matricule).first():
            continue
        student = Student(
            matricule=matricule,
            last_name=str(row[lowered["nom"]]).strip(),
            first_name=str(row[lowered["prenom"]]).strip(),
            sex=str(row[lowered["sexe"]]).strip().upper()[:1],
            serie=str(row[lowered["serie"]]).strip().upper()[:1],
            lv2_choice=str(row[lowered["lv2"]]).strip().capitalize(),
        )
        db.session.add(student)
        imported += 1
    db.session.commit()
    flash(f"Import terminé: {imported} élèves ajoutés.", "success")
    return redirect(url_for("dashboard"))


@app.route("/teacher/grades/<int:subject_id>", methods=["GET", "POST"])
@login_required(role="teacher")
def enter_grades(subject_id):
    subject = Subject.query.get_or_404(subject_id)
    if subject.teacher_id != session["user_id"]:
        flash("Accès interdit à cette matière.", "danger")
        return redirect(url_for("dashboard"))

    students = Student.query.filter_by(serie=subject.serie).order_by(Student.last_name).all()

    if request.method == "POST":
        semester = int(request.form.get("semester", 1))
        if SemesterValidation.query.filter_by(semester=semester).first():
            flash(
                "Semestre validé: les notes ne peuvent plus être modifiées.",
                "warning",
            )
            return redirect(url_for("enter_grades", subject_id=subject.id, semester=semester))

        for student in students:
            inter = request.form.get(f"inter_{student.id}", "")
            d1_raw = request.form.get(f"d1_{student.id}", "")
            d2_raw = request.form.get(f"d2_{student.id}", "")

            grade = GradeEntry.query.filter_by(
                student_id=student.id, subject_id=subject.id, semester=semester
            ).first()
            if not grade:
                grade = GradeEntry(
                    student_id=student.id,
                    subject_id=subject.id,
                    semester=semester,
                    updated_by=session["user_id"],
                )
                db.session.add(grade)

            grade.interrogations = inter
            grade.devoir1 = float(d1_raw) if d1_raw else None
            grade.devoir2 = float(d2_raw) if d2_raw else None
            grade.updated_by = session["user_id"]

        db.session.commit()
        flash("Notes enregistrées.", "success")
        return redirect(url_for("enter_grades", subject_id=subject.id))

    semester = int(request.args.get("semester", 1))
    grade_map = {
        g.student_id: g
        for g in GradeEntry.query.filter_by(subject_id=subject.id, semester=semester).all()
    }
    return render_template(
        "enter_grades.html",
        subject=subject,
        students=students,
        grade_map=grade_map,
        semester=semester,
    )


@app.route("/admin/results/<int:semester>")
@login_required(role="admin")
def semester_results(semester):
    rows = compute_semester_results(semester)
    return render_template("semester_results.html", rows=rows, semester=semester)


@app.route("/admin/results/<int:semester>/validate", methods=["POST"])
@login_required(role="admin")
def validate_semester(semester):
    existing = SemesterValidation.query.filter_by(semester=semester).first()
    if existing:
        flash("Semestre déjà validé.", "warning")
    else:
        db.session.add(SemesterValidation(semester=semester, validated_by=session["user_id"]))
        db.session.commit()
        flash("Résultats validés.", "success")
    return redirect(url_for("semester_results", semester=semester))


@app.route("/export/cahier/<int:subject_id>")
@login_required(role="teacher")
def export_gradebook(subject_id):
    subject = Subject.query.get_or_404(subject_id)
    if subject.teacher_id != session["user_id"]:
        flash("Accès interdit.", "danger")
        return redirect(url_for("dashboard"))

    grades = GradeEntry.query.filter_by(subject_id=subject.id).all()
    data = []
    for g in grades:
        data.append(
            {
                "matricule": g.student.matricule,
                "nom": g.student.last_name,
                "prenom": g.student.first_name,
                "semestre": g.semester,
                "interrogations": g.interrogations,
                "devoir1": g.devoir1,
                "devoir2": g.devoir2,
            }
        )

    output = io.BytesIO()
    pd.DataFrame(data).to_excel(output, index=False)
    output.seek(0)
    return send_file(
        output,
        as_attachment=True,
        download_name=f"cahier_{subject.name}.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.route("/export/results/<int:semester>/excel")
@login_required(role="admin")
def export_results_excel(semester):
    rows = compute_semester_results(semester)
    output = io.BytesIO()
    pd.DataFrame(rows).drop(columns=["details"]).to_excel(output, index=False)
    output.seek(0)
    return send_file(
        output,
        as_attachment=True,
        download_name=f"resultats_semestre_{semester}.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.route("/export/results/<int:semester>/pdf")
@login_required(role="admin")
def export_results_pdf(semester):
    rows = compute_semester_results(semester)
    output = io.BytesIO()
    pdf = canvas.Canvas(output, pagesize=A4)
    width, height = A4
    y = height - 50
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(50, y, f"Résultats semestriels - Semestre {semester}")
    y -= 30
    pdf.setFont("Helvetica", 10)

    for row in rows:
        line = f"{row['rang']:>3}. {row['nom']} {row['prenom']} ({row['matricule']}) - MG: {row['moyenne_generale']}"
        pdf.drawString(50, y, line)
        y -= 16
        if y < 50:
            pdf.showPage()
            y = height - 50

    pdf.save()
    output.seek(0)
    return send_file(output, as_attachment=True, download_name=f"resultats_semestre_{semester}.pdf")


@app.route("/export/bulletin/<int:student_id>/<int:semester>/pdf")
@login_required(role="admin")
def export_bulletin_pdf(student_id, semester):
    student = Student.query.get_or_404(student_id)
    grades = GradeEntry.query.filter_by(student_id=student.id, semester=semester).all()

    output = io.BytesIO()
    pdf = canvas.Canvas(output, pagesize=A4)
    y = 800
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(50, y, f"Bulletin - {student.last_name} {student.first_name} ({student.matricule})")
    y -= 30

    total_weight = 0
    total_coeff = 0
    pdf.setFont("Helvetica", 10)
    for grade in grades:
        computed, error = compute_subject_average(grade)
        if error:
            continue
        total_weight += computed["ponderee"]
        total_coeff += computed["coefficient"]
        pdf.drawString(
            50,
            y,
            f"{grade.subject.name}: MI={computed['mi']} | M={computed['moyenne_matiere']} | Coef={computed['coefficient']}",
        )
        y -= 16

    moyenne = round(total_weight / total_coeff, 2) if total_coeff else 0
    y -= 10
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(50, y, f"Moyenne Générale: {moyenne}/20")

    pdf.save()
    output.seek(0)
    return send_file(output, as_attachment=True, download_name=f"bulletin_{student.matricule}.pdf")


@app.context_processor
def inject_validation_status():
    validations = {v.semester for v in SemesterValidation.query.all()}
    return {"validated_semesters": validations}


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        bootstrap_data()
    app.run(debug=True)
