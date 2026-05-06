FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

COPY pyproject.toml README.md /app/
COPY arbiter /app/arbiter

RUN pip install --upgrade pip && pip install .

EXPOSE 8501

CMD ["streamlit", "run", "arbiter/app/streamlit_app.py", "--server.port", "8501", "--server.address", "0.0.0.0"]
