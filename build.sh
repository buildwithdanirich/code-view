#!/usr/bin/env bash
set -euo pipefail
python -m pip install -r requirements.txt
python manage.py collectstatic --noinput
# Migrations deliberately run as an explicit, reviewed release step.
