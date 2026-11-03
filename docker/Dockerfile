# Two stages: `builder` installs the locked dependencies with uv, `final` holds
# only the Python runtime and that environment, and runs as an unprivileged user.
FROM python:3.13-alpine@sha256:7984cf56ceaddebe4fefeb75d64000b9f45d8b77b11a09b24524da6cdc3af0c8 AS python-base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONFAULTHANDLER=1


FROM python-base AS builder

ENV UV_PROJECT_ENVIRONMENT=/venv \
    UV_PYTHON_PREFERENCE=only-system \
    UV_VERSION=0.13.7
RUN pip install --no-cache-dir "uv==$UV_VERSION"

# `curl_cffi` ships musl wheels, so no browser, webdriver or compiler is needed.
WORKDIR /src
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY discogs_alert ./discogs_alert
RUN uv sync --locked --no-dev --no-editable


FROM python-base AS final

# pip and setuptools are only needed to build; dropping them removes their
# vendored copies of urllib3 and msgpack from the image.
RUN pip uninstall -y pip setuptools 2>/dev/null; \
    rm -rf /usr/local/lib/python3.13/site-packages/pip* /usr/local/lib/python3.13/site-packages/setuptools* \
    && adduser -D -h /home/app app

COPY --from=builder /venv /venv

# `state.db`, the heartbeat and the currency cache live under /home/app/.discogs_alert.
# Mount a volume there to keep alerts deduplicated across container restarts.
ENV HOME=/home/app \
    DA_CURRENCY_CACHE_DIR=/home/app/.discogs_alert/currency_cache \
    IN_DA_DOCKER="true"
USER app
WORKDIR /home/app

# `docker ps` shows the container as unhealthy when the last iteration failed,
# read no marketplace page, or is older than twice the interval. `--status`
# exits 2 before the first iteration, so the start period covers that.
HEALTHCHECK --interval=5m --timeout=30s --start-period=3m \
    CMD /venv/bin/discogs_alert --status >/dev/null 2>&1 || exit 1

ENTRYPOINT ["/venv/bin/discogs_alert"]
