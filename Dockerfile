FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_PORT=8501

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py vocab_dictionary.py vocab_domain.py vocab_nlp.py vocab_lexical_engine.py vocab_synthesis.py vocab_migrations.py vocab_workflow.py vocab_persistence.py vocab_translation.py ./
COPY db/migrations ./db/migrations

RUN useradd --create-home --uid 10001 vocab
USER vocab

EXPOSE 8501
CMD ["streamlit", "run", "app.py"]
