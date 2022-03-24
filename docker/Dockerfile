# Creating a python base with shared environment variables
FROM python:3.10.0-slim as python-base
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONFAULTHANDLER=1

WORKDIR /discogs_alert


# create 'builder' stage to install dependencies and build `discogs_alert`
FROM python-base as builder

ENV PIP_DEFAULT_TIMEOUT=100 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

# Install Poetry & create venv (respects $POETRY_VERSION & $POETRY_HOME)
ENV POETRY_VERSION=1.1.13
RUN pip install "poetry==$POETRY_VERSION"
RUN python -m venv /venv

# install dependences & create build version of package
COPY pyproject.toml poetry.lock ./
RUN . /venv/bin/activate && poetry install --no-dev --no-root
COPY . .
RUN . /venv/bin/activate && poetry build


# create lightweight 'final' stage with which to run discogs alert
FROM python-base as final

# install from whl
COPY --from=builder /venv /venv
COPY --from=builder /discogs_alert/dist .
RUN . /venv/bin/activate && pip install *.whl

# run entrypoint
COPY ./docker/docker-entrypoint.sh ./
CMD ["./docker-entrypoint.sh"]
