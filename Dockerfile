FROM mcr.microsoft.com/playwright/python:v1.47.0-jammy

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chmod +x start.sh

EXPOSE 8000

# For Render's free-plan deployment (render.yaml), start.sh runs uvicorn +
# celery worker + celery beat together in this one container. For local
# docker-compose, this CMD is overridden per-service (see docker-compose.yml).
CMD ["./start.sh"]
