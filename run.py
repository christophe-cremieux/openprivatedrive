"""
Description: Entrypoint script that creates and runs the Flask application, initializes the instance directory, and starts background jobs.
Author: Your Christophe CREMIEUX <sammy.crem@gmail.com>
Copyright: (c) 2026 Christophe CREMIEUX

License: GNU Affero General Public License v3.0
         This program is free software: you can redistribute it and/or modify
         it under the terms of the GNU Affero General Public License as
         published by the Free Software Foundation.

         See the LICENSE file at the root of this project for details.
"""

import os
from app import create_app, db
from app.services.playground import seed_test_users
from app.services.bootstrap_service import bootstrap_service

app = create_app()

# Ensure the instance directory exists
instance_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), "instance")
if not os.path.exists(instance_path):
    os.makedirs(instance_path)

# Ensure database tables are created
if __name__ == "__main__":
    with app.app_context():
        db.create_all()

        admin_user = bootstrap_service.ensure_admin_user(app)
        print(f"Admin user ready: {admin_user.username}")

        # Seed test users if requested
        if os.environ.get("SEED_DEMO_USERS") == "True":
            seed_test_users()

        # Start periodic trash retention job
        from app.services.background_jobs import trash_retention_policy_job
        import threading
        # We use a standard thread here instead of executor because executor tries to copy request context,
        # which doesn't exist at startup.
        threading.Thread(target=trash_retention_policy_job, args=(app,), daemon=True).start()

if __name__ == "__main__":
    import sys
    port = 5100
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            pass
    app.run(host="0.0.0.0", port=port)
