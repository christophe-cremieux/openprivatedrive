"""
Description: Defines the Flask application factory and initializes configuration, logging, proxy middleware, and extensions.
Author: Your Christophe CREMIEUX <sammy.crem@gmail.com>
Copyright: (c) 2026 Christophe CREMIEUX

License: GNU Affero General Public License v3.0
         This program is free software: you can redistribute it and/or modify
         it under the terms of the GNU Affero General Public License as
         published by the Free Software Foundation.

         See the LICENSE file at the root of this project for details.
"""

import os
import click
from flask import Flask, request
from werkzeug.middleware.proxy_fix import ProxyFix
from .config import Config
from .extensions import db, migrate, login_manager, csrf, limiter, executor

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Configure logging to file if path is provided
    if app.config.get("LOG_FILE_PATH"):
        import logging
        from logging.handlers import RotatingFileHandler
        file_handler = RotatingFileHandler(
            app.config["LOG_FILE_PATH"], maxBytes=1024 * 1024 * 10, backupCount=10
        )
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
        ))
        file_handler.setLevel(logging.INFO)
        app.logger.addHandler(file_handler)
        app.logger.info('Application startup with file logging')

    # Production config validation
    is_prod = os.environ.get("FLASK_ENV") == "production" or (not app.debug and not app.testing)
    if is_prod:
        errors = []
        if app.config.get("SECRET_KEY") == "you-will-never-guess":
            errors.append("SECRET_KEY is using the default value.")
        if app.config.get("ADMIN_PASSWORD") == "admin123":
            errors.append("ADMIN_PASSWORD is using the default value.")
        if not app.config.get("SESSION_COOKIE_SECURE"):
            errors.append("SESSION_COOKIE_SECURE is False in production.")
        if app.config.get("RATELIMIT_STORAGE_URI") == "memory://" and not os.environ.get("SIMPLE_DOCKER_DEPLOYMENT") == "True":
            errors.append("RATELIMIT_STORAGE_URI is using 'memory://' in production.")

        if errors:
            msg = "PRODUCTION SECURITY FAILURE: " + " ".join(errors)
            app.logger.error(msg)
            if os.environ.get("FLASK_ENV") == "production":
                raise RuntimeError(msg)

    # ProxyFix for Nginx reverse proxy
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

    # SQLITE doesn't support pool_size/max_overflow/pool_timeout if using StaticPool (default for memory)
    # but for file-based sqlite, it uses QueuePool.
    # To be safe and flexible, we configure it during init_app if it's not an in-memory SQLite DB.
    db_uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
    is_mem_sqlite = db_uri == "sqlite://" or db_uri == "sqlite:///:memory:"

    if not is_mem_sqlite:
        app.config.setdefault('SQLALCHEMY_ENGINE_OPTIONS', {})
        app.config['SQLALCHEMY_ENGINE_OPTIONS'].update({
            "pool_size": int(app.config.get("SQLALCHEMY_POOL_SIZE", 20)),
            "max_overflow": int(app.config.get("SQLALCHEMY_MAX_OVERFLOW", 40)),
            "pool_timeout": int(app.config.get("SQLALCHEMY_POOL_TIMEOUT", 60)),
        })

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)
    app.config['EXECUTOR_PROPAGATE_EXCEPTIONS'] = True
    app.config['EXECUTOR_TYPE'] = 'thread'
    executor.init_app(app)

    # Configure limiter with storage URI from config
    if app.config.get("RATELIMIT_STORAGE_URI"):
        limiter._storage_uri = app.config["RATELIMIT_STORAGE_URI"]
    limiter.init_app(app)

    # Login manager configuration
    login_manager.login_view = "auth.login"
    login_manager.login_message_category = "info"

    # Register blueprints
    from .auth.routes_web import auth_web as auth_web_bp
    app.register_blueprint(auth_web_bp)

    from .drive.routes_web import drive_web as drive_web_bp
    app.register_blueprint(drive_web_bp)

    from .admin.routes_web import admin_web as admin_web_bp
    app.register_blueprint(admin_web_bp)

    from .sharing.routes_web import sharing_web as sharing_web_bp
    app.register_blueprint(sharing_web_bp)

    from .public_links.routes_web import public_links_web as public_links_web_bp
    app.register_blueprint(public_links_web_bp)

    from .api.routes import api_v1 as api_v1_bp
    app.register_blueprint(api_v1_bp)
    csrf.exempt(api_v1_bp)

    from .api.user_picker import user_picker_api as user_picker_api_bp
    app.register_blueprint(user_picker_api_bp)
    csrf.exempt(user_picker_api_bp)

    @login_manager.user_loader
    def load_user(id):
        from .models.user import User
        return db.session.get(User, int(id))

    @app.context_processor
    def inject_storage_info():
        from flask_login import current_user
        if current_user.is_authenticated:
            from .services.file_service import file_service
            return {'storage_info': file_service.get_user_storage_stats(current_user)}
        return {'storage_info': None}

    @app.route("/health")
    def health_check():
        office_preview_enabled = app.config.get("OFFICE_PREVIEW_ENABLED", False)
        libreoffice_bin = app.config.get("LIBREOFFICE_BIN", "/usr/bin/libreoffice")
        libreoffice_found = os.path.exists(libreoffice_bin)

        return {
            "status": "healthy",
            "office_preview": {
                "enabled": office_preview_enabled,
                "binary_found": libreoffice_found,
                "available": office_preview_enabled and libreoffice_found
            }
        }, 200

    @app.route("/ready")
    def ready_check():
        from sqlalchemy import text
        from .extensions import db
        from .models.system_stat import SystemStat

        status = {
            "status": "ready",
            "database": "down",
            "storage": "unwritable"
        }
        ready = True

        # 1. Check DB
        try:
            db.session.execute(text("SELECT 1")).scalar()
            status["database"] = "up"
        except Exception:
            ready = False

        # 2. Check Storage
        storage_path = app.config.get('STORAGE_PATH')
        if storage_path and os.path.exists(storage_path) and os.access(storage_path, os.W_OK):
            status["storage"] = "writable"
        else:
            ready = False

        return status, 200 if ready else 503

    @app.after_request
    def add_security_headers(response):
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains; preload'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; "
            "script-src 'self' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "font-src 'self' https://cdn.jsdelivr.net; "
            "img-src 'self' data:; "
            "frame-ancestors 'self'; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "connect-src 'self' https://cdn.jsdelivr.net;"
        )
        return response

    @app.cli.command("cleanup")
    def cleanup_command():
        """Runs the storage cleanup background job."""
        from .services.background_jobs import cleanup_storage_job
        print("Starting storage cleanup...")
        cleanup_storage_job(app)
        print("Cleanup completed.")

    @app.cli.command("bootstrap-admin")
    @click.option(
        "--reset-password",
        is_flag=True,
        help="Reset the admin password from ADMIN_PASSWORD.",
    )
    def bootstrap_admin_command(reset_password):
        """Creates the initial admin user when it does not already exist."""
        from .services.bootstrap_service import bootstrap_service

        if reset_password:
            user = bootstrap_service.reset_admin_password(app)
            print(f"Admin password reset: {user.username}")
            return

        user = bootstrap_service.ensure_admin_user(app)
        if user:
            print(f"Admin user ready: {user.username}")

    return app
