#!/bin/bash

# Exit on error
set -e

echo "Running database migrations..."
mkdir -p /app/instance /app/storage /app/logs
chown -R appuser:appuser /app/instance /app/storage /app/logs

# In production, we only run upgrade. init/migrate should be done during development.
gosu appuser flask db upgrade
gosu appuser flask bootstrap-admin

# Start the application
echo "Starting Private Drive with Gunicorn..."
# Redirect logs to stdout for Docker by default, unless LOG_FILE_PATH is set
if [ -n "$LOG_FILE_PATH" ]; then
    exec gosu appuser gunicorn --bind 0.0.0.0:5100 --workers 4 --timeout 120 --access-logfile - --error-logfile "$LOG_FILE_PATH" "run:app"
else
    exec gosu appuser gunicorn --bind 0.0.0.0:5100 --workers 4 --timeout 120 --access-logfile - --error-logfile - "run:app"
fi
