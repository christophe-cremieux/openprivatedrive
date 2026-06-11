#!/bin/bash

# Simple script to backup host-mounted data directories safely for SQLite
set -e

BACKUP_DIR="./backups"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="${BACKUP_DIR}/docker_backup_${TIMESTAMP}.tar.gz"
SQLITE_DB="./data/instance/app.db"
TEMP_DB_BACKUP="${BACKUP_DIR}/app_${TIMESTAMP}.db"

mkdir -p "${BACKUP_DIR}"

echo "Starting backup of persistent data..."

# Perform safe SQLite backup if the database exists
if [ -f "${SQLITE_DB}" ]; then
    echo "SQLite database found. Performing online backup..."
    sqlite3 "${SQLITE_DB}" ".backup '${TEMP_DB_BACKUP}'"
else
    echo "Warning: SQLite database not found at ${SQLITE_DB}"
fi

# Archive the database backup and the storage directory
echo "Creating archive..."
tar -czf "${BACKUP_FILE}" "${TEMP_DB_BACKUP}" ./data/storage ./data/logs

# Cleanup the temporary DB backup file
[ -f "${TEMP_DB_BACKUP}" ] && rm "${TEMP_DB_BACKUP}"

echo "Backup completed: ${BACKUP_FILE}"
