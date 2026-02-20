# Application scolaire (Flask)

Application web de gestion des notes pour classes de secondaire avec rôles **PP/Admin** et **Professeur**.

## Fonctionnalités couvertes

- Authentification par session (PP + professeurs).
- Import Excel des élèves (colonnes: `matricule, nom, prenom, sexe, serie, lv2`).
- Gestion matières / coefficients / assignation professeurs.
- Saisie des notes par matière et par semestre (2–4 interrogations, 2 devoirs).
- Calcul automatique:
  - MI = moyenne interrogations
  - Moyenne matière = (MI + devoir1 + devoir2) / 3
  - Moyenne générale pondérée = somme(matière*coef) / somme(coef)
  - Classement avec ex-aequo.
- Export Excel:
  - Cahier de notes professeur
  - Résultats semestriels
- Export PDF:
  - Résultats semestriels
  - Bulletin individuel
- Validation semestrielle par le PP.

## Démarrage local

```bash
cd school_app
python -m venv .venv
source .venv/bin/activate
pip install -r ../requirements.txt
python app.py
```

Puis ouvrir `http://127.0.0.1:5000`.

Compte initial:
- utilisateur: `pp`
- mot de passe: `pp12345`

## Déploiement PythonAnywhere (SQLite)

1. Créer une web app Flask (manuel).
2. Cloner le repo dans votre home PythonAnywhere.
3. Créer un virtualenv et installer les dépendances.
4. Configurer le fichier WSGI avec:

```python
import sys
path = '/home/<username>/-autoswagger/school_app'
if path not in sys.path:
    sys.path.append(path)

from app import app as application
```

5. Redémarrer l’app web.

## Structure

- `app.py`: routes, modèles SQLAlchemy, calculs, exports.
- `templates/`: UI Bootstrap.
- `static/css/style.css`: styles (coloration filles au classement).
- `sample_eleves.csv`: exemple de format d’import.

## Remarques

- Le PP supervise mais ne modifie pas les notes (routes d’édition limitées aux professeurs assignés).
- Les règles LV1/LV2 sont préparées via le champ `lv2` des élèves; l’intégration automatique plus fine peut être branchée dès réception de votre fichier réel et de vos grilles officielles.
- Les modèles PDF sont provisoires (ReportLab) et pourront être alignés exactement à vos maquettes officielles quand vous les partagerez.
