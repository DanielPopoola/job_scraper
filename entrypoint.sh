#!/bin/sh

set -e

# Apply database migrations
python manage.py migrate --noinput

# Start the scraping process in the background
echo "Starting initial job scraping in the background..."
python manage.py orchestrate \
    --mode "custom" \
    --sites "linkedin" \
    --max-jobs 100 \
    --max-concurrency 3 \
    --delay-between-searches 20 \
    --delay-between-sites 60 \
    --search-terms \
        "Project Manager" \
        "Python Developer" \
        "Data Engineer" \
        "Data Scientist" \
        "Cloud Engineer" \
        "Game Developer" \
        "Backend Developer" \
        "Frontend Developer" \
        "Full Stack Developer" \
        "AI Engineer" \
        "UI/UX Designer" \
        "Mobile Developer" \
        "Machine Learning Engineer" \
        "Product Manager" &

# Start the web server
echo "Starting Django server..."
exec python manage.py runserver 0.0.0.0:8000
