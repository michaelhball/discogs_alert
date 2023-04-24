# Creating a python base with shared environment variables
FROM python:3.10.0-slim as python-base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONFAULTHANDLER=1


# create 'builder' stage to install dependencies and build `discogs_alert`
FROM python-base as builder

ENV PIP_DEFAULT_TIMEOUT=100 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

# create & activate venv
RUN python -m venv /venv
RUN . /venv/bin/activate

# install Poetry (respects $POETRY_VERSION & $POETRY_HOME)
ENV POETRY_VERSION=1.3.2
RUN pip install "poetry==$POETRY_VERSION"

# install dependences & create build version of package
COPY pyproject.toml poetry.lock ./
RUN poetry install --no-dev --no-root
COPY . .
RUN poetry build

# install chromium binary and matching chromedriver binary
RUN apt-get update && apt-get install -y --no-install-recommends chromium-driver


# create lightweight 'final' stage with which to run discogs alert
FROM python-base as final

# copy everything we need & install `discogs_alert` from whl
COPY --from=builder /venv /venv
COPY --from=builder /dist .
COPY --from=builder /usr/bin/chromium /usr/bin/chromium
COPY --from=builder /usr/bin/chromedriver /usr/bin/chromedriver
RUN . /venv/bin/activate && pip install *.whl

# run entrypoint
COPY ./docker/docker-entrypoint.sh ./
CMD ["./docker-entrypoint.sh"]
