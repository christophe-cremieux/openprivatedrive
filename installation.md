```markdown
# Installation Guide

This guide covers all supported ways to install and run **OpenPrivateDrive**.

## Prerequisites

- **Docker** (recommended) or Python 3.12+
- 2 GB RAM minimum (4 GB+ recommended for production)
- Domain name + SSL (recommended for production)

---

## 🚀 Docker Compose (Recommended)

### 1. Clone the Repository

```bash
git clone https://github.com/christophe-cremieux/openprivatedrive.git
cd openprivatedrive
```

### 2. Set Environment Variables

```bash
# Generate a strong secret key
export SECRET_KEY=$(openssl rand -hex 32)

# Set admin password
export ADMIN_PASSWORD=YourStrongPassword123!
```

### 3. Start the Application

```bash
docker compose up -d --build
```

The app will be available at `http://your-server-ip:5000`

**Default login:**
- **Username**: `admin`
- **Password**: the value of `ADMIN_PASSWORD`

### 4. Persistent Data

The following folders are mounted for persistence:

- `./data/instance` → Database + instance files
- `./data/storage` → All uploaded files
- `./data/logs` → Application logs

---

## 🛠 Bare Metal / VPS Installation

### 1. System Dependencies

```bash
sudo apt update
sudo apt install python3.12 python3.12-venv python3-pip nginx
```

### 2. Clone & Setup

```bash
git clone https://github.com/christophe-cremieux/openprivatedrive.git
cd openprivatedrive

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Configuration

```bash
cp .env.example .env
# Edit .env with your settings
```

**Example `.env` values:**

```env
FLASK_APP=app
FLASK_ENV=production
SECRET_KEY=your-super-secret-key-here
DATABASE_URL=sqlite:///instance/app.db
STORAGE_PATH=./storage
ADMIN_PASSWORD=YourStrongPassword123!
```

### 4. Database Setup

```bash
flask db upgrade
```

### 5. Run with Gunicorn (Production)

```bash
gunicorn -w 4 --bind 0.0.0.0:5000 'app:create_app()'
```

### 6. Nginx Reverse Proxy (Strongly Recommended)

Create `/etc/nginx/sites-available/openprivatedrive`:

```nginx
server {
    listen 80;
    server_name yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Then enable and restart:

```bash
sudo ln -s /etc/nginx/sites-available/openprivatedrive /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

---

## 🔄 Updating the Application

```bash
git pull
docker compose down
docker compose up -d --build
```

Or for bare metal:

```bash
git pull
flask db upgrade
```

---

## 📁 Directory Structure (Key Folders)

- `data/instance/` — Database
- `data/storage/` — Encrypted user files
- `data/logs/` — Logs

---

## 🔐 Security Recommendations for Production

1. **Always use HTTPS** (Let’s Encrypt)
2. Use a strong `SECRET_KEY`
3. Change the default admin password immediately
4. Enable firewall (`ufw allow 80`, `ufw allow 443`)
5. Regular backups of `data/` folder
6. Monitor logs in `data/logs/`

---

## 🧪 Testing the Installation

After starting the app:

1. Log in as admin
2. Create a test folder
3. Upload a file (should be encrypted on upload)
4. Try creating a public upload link

---

## Troubleshooting

- Check logs: `docker compose logs -f`
- Database issues: `flask db upgrade`
- Permission errors: Ensure `data/storage` is writable by the container/user

For more help, open an issue on GitHub.

---

**Need help with a specific deployment method?** Feel free to ask in the repository Discussions.
```

---

