FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app

# Run as a non-root user
RUN useradd --create-home appuser && chown -R appuser /app
USER appuser

EXPOSE 8080
# 2 workers fit comfortably in 512 MB. Everything is async, so more workers are rarely needed.
CMD ["gunicorn", "app.main:app", "-k", "uvicorn.workers.UvicornWorker", "-w", "2", "-b", "0.0.0.0:8080", "--timeout", "60", "--access-logfile", "-"]
