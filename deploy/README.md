# Production Deployment

This directory contains configuration files for deploying Private Drive in a production environment using Gunicorn and Nginx.

## Prerequisites

- Python 3.12+
- Nginx
- Systemd
- Domain name and SSL certificate (e.g., from Let'sEncrypt)

## Setup Instructions

1.  **Prepare the system:**
    ```bash
    sudo useradd -m -s /bin/bash private-drive
    sudo mkdir -p /opt/private-drive
    sudo chown private-drive:private-drive /opt/private-drive
    ```

2.  **Clone the repository and setup environment:**
    ```bash
    cd /opt/private-drive
    sudo -u private-drive git clone <repo_url> .
    sudo -u private-drive python3 -m venv venv
    sudo -u private-drive venv/bin/pip install -r requirements.txt
    ```

3.  **Configure environment variables:**
    Create a `.env` file in `/opt/private-drive/` with production settings:
    ```
    SECRET_KEY=generate-a-secure-random-key
    DATABASE_URL=sqlite:////opt/private-drive/instance/app.db
    STORAGE_PATH=/opt/private-drive/storage
    MAX_CONTENT_LENGTH_MB=500
    SESSION_COOKIE_SECURE=True
    # ... other settings
    ```

4.  **Install Systemd service:**
    ```bash
    sudo cp deploy/private-drive.service /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable private-drive
    sudo systemctl start private-drive
    ```

5.  **Install Nginx configuration:**
    - Edit `deploy/nginx-private-drive.conf` to set your domain and SSL paths.
    - Copy to Nginx sites-available:
    ```bash
    sudo cp deploy/nginx-private-drive.conf /etc/nginx/sites-available/private-drive
    sudo ln -s /etc/nginx/sites-available/private-drive /etc/nginx/sites-enabled/
    sudo nginx -t
    sudo systemctl restart nginx
    ```

## Security Considerations

- Ensure `SECRET_KEY` is kept secret and unique for production.
- Keep the `instance/` and `storage/` directories outside of any web-accessible path.
- Nginx is configured to block direct access to the `/storage` path.
- Static files are served directly by Nginx for better performance.
