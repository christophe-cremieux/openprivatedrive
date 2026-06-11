#!/bin/bash

# Exit on any error
set -e

# Set environment variables for Flask
export FLASK_APP=run.py
export FLASK_DEBUG=1

# Check if virtual environment exists and activate it
if [ -d "venv" ]; then
    echo "Activating virtual environment..."
    source venv/bin/activate
fi

# Run the Flask application
echo "Starting Private Drive Flask application on port 5100..."
python3 run.py
