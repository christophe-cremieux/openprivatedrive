"""
Description: End-to-end test module for test combined flow.
Author: Your Christophe CREMIEUX <sammy.crem@gmail.com>
Copyright: (c) 2026 Christophe CREMIEUX

License: GNU Affero General Public License v3.0
         This program is free software: you can redistribute it and/or modify
         it under the terms of the GNU Affero General Public License as
         published by the Free Software Foundation.

         See the LICENSE file at the root of this project for details.
"""

from playwright.sync_api import expect
import os
import tempfile
import time
import re
import pytest
import socket
import subprocess
import shutil
import requests
import zipfile

def get_free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('', 0))
    port = s.getsockname()[1]
    s.close()
    return port

@pytest.fixture(scope="module")
def server_url_local():
    port = get_free_port()
    host = "127.0.0.1"
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test.db")
    storage_path = os.path.join(temp_dir, "storage")
    os.makedirs(storage_path)

    env = os.environ.copy()
    env["FLASK_APP"] = "run.py"
    env["DATABASE_URL"] = f"sqlite:///{db_path}"
    env["STORAGE_PATH"] = storage_path
    env["SECRET_KEY"] = "testsecret"
    env["WTF_CSRF_ENABLED"] = "True"
    env["ADMIN_PASSWORD"] = "admin123"
    env["PYTHONUNBUFFERED"] = "1"
    env["RATELIMIT_ENABLED"] = "False"

    log_file = open(os.path.join(temp_dir, "server.log"), "w")
    process = subprocess.Popen(["python3", "run.py", str(port)], env=env, stdout=log_file, stderr=subprocess.STDOUT)

    url = f"http://{host}:{port}"
    for i in range(30):
        try:
            if requests.get(url, timeout=1).status_code in [200, 302]: break
        except: pass
        time.sleep(1)

    yield url
    process.terminate()
    process.wait()
    log_file.close()
    shutil.rmtree(temp_dir)

