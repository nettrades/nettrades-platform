FROM python:3.12-slim

WORKDIR /app

# Copy merged requirements
COPY src/core/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy API application (no static files)
COPY deploy/docker/nettrades-ui/app/ ./app/
COPY deploy/docker/nettrades-ui/templates/ ./templates/

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]