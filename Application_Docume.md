✦ Private-Drive: Full Application Documentation

  This document provides a comprehensive overview of the Private-Drive application's functionality. It is designed to serve as a guide for step-by-step usage
  and presentation videos.

  ---

  1. Overview
  Private-Drive is a secure, self-hosted document library designed for private file storage and management. It features a robust permission engine,
  multi-device synchronization, and advanced security hardening.

   - Primary Goal: Secure, private file storage with centralized access control.
   - Interface: Web-based (SSR with Jinja2) and a dedicated REST API for Android integration.
   - Architecture: Flask-based with a service-oriented architecture, ensuring shared logic between Web and API.

  ---

  2. Core File & Folder Management (The "Drive")
  The heart of the application is the "My Drive" interface, where users manage their digital assets.

  File Operations
   - Uploads:
     - Direct Upload: Fast uploads for smaller files via the web interface.
     - Session-Based Chunked Uploads: Reliable, resumable uploads for large files (primarily used by the API).
   - Navigation:
     - Folder Structure: Nested folders with path breadcrumbs.
     - Search: Instant search across files and folders by name.
     - Starred: Quick access to "favorited" items.
     - Recent: View recently uploaded or modified files.
   - Manipulation:
     - Rename & Move: Organize files without breaking links.
     - Copy: Easily duplicate files or entire folder structures.
     - Soft Delete: Items are moved to the Trash rather than being immediately deleted.
   - Bulk Actions: Select multiple items for bulk delete, move, or download (as a ZIP).

  Advanced File Features
   - ZIP Extraction: Extract ZIP files directly on the server to avoid downloading large archives.
   - Previews & Thumbnails:
     - Image Thumbnails: Automatic generation of small and large thumbnails.
     - Video Thumbnails: Frame capture for video files (via ffmpeg).
     - Office Previews: Automatic conversion of Word, Excel, and PowerPoint files to PDF for browser viewing (via LibreOffice).
     - PDF Thumbnails: First-page preview for PDF documents.

  ---

  3. Collaboration & Sharing
  Private-Drive provides granular control over how files are shared, both internally and externally.

  Internal Sharing
   - Permission Levels:
     - Viewer: Read-only access and download.
     - Editor: Can upload, rename, and edit content.
     - Manager: Full control including deletion and further sharing.
   - Inheritance: Permissions set on a folder can be inherited by all sub-folders and files within it.
   - Expiration: Set an optional expiration date for any share.

  Public Interaction
   - Public Links: Generate unique, secure UUID links to share files or folders with non-users.
   - Public Upload Links:
     - Create a "Drop-box" folder where external users can upload files.
     - Security: One-time keys, file count limits, and total size quotas ensure the feature isn't abused.

  ---

  4. Security & Privacy
  Security is built into every layer of the application.

  Access Control
   - Centralized Permission Engine: Every single request to view, download, or modify a file is gated by the permission engine.
   - UUIDs: Public identifiers use UUIDs to prevent "ID enumeration" attacks.
   - Private Storage: Files are stored outside the web root and are never served directly by physical path.

  Antivirus & Threat Protection
   - ClamAV Integration: Automatic scanning of uploaded files for viruses.
   - Quarantine: Infected files are automatically quarantined and hidden from non-admin users.
   - Strict Mode: Optional setting to block downloads for files whose virus scans are still pending.

  Encryption
   - At-Rest Security: Support for AES-256-GCM encryption using Scrypt key derivation for sensitive file storage and downloads.

  ---

  5. Administration Console
  A dedicated dashboard for system administrators to monitor and manage the instance.

   - User Management:
     - Create, deactivate, or reactivate users.
     - Reset passwords and revoke active API tokens/sessions.
     - Manage individual user storage quotas.
   - System Monitoring:
     - Activity Logs: A full audit trail of system events (logins, deletions, permission changes).
     - Storage Stats: Real-time overview of storage usage.
     - Diagnostics: Connectivity tests for ClamAV and system health checks.
   - Upload Policies:
     - Define global allowed/blocked file extensions (e.g., blocking .exe or .sh for security).

  ---

  6. API & Sync Engine
  The application is designed for multi-device workflows.

   - Android Integration: A dedicated API v1 handles authentication, file browsing, and uploads.
   - Sync Engine: Tracks changes across the filesystem, allowing clients to efficiently synchronize only what has changed.
   - Device Management: Users can see which devices are connected to their account and revoke access instantly.

  ---

  7. Data Integrity & Maintenance
  Background jobs ensure the system remains clean and efficient.

   - Trash Retention: Items in the trash for more than 30 days are automatically purged.
   - Cleanup Jobs: Daily jobs clean up expired upload sessions, orphaned files (files on disk but not in DB), and old activity logs (older than 90 days).
   - Soft Deletion: Mandatory soft-deletion for all user-managed entities to prevent accidental data loss.

  ---

  Summary for Video Presentation
   1. Introduction: High-level overview of Private-Drive.
   2. User Experience: Tour of "My Drive," Starred, and Search.
   3. File Management: Uploading, moving, and the powerful ZIP extraction.
   4. Collaboration: How to share internally and create public upload links.
   5. Behind the Scenes: Previews, Antivirus, and Background processing.
   6. Administration: Managing users, quotas, and security policies.
   7. Mobile/Sync: Overview of the Android API and device management.

