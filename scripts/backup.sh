#!/bin/bash
# Backup script for Private Drive

# Configuration
BACKUP_DIR="/opt/private-drive/backups"
APP_DIR="/opt/private-drive"
DB_PATH="$APP_DIR/instance/app.db"
STORAGE_DIR="$APP_DIR/storage"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_NAME="backup_$TIMESTAMP.tar.gz"
RETENTION_DAYS=7

# Create backup directory if it doesn't exist
mkdir -p "$BACKUP_DIR"

echo "Starting backup: $BACKUP_NAME"

# Create a temporary directory for the backup
TEMP_BACKUP="/tmp/private-drive-backup-$TIMESTAMP"
mkdir -p "$TEMP_BACKUP"

# Copy database (using sqlite3 .backup for consistency if possible, or just cp)
if [ -f "$DB_PATH" ]; then
    sqlite3 "$DB_PATH" ".backup '$TEMP_BACKUP/app.db'"
else
    echo "Warning: Database not found at $DB_PATH"
fi

# Copy storage directory, excluding temporary files
if [ -d "$STORAGE_DIR" ]; then
    mkdir -p "$TEMP_BACKUP/storage"
    rsync -av --exclude='*.tmp' --exclude='temp/' "$STORAGE_DIR/" "$TEMP_BACKUP/storage/"
else
    echo "Warning: Storage directory not found at $STORAGE_DIR"
fi

# Create compressed archive
tar -czf "$BACKUP_DIR/$BACKUP_NAME" -C "$TEMP_BACKUP" .

# Verify archive integrity
echo "Verifying backup integrity..."
if tar -tzf "$BACKUP_DIR/$BACKUP_NAME" > /dev/null; then
    echo "Integrity check passed."
else
    echo "Error: Backup integrity check failed!"
    rm -f "$BACKUP_DIR/$BACKUP_NAME"
    rm -rf "$TEMP_BACKUP"
    exit 1
fi

# Clean up temporary directory
rm -rf "$TEMP_BACKUP"

echo "Backup completed: $BACKUP_DIR/$BACKUP_NAME"

# Retention: Delete backups older than RETENTION_DAYS
find "$BACKUP_DIR" -name "backup_*.tar.gz" -mtime +$RETENTION_DAYS -delete
echo "Retention policy applied (deleted backups older than $RETENTION_DAYS days)"
