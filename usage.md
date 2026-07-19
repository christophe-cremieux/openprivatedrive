# Usage Guide

Welcome to **OpenPrivateDrive**! This guide explains how to use the main features after you have successfully installed the application.

## First Login

1. Open your browser and go to your instance (e.g. `http://your-server:5000` or `https://drive.yourdomain.com`)
2. Log in with the admin credentials:
   - **Username**: `admin`
   - **Password**: The one you set via `ADMIN_PASSWORD` environment variable

**Important**: Change the default admin password immediately after first login.

## Core Concepts

- **Users** — People who can log into the web interface
- **Folders** — Organize files with granular permissions
- **Files** — Stored with optional client-side encryption
- **Public Links** — One-time or limited-use upload/download links
- **Permissions** — Centralized engine controlling all access

---

## 📁 File & Folder Management

### Creating Folders
1. Click **New Folder** in the dashboard
2. Give it a name and optional description
3. Set default encryption policy (optional)

### Uploading Files
- **Click Upload** button
- For sensitive files: enable **Client-side Encryption**
  - Enter a strong password (used only for encryption/decryption)
  - The server never sees the plaintext content

### File Previews
- Images, PDFs, Office documents, text files, and media files support in-browser previews
- Click on any file to open the preview panel

### Search
- Global search bar at the top
- Searches filenames and (for supported formats) document content

---

## 🔗 Sharing & Collaboration

### Internal Sharing
1. Right-click a file or folder → **Share**
2. Select users or groups
3. Choose permissions (View / Edit / Admin)

### Public Download Links
1. Right-click file → **Create Download Link**
2. Configure:
   - Expiration date
   - Max downloads
   - Optional password
3. Copy the generated link

### Partner Upload Links (External File Collection)
1. Go to a target folder
2. Click **Create Upload Request Link**
3. Set options:
   - Optional password
   - Max number of files
   - Max total size
   - Expiration
4. Send the link to your partner/client
5. Files arrive directly in your chosen folder

---

## 🔒 Encryption Workflow

**Client-side AES-256-GCM Encryption** (Recommended for sensitive documents):

1. When uploading, choose **Encrypt with password**
2. Enter a strong password
3. The browser encrypts the file before sending it
4. On download (via web or Android):
   - Enter the same password to decrypt

> **Note**: The server never sees the encryption password or the plaintext file.

You can also set **folder-level policies** that require encryption for all uploads in specific workspaces.

---

## 👤 User & Admin Management

### Admin Panel
- Manage users (create, deactivate, delete)
- View storage usage
- Monitor system health
- Configure global settings

### Creating New Users
1. Go to **Admin** → **Users**
2. Click **Add User**
3. Set username, email, password, and role

### Permissions Best Practices
- Use least-privilege principle
- Create dedicated folders for departments/clients
- Regularly review shared links

---

## 📱 Android Access

OpenPrivateDrive provides a secure API designed for Android clients:

- Token-based authentication
- Secure decrypt flow for encrypted files
- File upload/download with progress tracking

*(Native Android app or integration coming soon — API documentation available in `/docs/api`)*

---

## 🔄 Common Tasks

| Task                        | How to Do It                              |
|----------------------------|-------------------------------------------|
| Rename file/folder         | Right-click → Rename                      |
| Move items                 | Drag & drop or Right-click → Move         |
| Delete (soft)              | Right-click → Delete                      |
| Empty Trash                | Admin or owner action                     |
| Regenerate thumbnails      | Admin tools                               |
| Backup data                | Copy `data/` folder                       |

---

## Keyboard Shortcuts

- `Ctrl/Cmd + K` — Global search
- `Ctrl/Cmd + N` — New folder
- `Ctrl/Cmd + U` — Upload files
- `F2` — Rename selected item

---

## Troubleshooting

- **File not uploading?** Check storage permissions and available disk space.
- **Encryption password forgotten?** Unfortunately, the file cannot be recovered (zero-knowledge design).
- **Performance issues?** Consider increasing server resources or enabling caching.
- **Public link not working?** Verify the link hasn't expired and the target folder still exists.

For more help, check:
- [Installation Guide](../installation.md)
- [Security Policy](../SECURITY.md)
- Open an issue on [GitHub](https://github.com/christophe-cremieux/openprivatedrive/issues)

---

**Enjoy owning your private cloud!** 🔒

*Made with ❤️ for privacy-conscious users.*
