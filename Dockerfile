FROM python:3.13-slim

# Set workdir early
WORKDIR /app

# Copy just what's needed
COPY requirements.txt autoswagger.py web_app.py ./

# Install Python packages and SpaCy model, then cleanup
RUN pip install --no-cache-dir --upgrade pip 
RUN pip install --no-cache-dir -r requirements.txt && \
    python -m spacy download en_core_web_lg && \
    rm -rf ~/.cache/pip

# Expose port for web interface
EXPOSE 5000

# Set entrypoint for web app
ENTRYPOINT ["python", "web_app.py"]
