#!/bin/sh
set -eu

PORT_VALUE="${PORT:-8080}"

exec gunicorn -w 1 -b "0.0.0.0:${PORT_VALUE}" app.web_app:app
