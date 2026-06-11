"""
Description: Handles authentication web routes for login, logout, registration, and session management.
Author: Your Christophe CREMIEUX <sammy.crem@gmail.com>
Copyright: (c) 2026 Christophe CREMIEUX

License: GNU Affero General Public License v3.0
         This program is free software: you can redistribute it and/or modify
         it under the terms of the GNU Affero General Public License as
         published by the Free Software Foundation.

         See the LICENSE file at the root of this project for details.
"""

from datetime import datetime, timezone
from app.extensions import db
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, current_user, login_required
from urllib.parse import urlsplit
from app.models.user import User
from app.auth.forms import LoginForm, RegistrationForm
from app.auth.services import auth_service
from app.services.password_service import password_service
from app.api.services import api_service
from app.services.activity_log_service import activity_log_service
from app.extensions import limiter
from app.config import Config

auth_web = Blueprint("auth", __name__)

@auth_web.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("drive.dashboard"))

    form = RegistrationForm()
    if form.validate_on_submit():
        auth_service.create_user(
            username=form.username.data,
            email=form.email.data,
            password=form.password.data
        )
        flash("Congratulations, you are now a registered user!", "success")
        return redirect(url_for("auth.login"))
    return render_template("auth/register.html", title="Register", form=form)

@auth_web.route("/login", methods=["GET", "POST"])
@limiter.limit(Config.LOGIN_RATE_LIMIT)
def login():
    if current_user.is_authenticated:
        return redirect(url_for("drive.dashboard"))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).populate_existing().first()
        if user is None or not user.check_password(form.password.data):
            if user:
                activity_log_service.log_activity(user.id, 'failed_login')
            flash("Invalid username or password", "danger")
            return redirect(url_for("auth.login"))

        if not user.is_active:
            activity_log_service.log_activity(user.id, 'failed_login_inactive')
            flash("This account is deactivated. Contact an administrator.", "danger")
            return redirect(url_for("auth.login"))

        user.last_login_at = datetime.now(timezone.utc).replace(tzinfo=None)
        db.session.commit()
        login_user(user, remember=form.remember_me.data)
        activity_log_service.log_activity(user.id, 'login')
        flash(f"Welcome, {user.username}!", "success")
        next_page = request.args.get("next")
        if not next_page or urlsplit(next_page).netloc != "":
            next_page = url_for("drive.dashboard")
        return redirect(next_page)
    return render_template("auth/login.html", title="Log In", form=form)

@auth_web.route("/logout")
def logout():
    logout_user()
    return redirect(url_for("auth.login"))

@auth_web.route("/reset-password/<token>", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for("drive.dashboard"))

    token_record, error_msg = password_service.verify_reset_token(token)
    if not token_record:
        activity_log_service.log_activity(None, 'password_reset_failed_or_expired', metadata={'error': error_msg})
        flash(error_msg, "danger")
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        new_password = request.form.get("new_password")
        confirm_password = request.form.get("confirm_password")

        if new_password != confirm_password:
            flash("Passwords do not match.", "danger")
            return render_template("auth/reset_password.html", title="Reset Password", token=token)

        is_valid, val_error = password_service.validate_password(new_password)
        if not is_valid:
            flash(val_error, "danger")
            return render_template("auth/reset_password.html", title="Reset Password", token=token)

        user = User.query.filter_by(id=token_record.user_id).populate_existing().first()
        if not user.is_active:
            flash("This account is deactivated. Contact an administrator.", "danger")
            return redirect(url_for("auth.login"))

        if user.check_password(new_password):
            flash("New password must be different from the current password.", "danger")
            return render_template("auth/reset_password.html", title="Reset Password", token=token)

        user.set_password(new_password)

        from datetime import datetime, timezone
        token_record.used_at = datetime.now(timezone.utc).replace(tzinfo=None)
        token_record.ip_used = request.remote_addr
        token_record.user_agent_used = request.user_agent.string

        # Revoke all API tokens for this user for security
        api_service.revoke_tokens(user)

        db.session.commit()

        activity_log_service.log_activity(user.id, 'password_reset_completed')
        flash("Your password has been reset successfully. You can now log in with your new password.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/reset_password.html", title="Reset Password", token=token)
