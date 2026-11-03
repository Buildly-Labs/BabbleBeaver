# Use an official lightweight Python image.
# https://hub.docker.com/_/python
FROM python:3.11

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set work directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . .

# Optional private billing module. Installed only when a read-only GitHub token is supplied as a build
# variable, so builds without it are unchanged. Pinned to a tag for reproducible builds.
ARG BB_BILLING_GH_TOKEN=""
RUN if [ -n "$BB_BILLING_GH_TOKEN" ]; then \
      pip install --no-cache-dir "git+https://x-access-token:${BB_BILLING_GH_TOKEN}@github.com/Buildly-Labs/babblebeaver-billing.git@v0.1.2"; \
    fi

# GCP credentials (if needed) are provided at runtime via GOOGLE_APPLICATION_CREDENTIALS
# or uploaded through /upload_credentials — never fetched or baked into the image.

# Command to run the app
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--reload"]

# Specify tag name to be created on github
LABEL version="1.0.1"
