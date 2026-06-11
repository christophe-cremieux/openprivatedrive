"""
Description: Implements sharing web routes and views for shared resources.
Author: Your Christophe CREMIEUX <sammy.crem@gmail.com>
Copyright: (c) 2026 Christophe CREMIEUX

License: GNU Affero General Public License v3.0
         This program is free software: you can redistribute it and/or modify
         it under the terms of the GNU Affero General Public License as
         published by the Free Software Foundation.

         See the LICENSE file at the root of this project for details.
"""

from flask import Blueprint, render_template, redirect, url_for, request, flash, abort
from flask_login import login_required, current_user
from app.sharing.services import sharing_service
from app.services.folder_service import folder_service
from app.services.file_service import file_service

sharing_web = Blueprint("sharing", __name__)

@sharing_web.route("/shared-with-me")
@login_required
def shared_with_me():
    shared_items = sharing_service.list_shared_with_user(current_user)
    return render_template("drive/shared.html", title="Shared with Me", shared_items=shared_items)

@sharing_web.route("/share", methods=["POST"])
@login_required
def share_resource():
    resource_type = request.form.get("resource_type")
    resource_uuid = request.form.get("resource_uuid")
    username = request.form.get("username")
    permission = request.form.get("permission")
    inherit = request.form.get("inherit") == 'true'

    if not all([resource_type, resource_uuid, username, permission]):
        flash("Missing required fields for sharing.", "danger")
        return redirect(request.referrer or url_for("drive.dashboard"))

    resource = None
    if resource_type == 'folder':
        resource = folder_service.get_folder_by_uuid(resource_uuid)
    else:
        resource = file_service.get_file_by_uuid(resource_uuid)

    if not resource:
        abort(404)

    try:
        sharing_service.share_resource(
            current_user, resource, username, permission, inherit=inherit
        )
        flash(f"Resource shared with {username} successfully.", "success")
    except ValueError as e:
        flash(str(e), "danger")
    except Exception as e:
        flash("An error occurred during sharing.", "danger")

    return redirect(request.referrer or url_for("drive.dashboard"))

@sharing_web.route("/share/<share_uuid>/delete", methods=["POST"])
@login_required
def delete_share(share_uuid):
    try:
        sharing_service.remove_share(current_user, share_uuid)
        flash("Share removed successfully.", "success")
    except ValueError as e:
        flash(str(e), "danger")
    except Exception as e:
        flash("An error occurred while removing the share.", "danger")

    return redirect(request.referrer or url_for("drive.dashboard"))
