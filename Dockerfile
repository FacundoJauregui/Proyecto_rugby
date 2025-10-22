# Python base image
FROM python:3.11-slim

# Prevents Python from writing .pyc files and enables unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Set work dir
WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
 && rm -rf /var/lib/apt/lists/*

# Install Python deps first (leverage caching)
COPY requirements.txt ./
RUN python -m pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . .

# Collect static files
ENV DJANGO_SETTINGS_MODULE=rugby_project.settings
RUN python manage.py collectstatic --noinput || true

# Expose port
EXPOSE 8080

# Gunicorn config: Cloud Run expects to listen on $PORT
ENV PORT=8080
CMD ["sh", "-c", "gunicorn rugby_project.wsgi:application --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120"]
