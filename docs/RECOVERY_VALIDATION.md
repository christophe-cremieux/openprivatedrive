# Disaster Recovery Validation Guide

This document outlines the steps to verify the integrity of the OpenPrivateDrive recovery process.

## 1. Automated Validation
The `backup.sh` and `restore.sh` scripts now include automated integrity checks:
- **Archive Integrity:** Both scripts use `tar -tzf` to ensure the gzip archive is not corrupted.
- **Database Consistency:** `restore.sh` runs `sqlite3 PRAGMA integrity_check` on the extracted database before applying it.

## 2. Manual Verification Procedure
To perform a complete manual recovery test:

1. **Perform a Backup:**
   ```bash
   ./scripts/backup.sh
   ```
2. **Verify Backup Content:**
   List the contents of the generated tarball to ensure `app.db` and the `storage/` directory are present.
   ```bash
   tar -tvf /opt/private-drive/backups/backup_YYYYMMDD_HHMMSS.tar.gz
   ```
3. **Simulate a Restore on a Sandbox Environment:**
   **Warning: Do not perform this on a production system without a secondary backup.**
   ```bash
   ./scripts/restore.sh /path/to/backup.tar.gz
   ```
4. **Post-Restore Checks:**
   - Log in with existing user credentials.
   - Verify that files uploaded prior to backup are accessible.
   - Verify that encrypted files can still be decrypted with their original passwords.
   - Run the Admin Diagnostics page (`/admin/diagnostics`) to ensure all background services (LibreOffice, FFmpeg) are correctly mapped.

## 3. Retention Policy
The system maintains a 7-day rolling window of backups. Ensure that the backup storage location has sufficient disk space for 7 times the size of your `storage/` directory + `app.db`.
