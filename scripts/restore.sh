#!/bin/bash
# Restore script for Private Drive

if [ -z "$1" ]; then
    echo "Usage: $0 <path_to_backup_tar_gz>"
    exit 1
fi

BACKUP_FILE="$1"
APP_DIR="/opt/private-drive"
DB_PATH="$APP_DIR/instance/app.db"
STORAGE_DIR="$APP_DIR/storage"

if [ ! -f "$BACKUP_FILE" ]; then
    echo "Error: Backup file not found: $BACKUP_FILE"
    exit 1
fi

echo "Validating backup $BACKUP_FILE..."

# Verify archive integrity
if ! tar -tzf "$BACKUP_FILE" > /dev/null; then
    echo "Error: Backup file is corrupted or not a valid gzip archive."
    exit 1
fi
echo "Integrity check passed."

echo "Restoring from $BACKUP_FILE..."

# Create a temporary directory for extraction
TEMP_RESTORE="/tmp/private-drive-restore-$(date +%s)"
mkdir -p "$TEMP_RESTORE"

# Extract archive
tar -xzf "$BACKUP_FILE" -C "$TEMP_RESTORE"

# Validate database consistency if it exists in backup
if [ -f "$TEMP_RESTORE/app.db" ]; then
    echo "Verifying database consistency..."
    if ! sqlite3 "$TEMP_RESTORE/app.db" "PRAGMA integrity_check;" | grep -q "ok"; then
        echo "Error: Database in backup is corrupted!"
        rm -rf "$TEMP_RESTORE"
        exit 1
    fi
    echo "Database check passed."
fi

# Stop the service if it's running (optional, requires sudo)
# sudo systemctl stop private-drive

# Restore database
if [ -f "$TEMP_RESTORE/app.db" ]; then
    mkdir -p "$(dirname "$DB_PATH")"
    cp "$TEMP_RESTORE/app.db" "$DB_PATH"
    echo "Database restored."
fi

# Restore storage
if [ -d "$TEMP_RESTORE/storage" ]; then
    mkdir -p "$STORAGE_DIR"
    rsync -av "$TEMP_RESTORE/storage/" "$STORAGE_DIR/"
    echo "Storage restored."
fi

# Clean up
rm -rf "$TEMP_RESTORE"

# Restart service
# sudo systemctl start private-drive

echo "Restore completed. Please check file permissions if necessary."
