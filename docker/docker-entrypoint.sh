#!/bin/sh

set -e
. /venv/bin/activate
echo Your container args are "$@"
python -m discogs_alert "$@"
