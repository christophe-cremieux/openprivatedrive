document.addEventListener('DOMContentLoaded', function() {
    const fileInput = document.getElementById('fileInput');
    const modeFile = document.getElementById('modeFile');
    const modeDir = document.getElementById('modeDir');
    const singleFileOptions = document.getElementById('singleFileOptions');
    const bulkFileOptions = document.getElementById('bulkFileOptions');
    const relativePathsContainer = document.getElementById('relativePathsContainer');
    const uploadForm = document.getElementById('uploadForm');

    function updateUI() {
        const files = fileInput.files;
        if (files.length > 1) {
            if (singleFileOptions) singleFileOptions.style.display = 'none';
            if (bulkFileOptions) bulkFileOptions.style.display = 'block';
        } else {
            if (singleFileOptions) singleFileOptions.style.display = 'block';
            if (bulkFileOptions) bulkFileOptions.style.display = 'none';

            const customNameInput = document.getElementById('custom_name');
            if (customNameInput && files.length === 1) {
                customNameInput.value = files[0].name;
            }
        }

        relativePathsContainer.innerHTML = '';
        if (modeDir && modeDir.checked) {
            for (let i = 0; i < files.length; i++) {
                const input = document.createElement('input');
                input.type = 'hidden';
                input.name = 'relative_paths[]';
                input.value = files[i].webkitRelativePath || '';
                relativePathsContainer.appendChild(input);
            }
        }
    }

    if (modeFile) {
        modeFile.addEventListener('change', function() {
            fileInput.webkitdirectory = false;
            fileInput.multiple = true;
            fileInput.value = '';
            updateUI();
        });
    }

    if (modeDir) {
        modeDir.addEventListener('change', function() {
            fileInput.webkitdirectory = true;
            fileInput.multiple = true;
            fileInput.value = '';
            updateUI();
        });
    }

    if (fileInput) {
        fileInput.addEventListener('change', updateUI);
    }

    const encryptCheck = document.getElementById('encryptCheck');
    const encryptionFields = document.getElementById('encryptionFields');

    function toggleEncryptionFields(checked) {
        if (!encryptionFields) return;
        encryptionFields.style.display = checked ? 'block' : 'none';
        const passwordInputs = encryptionFields.querySelectorAll('input');
        passwordInputs.forEach(input => input.required = checked);
    }

    if (encryptCheck && encryptionFields) {
        encryptCheck.addEventListener('change', function() {
            toggleEncryptionFields(this.checked);
        });

        // Handle auto-open for folder policy when modal is shown
        const uploadFileModalEl = document.getElementById('uploadFileModal');
        if (uploadFileModalEl) {
            uploadFileModalEl.addEventListener('show.bs.modal', function () {
                if (encryptCheck.checked) {
                    toggleEncryptionFields(true);
                }
            });
        }

        // Initialize state (handles folder policy)
        if (encryptCheck.checked) {
            toggleEncryptionFields(true);
        }
    }

    // Global Toast Utility
    const toastEl = document.getElementById('liveToast');
    const toast = toastEl ? new bootstrap.Toast(toastEl, { delay: 5000 }) : null;
    const toastBody = document.getElementById('toastBody');

    window.showToast = function(message, category = 'info') {
        if (!toast) return;

        toastEl.classList.remove('bg-success', 'bg-danger', 'bg-info', 'bg-warning', 'text-white');

        if (category === 'success') {
            toastEl.classList.add('bg-success', 'text-white');
        } else if (category === 'danger') {
            toastEl.classList.add('bg-danger', 'text-white');
        } else if (category === 'warning') {
            toastEl.classList.add('bg-warning', 'text-dark');
        } else {
            toastEl.classList.add('bg-info', 'text-white');
        }

        toastBody.innerText = message;
        toast.show();
    };

    if (uploadForm) {
        uploadForm.addEventListener('submit', function(e) {
            e.preventDefault();

            // Client-side validation for encryption
            if (encryptCheck && encryptCheck.checked) {
                const pass = document.getElementById('enc_password').value;
                const confirm = document.getElementById('enc_password_confirm').value;

                if (pass.length < 12) {
                    showToast('Encryption password must be at least 12 characters long.', 'warning');
                    return;
                }
                if (pass !== confirm) {
                    showToast('Passwords do not match.', 'warning');
                    return;
                }
            }

            const formData = new FormData(uploadForm);
            const xhr = new XMLHttpRequest();
            const progressBar = document.getElementById('uploadProgressBar');
            const progressContainer = document.getElementById('uploadProgress');
            const formContent = document.getElementById('uploadFormContent');
            const statusText = document.getElementById('uploadStatus');
            const startBtn = document.getElementById('startUploadBtn');
            const cancelBtn = document.getElementById('cancelUploadBtn');

            progressContainer.classList.remove('d-none');
            formContent.classList.add('d-none');
            startBtn.disabled = true;
            cancelBtn.disabled = true;

            xhr.upload.addEventListener('progress', function(e) {
                if (e.lengthComputable) {
                    const percent = Math.round((e.loaded / e.total) * 100);
                    progressBar.style.width = percent + '%';
                    statusText.innerText = `Uploading... ${percent}%`;
                }
            });

            xhr.addEventListener('load', function() {
                if (xhr.status >= 200 && xhr.status < 300) {
                    statusText.innerText = 'Upload complete! Refreshing...';
                    window.location.reload();
                } else {
                    let errorMsg = 'Upload failed. Please try again.';
                    try {
                        const response = JSON.parse(xhr.responseText);
                        if (response.error) {
                            errorMsg = response.error;
                        }
                    } catch (e) {
                        errorMsg = xhr.statusText || errorMsg;
                    }

                    statusText.innerText = 'Upload failed: ' + errorMsg;
                    startBtn.disabled = false;
                    cancelBtn.disabled = false;
                    progressContainer.classList.add('d-none');
                    formContent.classList.remove('d-none');
                    showToast(errorMsg, 'danger');
                }
            });

            xhr.addEventListener('error', function() {
                showToast('An error occurred during upload.', 'danger');
                startBtn.disabled = false;
                cancelBtn.disabled = false;
                progressContainer.classList.add('d-none');
                formContent.classList.remove('d-none');
            });

            xhr.open('POST', uploadForm.action, true);
            xhr.send(formData);
        });
    }

    // View Toggle Logic
    const listBtn = document.getElementById('listBtn');
    const gridBtn = document.getElementById('gridBtn');

    function toggleView(mode) {
        const listCont = document.getElementById('list-container');
        const gridCont = document.getElementById('grid-container');

        if (!listCont || !gridCont) return;

        if (mode === 'grid') {
            listCont.classList.add('d-none');
            gridCont.classList.remove('d-none');
            if (gridBtn) gridBtn.classList.add('active');
            if (listBtn) listBtn.classList.remove('active');
            localStorage.setItem('driveView', 'grid');
        } else {
            listCont.classList.remove('d-none');
            gridCont.classList.add('d-none');
            if (listBtn) listBtn.classList.add('active');
            if (gridBtn) gridBtn.classList.remove('active');
            localStorage.setItem('driveView', 'list');
        }
    }

    if (listBtn) {
        listBtn.addEventListener('click', () => toggleView('list'));
    }
    if (gridBtn) {
        gridBtn.addEventListener('click', () => toggleView('grid'));
    }

    const savedView = localStorage.getItem('driveView') || 'list';
    toggleView(savedView);

    // Bulk Selection Logic
    const selectAll = document.getElementById('selectAll');
    const toolbarSelectAll = document.getElementById('toolbarSelectAll');
    const itemCheckboxes = document.querySelectorAll('.item-checkbox');
    const bulkBar = document.getElementById('bulkActionsBar');
    const selectedCountSpan = document.getElementById('selectedCount');

    function updateBulkBar() {
        // We use a Set of UUIDs to count unique selected items because list and grid checkboxes share the same UUIDs
        const selectedUuids = new Set();
        document.querySelectorAll('.item-checkbox:checked').forEach(cb => {
            selectedUuids.add(cb.getAttribute('data-uuid'));
        });

        const checkedCount = selectedUuids.size;
        if (checkedCount > 0) {
            bulkBar.classList.remove('d-none');
            selectedCountSpan.innerText = checkedCount;
        } else {
            bulkBar.classList.add('d-none');
        }

        // Sync master checkboxes
        const allChecked = itemCheckboxes.length > 0 && Array.from(itemCheckboxes).every(cb => cb.checked);
        if (selectAll) selectAll.checked = allChecked;
        if (toolbarSelectAll) toolbarSelectAll.checked = allChecked;
    }

    function toggleAll(checked) {
        itemCheckboxes.forEach(cb => cb.checked = checked);
        if (selectAll) selectAll.checked = checked;
        if (toolbarSelectAll) toolbarSelectAll.checked = checked;
        updateBulkBar();
    }

    if (selectAll) {
        selectAll.addEventListener('change', function() {
            toggleAll(this.checked);
        });
    }

    if (toolbarSelectAll) {
        toolbarSelectAll.addEventListener('change', function() {
            toggleAll(this.checked);
        });
    }

    itemCheckboxes.forEach(cb => {
        cb.addEventListener('change', function() {
            const uuid = this.getAttribute('data-uuid');
            const type = this.getAttribute('data-type');
            const checked = this.checked;

            // Sync other checkboxes for the same item (e.g., between list and grid views)
            document.querySelectorAll(`.item-checkbox[data-uuid="${uuid}"][data-type="${type}"]`).forEach(other => {
                if (other !== this) {
                    other.checked = checked;
                }
            });

            updateBulkBar();
        });
    });

    const clearSelectionBtn = document.getElementById('clearSelectionBtn');
    if (clearSelectionBtn) {
        clearSelectionBtn.addEventListener('click', () => {
            itemCheckboxes.forEach(cb => cb.checked = false);
            if (selectAll) selectAll.checked = false;
            updateBulkBar();
        });
    }

    const bulkDeleteBtn = document.getElementById('bulkDeleteBtn');
    if (bulkDeleteBtn) {
        bulkDeleteBtn.addEventListener('click', () => {
            if (confirm('Are you sure you want to delete all selected items?')) {
                const form = document.createElement('form');
                form.method = 'POST';
                form.action = '/bulk/delete';

                const csrf = document.querySelector('input[name="csrf_token"]').value;
                const csrfInput = document.createElement('input');
                csrfInput.type = 'hidden';
                csrfInput.name = 'csrf_token';
                csrfInput.value = csrf;
                form.appendChild(csrfInput);

                const selectedUuids = new Set();
                document.querySelectorAll('.item-checkbox:checked').forEach(cb => {
                    const uuid = cb.getAttribute('data-uuid');
                    const type = cb.getAttribute('data-type');
                    const key = `${type}:${uuid}`;
                    if (!selectedUuids.has(key)) {
                        selectedUuids.add(key);
                        const input = document.createElement('input');
                        input.type = 'hidden';
                        input.name = type === 'folder' ? 'folder_uuids[]' : 'file_uuids[]';
                        input.value = uuid;
                        form.appendChild(input);
                    }
                });

                document.body.appendChild(form);
                form.submit();
            }
        });
    }

    const bulkDownloadBtn = document.getElementById('bulkDownloadBtn');
    if (bulkDownloadBtn) {
        bulkDownloadBtn.addEventListener('click', () => {
            const params = new URLSearchParams();
            const selectedUuids = new Set();
            document.querySelectorAll('.item-checkbox:checked').forEach(cb => {
                const uuid = cb.getAttribute('data-uuid');
                const type = cb.getAttribute('data-type');
                const key = `${type}:${uuid}`;
                if (!selectedUuids.has(key)) {
                    selectedUuids.add(key);
                    const paramKey = type === 'folder' ? 'folder_uuids[]' : 'file_uuids[]';
                    params.append(paramKey, uuid);
                }
            });
            window.location.href = '/bulk/download?' + params.toString();
        });
    }

    const bulkMoveBtn = document.getElementById('bulkMoveBtn');
    if (bulkMoveBtn) {
        bulkMoveBtn.addEventListener('click', () => {
            const moveModal = new bootstrap.Modal(document.getElementById('moveModal'));
            const container = document.getElementById('moveItemsContainer');
            container.innerHTML = '';

            const selectedUuids = new Set();
            document.querySelectorAll('.item-checkbox:checked').forEach(cb => {
                const uuid = cb.getAttribute('data-uuid');
                const type = cb.getAttribute('data-type');
                const key = `${type}:${uuid}`;
                if (!selectedUuids.has(key)) {
                    selectedUuids.add(key);
                    const input = document.createElement('input');
                    input.type = 'hidden';
                    input.name = type === 'folder' ? 'folder_uuids[]' : 'file_uuids[]';
                    input.value = uuid;
                    container.appendChild(input);
                }
            });

            moveModal.show();
        });
    }

    // Confirm actions
    const confirmButtons = document.querySelectorAll('.confirm-action');
    confirmButtons.forEach(btn => {
        btn.addEventListener('click', function(e) {
            const msg = this.getAttribute('data-confirm') || 'Are you sure?';
            if (!confirm(msg)) {
                e.preventDefault();
            }
        });
    });

    // Reusable Modal Logic
    const renameModal = document.getElementById('renameModal') ? new bootstrap.Modal(document.getElementById('renameModal')) : null;
    const deleteModal = document.getElementById('deleteModal') ? new bootstrap.Modal(document.getElementById('deleteModal')) : null;
    const doubleDeleteModal = document.getElementById('deleteDoubleConfirmModal') ? new bootstrap.Modal(document.getElementById('deleteDoubleConfirmModal')) : null;
    const publicLinkModal = document.getElementById('publicLinkModal') ? new bootstrap.Modal(document.getElementById('publicLinkModal')) : null;
    const extractZipModalEl = document.getElementById('extractZipModal');
    const extractZipModal = extractZipModalEl ? new bootstrap.Modal(extractZipModalEl) : null;

    let pendingDeleteType = null;

    // Use event delegation for actions to support items in both list and grid views
    document.addEventListener('click', function(e) {
        const extractBtn = e.target.closest('.action-extract-zip');
        if (extractBtn) {
            const uuid = extractBtn.getAttribute('data-uuid');
            const name = extractBtn.getAttribute('data-name');
            const form = document.getElementById('extractZipForm');
            const nameSpan = document.getElementById('extractZipName');

            form.action = `/files/${uuid}/extract-zip`;
            nameSpan.innerText = name;
            extractZipModal.show();
        }

        const renameBtn = e.target.closest('.action-rename');
        if (renameBtn) {
            const uuid = renameBtn.getAttribute('data-uuid');
            const type = renameBtn.getAttribute('data-type');
            const name = renameBtn.getAttribute('data-name');
            const form = document.getElementById('renameForm');
            const input = document.getElementById('renameInput');
            const title = document.getElementById('renameModalTitle');

            if (type === 'folder') {
                form.action = `/folders/${uuid}/rename`;
                title.innerText = 'Rename Folder';
            } else {
                form.action = `/files/${uuid}/rename`;
                title.innerText = 'Rename File';
            }
            input.value = name;
            renameModal.show();
        }

        const deleteBtn = e.target.closest('.action-delete');
        if (deleteBtn) {
            const uuid = deleteBtn.getAttribute('data-uuid');
            const type = deleteBtn.getAttribute('data-type');
            const name = deleteBtn.getAttribute('data-name');
            const form = document.getElementById('deleteForm');
            const title = document.getElementById('deleteModalTitle');
            const body = document.getElementById('deleteModalBody');

            pendingDeleteType = type;

            if (type === 'folder') {
                form.action = `/folders/${uuid}/delete`;
                title.innerText = 'Delete Folder';
                body.innerText = `Are you sure you want to delete '${name}' and all items inside it?`;
            } else {
                form.action = `/files/${uuid}/delete`;
                title.innerText = 'Delete File';
                body.innerText = `Are you sure you want to delete '${name}'?`;
            }
            deleteModal.show();
        }

        const publicLinkBtn = e.target.closest('.action-public-link');
        if (publicLinkBtn) {
            const uuid = publicLinkBtn.getAttribute('data-uuid');
            const type = publicLinkBtn.getAttribute('data-type');

            document.getElementById('publicLinkResUuid').value = uuid;
            document.getElementById('publicLinkResType').value = type;

            const folderOptions = document.getElementById('folderUploadOptions');
            if (type === 'folder') {
                folderOptions.style.display = 'block';
            } else {
                folderOptions.style.display = 'none';
            }
            publicLinkModal.show();
        }
    });

    const confirmDeleteFirstBtn = document.getElementById('confirmDeleteFirstBtn');
    if (confirmDeleteFirstBtn) {
        confirmDeleteFirstBtn.addEventListener('click', function() {
            if (pendingDeleteType === 'folder') {
                deleteModal.hide();
                doubleDeleteModal.show();
            } else {
                document.getElementById('deleteForm').submit();
            }
        });
    }

    const confirmDeleteFinalBtn = document.getElementById('confirmDeleteFinalBtn');
    if (confirmDeleteFinalBtn) {
        confirmDeleteFinalBtn.addEventListener('click', function() {
            document.getElementById('deleteForm').submit();
        });
    }


    const publicLinkTypeSelect = document.getElementById('publicLinkTypeSelect');
    if (publicLinkTypeSelect) {
        publicLinkTypeSelect.addEventListener('change', function() {
            const uploadSettings = document.getElementById('uploadSettings');
            if (this.value === 'upload') {
                uploadSettings.style.display = 'block';
            } else {
                uploadSettings.style.display = 'none';
            }
        });
    }

    // Tooltip Initialization
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });

    // Office Preview Auto-refresh
    if (document.getElementById('office-pending-indicator')) {
        setTimeout(function() {
            location.reload();
        }, 5000);
    }

    // Copy Link Logic
    document.querySelectorAll('.action-copy-link').forEach(btn => {
        btn.addEventListener('click', function() {
            const path = this.getAttribute('data-url');
            const url = window.location.origin + path;

            navigator.clipboard.writeText(url).then(() => {
                const originalContent = this.innerHTML;
                this.innerHTML = '<i class="bi bi-check2"></i> Copied!';
                this.classList.remove('btn-outline-primary');
                this.classList.add('btn-success');

                setTimeout(() => {
                    this.innerHTML = originalContent;
                    this.classList.remove('btn-success');
                    this.classList.add('btn-outline-primary');
                }, 2000);
            }).catch(err => {
                console.error('Failed to copy: ', err);
                showToast('Failed to copy link to clipboard.', 'danger');
            });
        });
    });

    // Workspace Action Menu
    const workspaceMenu = document.getElementById('workspaceContextMenu');
    const workspaceArea = document.querySelector('.workspace-area');

    if (workspaceArea && workspaceMenu) {
        workspaceArea.addEventListener('click', function(e) {
            // If the menu is already visible, clicking anywhere in the workspace should hide it
            if (workspaceMenu.classList.contains('show')) {
                workspaceMenu.style.display = 'none';
                workspaceMenu.classList.remove('show');
                return;
            }

            // Only trigger if clicking on the actual workspace area, not on items or buttons
            if (e.target === workspaceArea || e.target.id === 'list-container' || e.target.id === 'grid-container' || e.target.classList.contains('row')) {
                e.preventDefault();
                e.stopPropagation();
                workspaceMenu.style.display = 'block';
                workspaceMenu.classList.add('show');
                workspaceMenu.style.left = e.clientX + 'px';
                workspaceMenu.style.top = e.clientY + 'px';
            }
        });

        document.addEventListener('click', function(e) {
            if (workspaceMenu.classList.contains('show') && !workspaceMenu.contains(e.target)) {
                workspaceMenu.style.display = 'none';
                workspaceMenu.classList.remove('show');
            }
        });
    }

    // Mobile FAB
    const mobileFab = document.getElementById('mobileFab');
    if (mobileFab) {
        mobileFab.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            if (workspaceMenu) {
                const isVisible = workspaceMenu.style.display === 'block';
                if (isVisible) {
                    workspaceMenu.style.display = 'none';
                    workspaceMenu.classList.remove('show');
                } else {
                    workspaceMenu.style.display = 'block';
                    workspaceMenu.classList.add('show');
                    workspaceMenu.style.left = (window.innerWidth - 220) + 'px'; // Offset from right
                    workspaceMenu.style.top = (window.innerHeight - 200) + 'px'; // Fixed position for mobile
                }
            }
        });
    }

    // Drag and Drop Upload
    const dropZone = document.body;
    const uploadModalEl = document.getElementById('uploadFileModal');
    const uploadModal = uploadModalEl ? new bootstrap.Modal(uploadModalEl) : null;

    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, preventDefaults, false);
    });

    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }

    ['dragenter', 'dragover'].forEach(eventName => {
        dropZone.addEventListener(eventName, highlight, false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, unhighlight, false);
    });

    function highlight(e) {
        dropZone.classList.add('drag-over');
    }

    function unhighlight(e) {
        dropZone.classList.remove('drag-over');
    }

    dropZone.addEventListener('drop', handleDrop, false);

    async function handleDrop(e) {
        const dt = e.dataTransfer;
        const items = dt.items;

        if (items && items.length > 0) {
            const files = [];
            const paths = [];

            // Helper to traverse entries
            async function traverse(entry, path = "") {
                if (entry.isFile) {
                    const file = await new Promise(resolve => entry.file(resolve));
                    files.push(file);
                    paths.push(path + file.name);
                } else if (entry.isDirectory) {
                    const reader = entry.createReader();
                    const entries = await new Promise(resolve => {
                        let result = [];
                        const readAll = () => {
                            reader.readEntries(batch => {
                                if (batch.length === 0) resolve(result);
                                else {
                                    result = result.concat(batch);
                                    readAll();
                                }
                            });
                        };
                        readAll();
                    });
                    for (const child of entries) {
                        await traverse(child, path + entry.name + "/");
                    }
                }
            }

            for (let i = 0; i < items.length; i++) {
                const entry = items[i].webkitGetAsEntry();
                if (entry) {
                    await traverse(entry);
                }
            }

            if (files.length > 0) {
                // We can't easily set fileInput.files for multiple files with paths via JS security
                // So we'll use a DataTransfer object to build a new FileList
                const dataTransfer = new DataTransfer();
                files.forEach(f => dataTransfer.items.add(f));
                fileInput.files = dataTransfer.files;

                // Update relative paths
                relativePathsContainer.innerHTML = '';
                paths.forEach(p => {
                    const input = document.createElement('input');
                    input.type = 'hidden';
                    input.name = 'relative_paths[]';
                    input.value = p;
                    relativePathsContainer.appendChild(input);
                });

                if (files.length > 1 || paths[0].includes('/')) {
                    if (modeDir) modeDir.checked = true;
                    if (singleFileOptions) singleFileOptions.style.display = 'none';
                    if (bulkFileOptions) bulkFileOptions.style.display = 'block';
                }

                if (uploadModal) uploadModal.show();
            }
        } else if (dt.files.length > 0) {
            fileInput.files = dt.files;
            updateUI();
            if (uploadModal) uploadModal.show();
        }
    }
});

function toggleUploadOptions(select, uuid) {
    const options = document.getElementById('uploadOptions' + uuid);
    if (options) {
        if (select.value === 'upload') {
            options.style.display = 'block';
        } else {
            options.style.display = 'none';
        }
    }
}
