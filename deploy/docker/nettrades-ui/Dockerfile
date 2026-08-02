FROM python:3.12-slim

WORKDIR /app

# Copy the merged requirements file from src/core
COPY src/core/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the UI application
COPY deploy/docker/nettrades-ui/app/ ./app/
COPY deploy/docker/nettrades-ui/static/ ./static/
COPY deploy/docker/nettrades-ui/templates/ ./templates/

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]