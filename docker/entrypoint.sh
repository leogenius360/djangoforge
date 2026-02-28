#!/bin/bash
set -e

# Wait for database
echo "Waiting for database..."
python /app/scripts/wait_for_db.py

# Run migrations
echo "Running migrations..."
python manage.py migrate --noinput

# Collect static files
echo "Collecting static files..."
python manage.py collectstatic --noinput

echo "Starting application..."
exec "$@"
