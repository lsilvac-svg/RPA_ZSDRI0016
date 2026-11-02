#!/bin/sh
# Prepara la base y los estáticos, y levanta la web en el puerto 8030.
set -e

python manage.py migrate --noinput
python manage.py collectstatic --noinput --verbosity 0

exec waitress-serve --listen=0.0.0.0:8030 --threads=8 config.wsgi:application
