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
ENV POETRY_VERSION=1.8.0
RUN pip install "poetry==$POETRY_VERSION"

# install chromium binary and matching chromedriver binary (+ gcc for installing e.g. psutil)
RUN apt-get update && apt-get install -y --no-install-recommends chromium-driver gcc python3-dev

# install dependences & create build version of package
COPY pyproject.toml poetry.lock ./
RUN poetry install --no-dev --no-root
COPY . .
RUN poetry build


# create lightweight 'final' stage with which to run discogs alert
FROM python-base as final

# copy everything we need & install `discogs_alert` from whl
COPY --from=builder /venv /venv
COPY --from=builder /dist .

# install chromium-driver, gcc, python3-dev (the latter two so that psutil can be installed)
# ideally we'd just copy the builds over (that are already installed above), but that doesn't seem to work ...
# COPY --from=builder /usr/bin/chromium /usr/bin/chromium
# COPY --from=builder /usr/bin/chromedriver /usr/bin/chromedriver
# COPY --from=builder /usr/bin/gcc /usr/bin/gcc
# COPY --from=builder /usr/bin/python3-config /usr/bin/python3-config
RUN apt-get update && apt-get install -y --no-install-recommends chromium-driver gcc python3-dev \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

RUN . /venv/bin/activate && pip install *.whl

# Create a directory in which to cache current conversion dicts
ENV DA_CURRENCY_CACHE_DIR=/.currency_cache
RUN mkdir $DA_CURRENCY_CACHE_DIR

# Set env variable so we can distinguish whether or not we're running in Docker
ENV IN_DA_DOCKER="true"

# run entrypoint
COPY ./docker/docker-entrypoint.sh ./
ENTRYPOINT ["./docker-entrypoint.sh"]
