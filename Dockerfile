FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/media /app/staticfiles

RUN python manage.py collectstatic --noinput || true

CMD sh -c "\
  python manage.py migrate --noinput && \
  python manage.py setup_initial_data 2>/dev/null || true && \
  python manage.py collectstatic --noinput && \
  gunicorn --bind 0.0.0.0:${PORT:-8000} --workers 2 --access-logfile - --error-logfile - backend.wsgi:application \
"
