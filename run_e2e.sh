#!/bin/bash

# Exit on any error
set -e

# Set PYTHONPATH to include the current directory so 'app' module can be found
export PYTHONPATH=$PYTHONPATH:$(pwd)

# Check if virtual environment exists and activate it
if [ -d "venv" ]; then
    echo "Activating virtual environment..."
    source venv/bin/activate
fi

# Run the E2E tests using pytest
# We run the entire e2e directory to include all relevant tests
echo "Running End-to-End tests..."
pytest tests/e2e/ --headed -s "$@"
