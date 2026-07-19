"""
Description: Service layer implementation for ActivityLogService.
Author: Your Christophe CREMIEUX <sammy.crem@gmail.com>
Copyright: (c) 2026 Christophe CREMIEUX

License: GNU Affero General Public License v3.0
         This program is free software: you can redistribute it and/or modify
         it under the terms of the GNU Affero General Public License as
         published by the Free Software Foundation.

         See the LICENSE file at the root of this project for details.
"""

from flask import request
from app.extensions import db
from app.models.activity_log import ActivityLog
from app.models.user import User
from app.models.file import File
from sqlalchemy import func

class ActivityLogService:
    @staticmethod
    def log_activity(actor_id, action, resource_type=None, resource_id=None, metadata=None, commit=True):
        """Logs a user activity."""
        ip_address = None
        user_agent = None

        # Check if we are in a request context
        try:
            if request:
                ip_address = request.remote_addr
                user_agent = request.user_agent.string if request.user_agent else None
        except RuntimeError:
            # Not in a request context
            pass

        log = ActivityLog(
            actor_user_id=actor_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata_json=metadata
        )
        db.session.add(log)
        if commit:
            db.session.commit()
        return log

    @staticmethod
    def get_recent_logs(limit=100, category=None):
        """Retrieves recent activity logs, optionally filtered by category."""
        query = ActivityLog.query

        if category:
            actions = []
            if category == 'logins':
                actions = ['login', 'failed_login', 'api_login', 'api_failed_login', 'failed_login_inactive', 'api_failed_login_inactive']
            elif category == 'uploads':
                actions = ['upload_file', 'public_upload_success', 'public_upload_rejected']
            elif category == 'security':
                actions = ['password_changed', 'api_password_changed', 'password_reset_link_created', 'password_reset_completed', 'password_reset_failed_or_expired']
            elif category == 'shares':
                actions = ['create_public_link', 'share_file', 'share_folder', 'public_link_download']
            elif category == 'deletions':
                actions = ['delete_file', 'delete_folder', 'permanent_delete_file', 'permanent_delete_folder', 'empty_trash']

            if actions:
                query = query.filter(ActivityLog.action.in_(actions))

        return query.order_by(ActivityLog.created_at.desc()).limit(limit).all()

    @staticmethod
    def get_dashboard_stats():
        """Returns overview metrics for the admin dashboard."""
        from app.models.public_link import PublicLink
        from app.models.zip_extract_job import ZipExtractJob

        total_users = User.query.count()
        total_files = File.query.filter_by(is_deleted=False).count()
        total_usage = db.session.query(func.sum(File.size_bytes)).filter(File.is_deleted == False).scalar() or 0
        active_public_links = PublicLink.query.filter_by(is_active=True).count()

        # Failed logins in the last 24h
        from datetime import datetime, timedelta, timezone
        day_ago = datetime.now(timezone.utc) - timedelta(days=1)
        failed_logins_24h = ActivityLog.query.filter(
            ActivityLog.action.in_(['failed_login', 'api_failed_login', 'failed_login_inactive', 'api_failed_login_inactive']),
            ActivityLog.created_at >= day_ago
        ).count()

        # Background job failures (all time for now)
        failed_scans = File.query.filter(File.scan_status.in_(['infected', 'scan_failed'])).count()
        failed_extractions = ZipExtractJob.query.filter_by(status='failed').count()

        return {
            'total_users': total_users,
            'total_files': total_files,
            'total_usage_bytes': total_usage,
            'active_public_links': active_public_links,
            'failed_logins_24h': failed_logins_24h,
            'failed_scans': failed_scans,
            'failed_extractions': failed_extractions
        }

    @staticmethod
    def get_all_users_with_stats():
        """Retrieves all users with their storage usage stats in a single optimized query."""
        from app.models.api_token import ApiToken

        # Subquery for storage usage grouped by owner
        usage_sub = db.session.query(
            File.owner_id,
            func.sum(File.size_bytes).label('usage')
        ).filter(File.is_deleted == False).group_by(File.owner_id).subquery()

        # Subquery for token counts grouped by user
        token_sub = db.session.query(
            ApiToken.user_id,
            func.count(ApiToken.id).label('token_count')
        ).filter(
            ApiToken.revoked_at == None,
            ApiToken.token_type == 'refresh'
        ).group_by(ApiToken.user_id).subquery()

        # Join User with subqueries
        users_with_stats = db.session.query(
            User,
            usage_sub.c.usage,
            token_sub.c.token_count
        ).outerjoin(
            usage_sub, User.id == usage_sub.c.owner_id
        ).outerjoin(
            token_sub, User.id == token_sub.c.user_id
        ).all()

        results = []
        for user, usage, token_count in users_with_stats:
            usage_val = usage or 0
            token_count_val = token_count or 0
            results.append({
                'user': user,
                'storage_usage_bytes': usage_val,
                'storage_quota_bytes': user.storage_quota_bytes,
                'usage_percent': (usage_val / user.storage_quota_bytes * 100) if user.storage_quota_bytes > 0 else 0,
                'active_tokens': token_count_val
            })
        return results

    @staticmethod
    def get_system_storage_usage():
        """Calculates total system storage usage."""
        total_usage = db.session.query(func.sum(File.size_bytes)).filter(File.is_deleted == False).scalar() or 0
        total_files = File.query.filter_by(is_deleted=False).count()
        return {
            'total_usage_bytes': total_usage,
            'total_files': total_files
        }

activity_log_service = ActivityLogService()
