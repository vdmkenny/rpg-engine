# Python base image
FROM python:3.14-slim

# Set the working directory
WORKDIR /app

# Install build essentials, rust, and poetry
RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential rustc cargo curl && \
    pip install poetry

# Copy dependency definition files from the project root
COPY pyproject.toml poetry.lock* /app/

# Configure poetry and install server and dev dependencies
RUN poetry config virtualenvs.create false && \
    poetry cache clear . --all && \
    poetry install --no-interaction --no-ansi --no-root --with server,dev

# Copy all source code into the container
COPY . /app/

# Set the command to run the application
CMD ["poetry", "run", "uvicorn", "server.src.main:app", "--host", "0.0.0.0", "--port", "8000"]
