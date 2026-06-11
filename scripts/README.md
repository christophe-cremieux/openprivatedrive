# Backup and Restore Scripts

This directory contains scripts for backing up and restoring the Private Drive database and storage.

## Scripts

### `backup.sh`

Creates a timestamped `tar.gz` archive of the SQLite database and the `storage/` directory.

-   **Database:** Uses `sqlite3 .backup` to ensure consistency.
-   **Storage:** Includes all files in the `storage/` directory, excluding `.tmp` files.
-   **Retention:** Automatically deletes backups older than 7 days (configurable in the script).
-   **Output:** Backups are saved to `/opt/private-drive/backups/`.

### `restore.sh`

Restores the database and storage from a specified backup archive.

-   **Usage:** `./restore.sh /path/to/backup_YYYYMMDD_HHMMSS.tar.gz`

## Automated Backups (Cron)

To schedule daily backups, add a cron job for the `private-drive` user:

1.  Open crontab:
    ```bash
    sudo -u private-drive crontab -e
    ```

2.  Add the following line to run the backup every day at 2:00 AM:
    ```cron
    0 2 * * * /opt/private-drive/scripts/backup.sh >> /opt/private-drive/backups/backup.log 2>&1
    ```

## Recommendations

-   **Off-site storage:** The `backup.sh` script saves backups locally. It is highly recommended to sync the `/opt/private-drive/backups/` directory to a remote location (e.g., using `rsync`, S3, or another cloud provider).
-   **Permissions:** Ensure the `backup.sh` and `restore.sh` scripts are executable:
    ```bash
    chmod +x scripts/backup.sh scripts/restore.sh
    ```
