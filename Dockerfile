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

# GCP credentials (if needed) are provided at runtime via GOOGLE_APPLICATION_CREDENTIALS
# or uploaded through /upload_credentials — never fetched or baked into the image.

# Command to run the app
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--reload"]

# Specify tag name to be created on github
LABEL version="1.0.1"
