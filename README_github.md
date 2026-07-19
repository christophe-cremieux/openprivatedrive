# OpenPrivateDrive

**Self-hosted private cloud drive** — A secure, encrypted Google Drive / Dropbox alternative you fully control.

![License](https://img.shields.io/github/license/christophe-cremieux/openprivatedrive)
![Python](https://img.shields.io/badge/Python-3.12+-blue)
![Docker](https://img.shields.io/badge/Docker-Ready-blue)

**Install it on your VPS, dedicated server, or homelab** and get full ownership of your documents with strong client-side encryption.

[🌐 Visit Website](https://openprivatedrive.com) • [📖 Documentation](https://openprivatedrive.com/docs) • [🚀 Live Demo](https://demo.openprivatedrive.com) • [⭐ Star the Project](https://github.com/christophe-cremieux/openprivatedrive)

## ✨ Key Features

- **Client-side AES-256-GCM encryption** for uploads
- **Secure public upload links** (one-time or limited-use for partners/clients)
- **Full permission system** (users, folders, sharing)
- **File previews** (images, PDFs, documents)
- **Android app support** via secure API
- **Self-hosted & offline-first** — no data leaves your server
- **Docker-ready** with easy one-command deployment

## Screenshots

![Dashboard Preview](https://openprivatedrive.com/screenshots/dashboard.png)
![Upload & Sharing](https://openprivatedrive.com/screenshots/sharing.png)
![Mobile View](https://openprivatedrive.com/screenshots/mobile.png)

*(Add actual screenshots here — highly recommended)*

## 🚀 Quick Start (Docker - Recommended)

```bash
git clone https://github.com/christophe-cremieux/openprivatedrive.git
cd openprivatedrive

# Set secure secrets
export SECRET_KEY=$(openssl rand -hex 32)
export ADMIN_PASSWORD=your_strong_password

docker compose up -d --build

Open http://your-server-ip:5000 in your browser and log in with:

Username: admin
Password: the one you set above

See the full installation guide for more options.


## 🛠 Tech Stack

Backend: Python 3.12+ + Flask (App Factory pattern)
Database: SQLAlchemy + SQLite (default) / PostgreSQL ready
Frontend: Jinja2 + Bootstrap 5
Deployment: Docker, Gunicorn + Nginx
Storage: Encrypted local filesystem (never exposed publicly)


##🔒 Architecture Highlights

Strong centralized permission engine
No direct filesystem exposure (/storage is protected)
UUID-based URLs (no sequential ID enumeration)
Soft deletes everywhere
Token-based authentication for Android API
Security headers enabled by default

##  📦 Deployment Options

Docker Compose (Recommended for most users)
Bare metal / VPS with Gunicorn + Nginx

## 💻 Local Development
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env with your settings

flask db upgrade
flask run

## 🔐 Security
All file operations are protected by a centralized permission layer.
Files are never served directly from disk.
We welcome security reviews and responsible disclosure.
See SECURITY.md for details.


## Contributing
Contributions are welcome! Please read CONTRIBUTING.md first.

Fork the project
Create a feature branch
Open a Pull Request

## License
This project is licensed under the GNU GPL-3.0 license — see the LICENSE file for details.

Made with ❤️ for privacy-conscious individuals, businesses, and self-hosters.



