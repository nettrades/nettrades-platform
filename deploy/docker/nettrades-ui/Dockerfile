# FILE: deploy/docker/nettrades-ui/Dockerfile

# Use the official Docker CLI image to get the statically linked binary
FROM docker:24-cli AS docker-cli

FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy the docker binary from the official image
COPY --from=docker-cli /usr/local/bin/docker /usr/local/bin/docker

WORKDIR /app

# Copy requirements and install
COPY src/core/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the UI code
COPY deploy/docker/nettrades-ui/app/ ./app/
COPY deploy/docker/nettrades-ui/static/ ./static/
COPY deploy/docker/nettrades-ui/templates/ ./templates/

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]