def test_comprehensive_application_flow(page, server_url_local):
    server_url = server_url_local
    browser = page.context.browser

    # --- Setup Local Files ---
    working_dir = os.path.abspath("tests/e2e/Working")
    os.makedirs(working_dir, exist_ok=True)
    with open(os.path.join(working_dir, "file1.txt"), "w") as f: f.write("file1 content")

    # 1. Admin Login & User Creation
    print("\n[Step 1] Admin: Login and Create Users")
    page.goto(f"{server_url}/login")
    page.fill('input[name="username"]', "admin")
    page.fill('input[name="password"]', "admin123")
    page.click('input[type="submit"]')
    expect(page.locator('.navbar-brand')).to_be_visible(timeout=10000)

    page.goto(f"{server_url}/admin/users")
    for user in ["user_a", "user_b"]:
        page.click('button[data-bs-target="#createUserModal"]')
        page.wait_for_selector('#createUserModal.show', state='visible')
        page.fill('#createUserModal input[name="username"]', user)
        page.fill('#createUserModal input[name="email"]', f"{user}@example.com")
        page.fill('#createUserModal input[name="password"]', "Password123456")
        page.locator('#createUserModal button:has-text("Create User")').click()
        page.wait_for_selector('#createUserModal', state='hidden')
        expect(page.locator('.alert-success')).to_be_visible()
    print("Users created.")

    # 2. User A: Directory Upload, Preview & Bulk Download
    print("[Step 2] User A: Directory Upload & Bulk Download")
    context_a = browser.new_context()
    page_a = context_a.new_page()
    page_a.goto(f"{server_url}/login")
    page_a.fill('input[name="username"]', "user_a")
    page_a.fill('input[name="password"]', "Password123456")
    page_a.click('input[type="submit"]')
    expect(page_a.locator('.navbar-brand')).to_be_visible()

    page_a.click('button[data-bs-target="#uploadFileModal"]')
    page_a.wait_for_selector('#uploadFileModal.show', state='visible')
    page_a.click('label[for="modeDir"]')
    page_a.set_input_files('input[id="fileInput"]', working_dir)
    page_a.click('button[id="startUploadBtn"]')
    expect(page_a.locator("table")).to_contain_text("Working", timeout=20000)

    # Enter directory and view file
    page_a.click('a:has-text("Working")')
    expect(page_a.locator("table")).to_contain_text("file1.txt")
    with page_a.expect_navigation():
        page_a.click('a:has-text("file1.txt")')
    expect(page_a.locator("h1")).to_contain_text("file1.txt")
    expect(page_a.locator(".main-content")).to_contain_text("file1 content")
    print("Directory upload and preview verified.")

    # Star and Search
    print("[Step 2.5] User A: Star and Search")
    page_a.goto(f"{server_url}/my-drive")
    page_a.click('a:has-text("Working")')
    row = page_a.locator("tr:has-text('file1.txt')").first
    row.locator(".bi-star").click()
    page_a.click('a:has-text("Starred")')
    expect(page_a.locator("table")).to_contain_text("file1.txt")
    page_a.fill('input[name="q"]', "file1")
    page_a.keyboard.press("Enter")
    expect(page_a.locator("table")).to_contain_text("file1.txt")
    print("Star and Search verified.")

    # Bulk Download 'Working' folder as ZIP
    page_a.goto(f"{server_url}/my-drive")
    row = page_a.locator("tr:has-text('Working')").first
    row.locator(".item-checkbox").check()
    expect(page_a.locator("#bulkActionsBar")).to_be_visible()
    with page_a.expect_download() as download_info:
        page_a.click('button[id="bulkDownloadBtn"]')
    assert download_info.value.suggested_filename.endswith(".zip")
    print("Folder bulk download verified.")

    # 3. User A: Share with User B & Create Public Link
    print("[Step 3] User A: Sharing")
    # Share a single file (not just folder)
    page_a.goto(f"{server_url}/my-drive")
    page_a.click('a:has-text("Working")')
    row = page_a.locator("tr:has-text('file1.txt')").first
    row.locator(".bi-three-dots-vertical").click()
    share_url = row.locator('a.dropdown-item:has-text("Share")').get_attribute("href")
    page_a.goto(f"{server_url}{share_url}")
    page_a.fill('input[name="username"]', "user_b")
    page_a.click('button:has-text("Share")')
    expect(page_a.locator(".alert-success")).to_be_visible()

    # Create Public Download Link for file1.txt with password
    page_a.goto(f"{server_url}/my-drive")
    page_a.click('a:has-text("Working")')
    row = page_a.locator("tr:has-text('file1.txt')").first
    row.locator(".bi-three-dots-vertical").click()
    row.locator('button.action-public-link').click()
    page_a.wait_for_selector('#publicLinkModal.show', state='visible')
    page_a.fill('#publicLinkModal input[name="password"]', "PublicPass123")
    page_a.click('#publicLinkModal button:has-text("Create Link")')
    page_a.wait_for_selector('.alert-success')
    public_download_url = re.search(r'Public link created: (http://[^\s]+)', page_a.locator('.alert-success').inner_text()).group(1)
    print(f"Public download link: {public_download_url}")

    # 4. ZIP Operations & Public Upload Link
    print("[Step 4] User A: ZIP and Public Upload")
    # Create and Upload ZIP
    with tempfile.TemporaryDirectory() as tmp_dir:
        zip_path = os.path.join(tmp_dir, "archive.zip")
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.writestr("zipped.txt", "zip content")
        page_a.goto(f"{server_url}/my-drive")
        page_a.click('button[data-bs-target="#uploadFileModal"]')
        page_a.set_input_files('input[id="fileInput"]', zip_path)
        page_a.click('button[id="startUploadBtn"]')
        expect(page_a.locator("table")).to_contain_text("archive.zip", timeout=20000)

    # Extract ZIP
    row = page_a.locator("tr:has-text('archive.zip')").first
    row.locator(".bi-three-dots-vertical").click()
    row.locator('button.action-extract-zip').click()
    page_a.click('#extractZipModal button:has-text("Extract")')

    page_a.goto(f"{server_url}/zip-extractions")
    for _ in range(10):
        if "completed" in page_a.locator("table").inner_text().lower(): break
        time.sleep(2)
        page_a.reload()

    # Create Public Upload Link for 'Working' folder
    page_a.goto(f"{server_url}/my-drive")
    row = page_a.locator("tr:has-text('Working')").first
    row.locator(".bi-three-dots-vertical").click()
    row.locator('button.action-public-link').click()
    page_a.select_option('#publicLinkTypeSelect', 'upload')
    page_a.fill('#publicLinkModal input[name="password"]', "UploadPass123")
    page_a.click('#publicLinkModal button:has-text("Create Link")')
    page_a.wait_for_selector('.alert-success')
    public_upload_url = re.search(r'Public link created: (http://[^\s]+)', page_a.locator('.alert-success').inner_text()).group(1)
    print(f"Public upload link: {public_upload_url}")

    # 5. User B: Verify Shared Item
    print("[Step 5] User B: Verify Sharing")
    context_b = browser.new_context()
    page_b = context_b.new_page()
    page_b.goto(f"{server_url}/login")
    page_b.fill('input[name="username"]', "user_b")
    page_b.fill('input[name="password"]', "Password123456")
    page_b.click('input[type="submit"]')
    page_b.click('a:has-text("Shared with me")')
    expect(page_b.locator(".list-group")).to_contain_text("file1.txt")
    print("Recipient verification passed.")

    # 6. External Guest: Download & Upload
    print("[Step 6] External Guest: Public Link Access")
    context_guest = browser.new_context()
    page_guest = context_guest.new_page()

    # Test Public Download with password
    page_guest.goto(public_download_url)
    page_guest.fill('input[name="password"]', "PublicPass123")
    with page_guest.expect_download() as dl_info:
        page_guest.click('button:has-text("Download")')
    assert dl_info.value.suggested_filename == "file1.txt"
    print("Public download verified.")

    # Test Public Upload with password
    page_guest.goto(public_upload_url)
    page_guest.fill('input[name="password"]', "UploadPass123")
    page_guest.click('button:has-text("Unlock Upload")')
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tmp:
        tmp.write(b"Guest upload")
        tmp_path = tmp.name
    try:
        page_guest.set_input_files('input[name="file"]', tmp_path)
        page_guest.click('button:has-text("Start Upload")')
        expect(page_guest.locator(".alert-success")).to_contain_text("Successfully uploaded")
    finally:
        os.remove(tmp_path)
    print("Public upload verified.")

    # 7. Admin: Tasks & Audit
    print("[Step 7] Admin: Final Tasks")
    page.goto(f"{server_url}/admin/logs")
    expect(page.locator("table")).to_contain_text("public_link_download")
    page.goto(f"{server_url}/admin/diagnostics")
    expect(page.locator("h1:has-text('System Diagnostics')")).to_be_visible()
    page.goto(f"{server_url}/admin/storage")
    expect(page.locator("h1.h2")).to_contain_text("Admin - Storage")
    page.goto(f"{server_url}/admin/upload-policy")
    expect(page.locator("h1.h2")).to_contain_text("Upload Policy")
    print("Admin audit verified.")

    # 8. User A: Rename and Delete
    print("[Step 8] User A: Rename and Delete")
    page_a.goto(f"{server_url}/my-drive")
    page_a.click('a:has-text("Working")')
    row = page_a.locator("tr:has-text('file1.txt')").first
    row.locator(".bi-three-dots-vertical").click()
    page_a.click('button.action-rename')
    page_a.wait_for_selector('#renameModal.show', state='visible')
    page_a.fill('#renameInput', "renamed_file.txt")
    page_a.click('#renameModal button:has-text("Rename")')
    page_a.wait_for_selector('#renameModal', state='hidden')
    expect(page_a.locator("table")).to_contain_text("renamed_file.txt")

    # Delete it
    row = page_a.locator("tr:has-text('renamed_file.txt')").first
    row.locator(".bi-three-dots-vertical").click()
    page_a.click('button.action-delete')
    page_a.wait_for_selector('#deleteModal.show', state='visible')
    page_a.click('#confirmDeleteFirstBtn')
    page_a.wait_for_selector('#deleteModal', state='hidden')
    expect(page_a.locator("table")).not_to_contain_text("renamed_file.txt")
    print("Rename and Delete verified.")

    print("\nSUCCESS: All E2E scenarios passed!")

    context_a.close()
    context_b.close()
    context_guest.close()

    # Cleanup local files
    if os.path.exists(working_dir):
        shutil.rmtree(working_dir)
