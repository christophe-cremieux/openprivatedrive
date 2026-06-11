# OpenPrivate-Drive Flask Application by Christophe CREMIEUX

## Project Goal
A private self-hosted document library application designed for secure file storage and management. It provides both a web interface and an API for Android integration, ensuring that all file operations are governed by a centralized permission engine.

## Tech Stack
- **Backend:** Python 3.12+, Flask (App Factory Pattern)
- **Database:** SQLAlchemy with SQLite (MVP) / PostgreSQL (Future-ready)
- **Migrations:** Flask-Migrate / Alembic
- **Authentication:** Flask-Login (Web), Token-based Auth (Android API)
- **Frontend:** Jinja2 templates, Bootstrap 5 or Tailwind CSS
- **Deployment:** Gunicorn + Nginx
- **Storage:** Private local filesystem storage (outside public webroot)

## Architecture Rules
- **No React:** Uses server-side rendering with Jinja2.
- **Service Layer:** Shared business logic between web and API routes.
- **Security:**
    - `/storage` is never exposed publicly.
    - Files are never served by physical path.
    - Centralized permission engine for every file/folder operation.
- **Data Integrity:**
    - Use UUIDs for public-facing identifiers.
    - Soft delete for files and folders.

## Folder Structure
```text
/
├── app/
│   ├── api/          # API routes (Android)
│   ├── web/          # Web routes (Jinja2)
│   ├── auth/         # Auth specific logic
│   ├── drive/        # Drive specific logic
│   ├── sharing/      # Sharing specific logic
│   ├── public_links/ # Public links specific logic
│   ├── sync/         # Sync specific logic
│   ├── admin/        # Admin specific logic
│   ├── services/     # Shared business logic
│   ├── models/       # SQLAlchemy models
│   ├── templates/    # Jinja2 templates
│   ├── static/       # CSS/JS assets
│   ├── permissions/  # Permission engine
│   └── __init__.py   # App factory
├── tests/            # Test suite
├── migrations/       # Database migrations
├── instance/         # Database and instance-specific files
├── storage/          # Private file storage
├── .env.example      # Environment variables template
├── requirements.txt  # Python dependencies
├── README.md
└── config.py         # Configuration settings
```

## Production Deployment & Security

### 1. Security Hardening
The application includes several security features by default:
- **Centralized Permissions:** All file/folder operations are gated by a role-based permission engine.
- **Security Headers:** HSTS (with preload), CSP (strict), X-Frame-Options, and X-Content-Type-Options are enabled.
- **Token-based API:** Android integration uses secure Bearer tokens with sliding expiration.
- **CSRF Protection:** Enabled globally for all state-changing web requests.
- **Public Upload Links:** Secure folder-specific upload links with one-time keys, configurable file count limits, and size quotas.

### 2. SQLite Production Caveats
When running with SQLite in production:
- **WAL Mode:** Enabled by default to allow concurrent reads/writes.
- **Busy Timeout:** Set to 5000ms to handle temporary locks.
- **Datetime Handling:** All datetimes are stored as naive UTC. The application standardizes comparisons to ensure consistency across different platforms.

### 3. Production Stack
- **Web Server:** Nginx (configured as reverse proxy).
- **WSGI Server:** Gunicorn with `ProxyFix`.
- **Background Tasks:** For large-scale use, consider moving expensive operations like recursive soft-deletes to a task queue (e.g., Celery).

## Local Development Setup

### 1. Create Virtual Environment
```bash
python3 -m venv venv
source venv/bin/activate
```

### 2. Install Requirements
```bash
pip install -r requirements.txt
```

### 3. Setting .env
Copy `.env.example` to `.env` and fill in the values:
```bash
cp .env.example .env
```
Example `.env`:
```text
FLASK_APP=app
FLASK_ENV=development
SECRET_KEY=your-secret-key
DATABASE_URL=sqlite:///instance/app.db
STORAGE_PATH=./storage
```

### 4. Running Migrations
```bash
flask db upgrade
```

### 5. Running Locally
```bash
flask run
```

### 6. Running with Gunicorn
```bash
gunicorn -w 4 'app:create_app()'
```

## Docker Deployment

The application is containerized and ready for deployment using Docker and Docker Compose. All persistent data is stored on the host machine to ensure the container remains stateless.

### 1. Persistent Data Locations
By default, the `docker-compose.yml` maps the following host directories to the container:
- `./data/instance`: Database and instance-specific files.
- `./data/storage`: Private file storage for user uploads.
- `./data/logs`: Application logs.

### 2. Running with Docker Compose

Build and start the application:
```bash
export SECRET_KEY=your-secure-key
export ADMIN_PASSWORD=your-admin-pass
docker-compose up -d --build
```

### 3. Environment Variables
You can customize the deployment by setting variables in your `.env` file or directly in `docker-compose.yml`:
- `SECRET_KEY`: Important for session security.
- `ADMIN_PASSWORD`: Default is `admin123`.
- `SESSION_COOKIE_SECURE`: Set to `True` if using HTTPS.

### 4. Backups
To backup your persistent data:
```bash
./scripts/docker_backup.sh
```
To restore from a backup:
```bash
./scripts/docker_restore.sh <backup_file.tar.gz>
```

## Database Migration Commands
- Create a new migration: `flask db migrate -m "description"`
- Apply migrations: `flask db upgrade`
- Rollback: `flask db downgrade`

## Test Commands
```bash
pytest
```

## Security Rules
- All file access must go through a controller that checks permissions.
- Direct access to the storage directory via web server configuration is strictly prohibited.
- UUIDs must be used in all URLs instead of integer IDs to prevent enumeration.
- Soft delete is mandatory for all user-managed entities.
