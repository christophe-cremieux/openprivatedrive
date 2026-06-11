#!/bin/bash

# Enhanced script to restore data from a backup with safety checks
set -e

if [ -z "$1" ]; then
    echo "Usage: $0 <backup_file.tar.gz>"
    exit 1
fi

BACKUP_FILE=$1

if [ ! -f "${BACKUP_FILE}" ]; then
    echo "Error: Backup file not found: ${BACKUP_FILE}"
    exit 1
fi

# Create a temporary directory for validation
TEMP_RESTORE_DIR=$(mktemp -d)
trap 'rm -rf "$TEMP_RESTORE_DIR"' EXIT

echo "Extracting backup to temporary directory for validation..."
tar -xzf "${BACKUP_FILE}" -C "$TEMP_RESTORE_DIR"

# Identify the database file in the backup
DB_FILE=$(find "$TEMP_RESTORE_DIR" -name "*.db" | head -n 1)

if [ -n "$DB_FILE" ]; then
    echo "Validating SQLite database integrity..."
    INTEGRITY=$(sqlite3 "$DB_FILE" "PRAGMA integrity_check;")
    if [ "$INTEGRITY" != "ok" ]; then
        echo "Error: Database integrity check failed: $INTEGRITY"
        exit 1
    fi
    echo "Database integrity check passed."
fi

echo "Stopping Private Drive container..."
docker-compose stop app || true

echo "Replacing data..."
# Restore storage
if [ -d "$TEMP_RESTORE_DIR/data/storage" ]; then
    rm -rf ./data/storage
    mkdir -p ./data
    cp -r "$TEMP_RESTORE_DIR/data/storage" ./data/
fi

# Restore logs
if [ -d "$TEMP_RESTORE_DIR/data/logs" ]; then
    rm -rf ./data/logs
    mkdir -p ./data
    cp -r "$TEMP_RESTORE_DIR/data/logs" ./data/
fi

# Restore database
if [ -n "$DB_FILE" ]; then
    mkdir -p ./data/instance
    cp "$DB_FILE" ./data/instance/app.db
fi

echo "Starting Private Drive container..."
docker-compose start app

echo "Restore completed successfully."
