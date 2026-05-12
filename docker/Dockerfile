# Creating a python base with shared environment variables
FROM python:3.12-slim as python-base

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
ENV POETRY_VERSION=1.8.0
RUN pip install "poetry==$POETRY_VERSION"

# install dependencies & create build version of package. No browser or
# webdriver needed — `curl_cffi` handles the marketplace scrape directly.
# `poetry.lock` is .gitignore'd, so we generate one inside the build.
COPY pyproject.toml ./
RUN poetry lock --no-update 2>/dev/null || poetry lock
RUN poetry install --no-root --without dev
COPY . .
RUN poetry build


# create lightweight 'final' stage with which to run discogs alert
FROM python-base as final

# copy everything we need & install `discogs_alert` from whl
COPY --from=builder /venv /venv
COPY --from=builder /dist .

RUN . /venv/bin/activate && pip install *.whl

# Create a directory in which to cache currency conversion dicts
ENV DA_CURRENCY_CACHE_DIR=/.currency_cache
RUN mkdir $DA_CURRENCY_CACHE_DIR

# Set env variable so we can distinguish whether or not we're running in Docker
ENV IN_DA_DOCKER="true"

# run entrypoint
COPY ./docker/docker-entrypoint.sh ./
ENTRYPOINT ["./docker-entrypoint.sh"]
