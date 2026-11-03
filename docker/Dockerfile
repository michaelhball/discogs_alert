# Creating a python base with shared environment variables
FROM python:3.12-slim as python-base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONFAULTHANDLER=1


# create 'builder' stage to install the locked dependencies and `discogs_alert`
FROM python-base as builder

ENV PIP_DEFAULT_TIMEOUT=100 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_PROJECT_ENVIRONMENT=/venv \
    UV_PYTHON_PREFERENCE=only-system

ENV UV_VERSION=0.13.7
RUN pip install "uv==$UV_VERSION"

# No browser or webdriver needed: `curl_cffi` handles the marketplace scrape directly.
WORKDIR /src
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY discogs_alert ./discogs_alert
RUN uv sync --locked --no-dev --no-editable


# create lightweight 'final' stage with which to run discogs alert
FROM python-base as final

COPY --from=builder /venv /venv

# Create a directory in which to cache currency conversion dicts
ENV DA_CURRENCY_CACHE_DIR=/.currency_cache
RUN mkdir $DA_CURRENCY_CACHE_DIR

# Set env variable so we can distinguish whether or not we're running in Docker
ENV IN_DA_DOCKER="true"

# run entrypoint
COPY ./docker/docker-entrypoint.sh ./
ENTRYPOINT ["./docker-entrypoint.sh"]
