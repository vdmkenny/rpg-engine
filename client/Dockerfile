# Python base image
FROM python:3.14-bookworm

# Set the working directory
WORKDIR /app

# Install build essentials, SDL2 for pygame, and poetry
RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential libsdl2-dev libsdl2-image-dev libsdl2-mixer-dev libsdl2-ttf-dev && \
    pip install poetry

# Copy dependency definition files from the project root
COPY pyproject.toml poetry.lock* /app/

# Configure poetry and install only client-related dependencies
RUN poetry config virtualenvs.create false && \
    poetry cache clear . --all && \
    poetry install --no-interaction --no-ansi --no-root --with client

# Copy all source code into the container
COPY . /app/
COPY . /app/

# Set the command to run the application
CMD ["poetry", "run", "python", "client/src/main.py"]


