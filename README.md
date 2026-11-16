# ColabVerse Admin Dashboard — expanded edition

An independent Django app providing an admin-only control panel at `/admin/`.

## Features

- Overview: users, active users, groups, memberships, meetings, questions, answers/comments, open reports, support queue and recent admin activity.
- Users: search, paginate, activate/deactivate accounts (superuser-only).
- Communities & groups: searchable, paginated **read-only** list of `community.ProjectGroup` records.
- Questions and answers: searchable questions, paginated comments/answers, superuser-only permanent deletion with typed confirmation. **Deletion can cascade**; back up data first.
- Meetings: paginated meeting history and status filters (read-only, not live LiveKit participant telemetry).
- Reports: moderation queue and status updates for the included `ContentReport` model.
- Help & Support: ticket queue, statuses and admin replies for the included `SupportTicket` model.
- Health: PostgreSQL, cache (opt-in), disk, CPU and RAM (requires psutil), LiveKit marked unconfigured until a real service probe is implemented.
- Security: audit trail for admin changes made **through this app** (not a full login/error monitoring system).

## Install / replace existing version

**Back up your current project and database first.** This archive contains a full replacement `colabverse_admin/` directory, not the entire ColabVerse project.

From the `code-view` project directory, extract this ZIP. If replacing the earlier admin app, back it up first:

```bash
cp -a colabverse_admin colabverse_admin_backup
unzip -o ~/Downloads/colabverse_admin_complete.zip -d .
```

In `config/settings.py`, ensure `INSTALLED_APPS` includes:

```python
'colabverse_admin.apps.ColabverseAdminConfig',
```

In `config/urls.py`, ensure `include` is imported and only **one** `admin/` route exists:

```python
path('admin/', include('colabverse_admin.urls')),
```

If Django's built-in admin is needed, move its existing route to another path (e.g. `django-admin/`) rather than leaving two identical `admin/` paths. Protect it appropriately in production.

Run:

```bash
python3 manage.py check
python3 manage.py makemigrations --check --dry-run colabverse_admin
python3 manage.py migrate
python3 manage.py runserver
```

The included migration creates three new tables: content reports, support tickets, and admin audit logs. **Do not run `makemigrations` unless the check shows a mismatch; investigate the mismatch first.**

Create a privileged administrator if needed:

```bash
python3 manage.py createsuperuser
```

Visit `/admin/`. Unauthenticated users are redirected to `/login/` and staff-only access is enforced server-side. Superuser credentials are standard Django hashed-password credentials. A **dedicated admin login page is not included**; the existing site login is reused.

## Deployment notes

- Use HTTPS, secure session/CSRF cookies, `DEBUG=False`, correct `ALLOWED_HOSTS`, a strong `SECRET_KEY`, and a production WSGI/ASGI server.
- Serve static assets with your normal production static-file pipeline (`collectstatic`); do not use Django's development server in production.
- Avoid exposing admin endpoints publicly without additional controls such as rate limiting, MFA, and network restrictions.
- All state changes use POST, CSRF protection, and superuser checks; audit logs record the changes handled by this app.
- Pagination limits large lists to 20 items. Database health checks run on demand; do not poll them too frequently.
- The existing `questions.Comment` model is treated as the answer model, matching the supplied ColabVerse project snapshot.
- **User-facing support submission, content reporting, LiveKit health, active participant counts, and community moderation actions are not wired into the existing apps.** Integrate them later rather than assuming they already work.
- No new third-party dependencies are required. `psutil` is optional for CPU and RAM stats.

## Validation

Run `python3 manage.py check` and `python3 manage.py test colabverse_admin` against your actual project environment. The packaged app has been syntax-checked but cannot be verified against your live database from here.
