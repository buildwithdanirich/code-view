// ColabVerse admin interactions are kept separate from Django templates.

document.addEventListener('DOMContentLoaded', () => {
    const currentPath = window.location.pathname;

    document.querySelectorAll('.sidebar nav a').forEach((link) => {
        if (link.pathname === currentPath) {
            link.classList.add('active');
            link.setAttribute('aria-current', 'page');
        }
    });

    document.querySelectorAll('form[data-confirm]').forEach((form) => {
        form.addEventListener('submit', (event) => {
            if (!window.confirm(form.dataset.confirm)) {
                event.preventDefault();
            }
        });
    });

    const refreshButton = document.getElementById('refresh-health');
    const healthRoot = document.getElementById('health-root');

    if (refreshButton && healthRoot) {
        refreshButton.addEventListener('click', async () => {
            refreshButton.disabled = true;

            try {
                const response = await fetch(healthRoot.dataset.url, {
                    credentials: 'same-origin',
                    cache: 'no-store'
                });

                if (!response.ok) {
                    throw new Error('Health check failed');
                }

                const report = await response.json();
                document.getElementById('overall-status').textContent = report.overall;
                document.getElementById('checked-at').textContent = report.checked_at;

                const checksRoot = document.getElementById('health-checks');
                checksRoot.replaceChildren();

                Object.entries(report.checks).forEach(([name, check]) => {
                    const card = document.createElement('article');
                    card.className = 'health-card';
                    const heading = document.createElement('h3');
                    heading.textContent = `${name} · ${check.status}`;
                    const detail = document.createElement('p');
                    detail.textContent = check.detail;
                    card.append(heading, detail);
                    checksRoot.append(card);
                });
            } catch (error) {
                window.alert('Could not refresh project health.');
            } finally {
                refreshButton.disabled = false;
            }
        });
    }

    document.querySelectorAll('.delete-form').forEach((form) => {
        form.addEventListener('submit', (event) => {
            const typed = form.querySelector('input[name="confirm"]');

            if (!typed || typed.value !== 'DELETE') {
                event.preventDefault();
                window.alert('Type DELETE exactly to confirm.');
                return;
            }

            if (!window.confirm('Permanently delete this content and related records?')) {
                event.preventDefault();
            }
        });
    });
});
