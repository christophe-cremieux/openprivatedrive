document.addEventListener('DOMContentLoaded', function() {
    const userPickerInputs = document.querySelectorAll('.user-picker');

    userPickerInputs.forEach(input => {
        const wrapper = document.createElement('div');
        wrapper.className = 'user-picker-wrapper position-relative';
        input.parentNode.insertBefore(wrapper, input);
        wrapper.appendChild(input);

        const dropdown = document.createElement('div');
        dropdown.className = 'dropdown-menu w-100 shadow-sm';
        dropdown.style.marginTop = '0';
        wrapper.appendChild(dropdown);

        let timeout = null;

        input.addEventListener('input', function() {
            clearTimeout(timeout);
            const query = input.value.trim();

            if (query.length < 2) {
                dropdown.classList.remove('show');
                return;
            }

            timeout = setTimeout(() => {
                fetch(`/api/v1/users/search?q=${encodeURIComponent(query)}`)
                    .then(response => response.json())
                    .then(data => {
                        dropdown.innerHTML = '';
                        if (data.data && data.data.length > 0) {
                            data.data.forEach(user => {
                                const item = document.createElement('button');
                                item.type = 'button';
                                item.className = 'dropdown-item d-flex justify-content-between align-items-center';
                                item.innerHTML = `
                                    <strong>${user.username}</strong>
                                    <small class="text-muted">${user.email}</small>
                                `;
                                item.addEventListener('click', () => {
                                    input.value = user.username;
                                    dropdown.classList.remove('show');
                                });
                                dropdown.appendChild(item);
                            });
                            dropdown.classList.add('show');
                        } else {
                            dropdown.classList.remove('show');
                        }
                    });
            }, 300);
        });

        document.addEventListener('click', function(e) {
            if (!wrapper.contains(e.target)) {
                dropdown.classList.remove('show');
            }
        });
    });
});
