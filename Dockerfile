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

# Optional private billing module, vendored as a git submodule (vendor/babblebeaver-billing, pinned to a tag).
# Installed only when the submodule was checked out, so clones and builds without access to the private
# repo are unchanged.
RUN if [ -f vendor/babblebeaver-billing/pyproject.toml ]; then \
      pip install --no-cache-dir ./vendor/babblebeaver-billing; \
    else \
      echo "hosted billing module not present; skipping"; \
    fi

# GCP credentials (if needed) are provided at runtime via GOOGLE_APPLICATION_CREDENTIALS
# or uploaded through /upload_credentials — never fetched or baked into the image.

# Command to run the app
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--reload"]

# Specify tag name to be created on github
LABEL version="1.0.1"
