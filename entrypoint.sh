#!/bin/sh

set -e

# Apply database migrations
python manage.py migrate --noinput


# Start the web server
echo "Starting Django server..."
exec python manage.py runserver 0.0.0.0:8000
