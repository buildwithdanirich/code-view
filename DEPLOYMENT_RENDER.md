# ColabVerse — Render deployment preparation (not deployed)

## Architecture
One Render **web service** runs Daphne for both Django HTTP and Django Channels WebSockets. Existing managed services remain: **Supabase PostgreSQL**, **Supabase Storage**, **Upstash Redis**, and **LiveKit Cloud**. The Render free plan can spin down after inactivity, disconnecting WebSockets; it is suitable for demos, not guaranteed 24/7 service. Check current free-tier availability before launch.

## Local setup (Ubuntu)

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip build-essential libpq-dev
python3 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cp .env.example .env
# Fill .env privately; never upload it or commit it.
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
python manage.py collectstatic --noinput
# Local test:
daphne -b 127.0.0.1 -p 8000 config.asgi:application
```

Node.js is only needed to **rebuild** the LiveKit JavaScript bundle. The bundle is included. If changing LiveKit JavaScript, use `npm ci` and the project's esbuild workflow; do not rebuild unnecessarily.

## Render Blueprint

`render.yaml` configures a Python web service, runs `bash build.sh`, and starts `daphne -b 0.0.0.0 -p $PORT config.asgi:application`. **Do not create the Blueprint or deploy until approved.** The generated Render hostname might differ from `colabverse.onrender.com`; update both `DJANGO_ALLOWED_HOSTS` and `DJANGO_CSRF_TRUSTED_ORIGINS` to match the actual host.

Render Blueprint `sync: false` values are placeholders for **manual secret entry** when creating the service. Never store actual credentials in `render.yaml` or Git. Confirm availability of these values at build time, as `collectstatic` loads Django settings.

### Secrets and where to put them (Render dashboard → Web Service → Environment)

| Variable | Source | Sensitive? |
| --- | --- | --- |
| `DJANGO_SECRET_KEY` | Render-generated random value (`generateValue`) | YES |
| `DATABASE_URL` | Supabase **PostgreSQL connection string**, preferably transaction pooler, with TLS | YES |
| `REDIS_URL` | Upstash Redis **rediss://** URL | YES |
| `SUPABASE_URL` | Supabase Project URL | Public identifier |
| `SUPABASE_SECRET_KEY` | Supabase server-side secret/service-role key | **YES — server only** |
| `GITHUB_APP_ID` | GitHub App settings | Identifier |
| `GITHUB_APP_PRIVATE_KEY` | **Entire GitHub App PEM private key**; paste in Render Environment, not source files | **YES** |
| `GITHUB_CLIENT_ID` | GitHub OAuth/GitHub App client ID | Identifier |
| `GITHUB_CLIENT_SECRET` | GitHub OAuth/GitHub App client secret | **YES** |
| `CODEVIEW_GOOGLE_CLIENT_ID` | Google Cloud OAuth client | Identifier |
| `CODEVIEW_GOOGLE_CLIENT_SECRET` | Google Cloud OAuth client secret | **YES** |
| `LIVEKIT_URL` | LiveKit Cloud server URL | Identifier |
| `LIVEKIT_API_KEY` | LiveKit Cloud | Identifier |
| `LIVEKIT_API_SECRET` | LiveKit Cloud | **YES** |
| `CODEVIEW_EMAIL_FROM` | Verified sender email address | Not normally secret |
| `CODEVIEW_EMAIL_HOST` | Your email provider SMTP host | Not secret |
| `CODEVIEW_EMAIL_USER` | Email provider SMTP login | Private |
| `CODEVIEW_EMAIL_PASSWORD` | SMTP password/app password | **YES** |

Nonsecret settings in `render.yaml`: `DJANGO_DEBUG=False`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS`, `GITHUB_OAUTH_CALLBACK_URL`, `CODEVIEW_EMAIL_BACKEND`, and email port/TLS flags. Set `SUPABASE_PUBLIC_BUCKET=profile_picture` and `SUPABASE_PRIVATE_BUCKET=group_files` if bucket names differ from defaults.

**Supabase storage**: existing buckets must be named `profile_picture` (**public**) and `group_files` (**private**). The backend uses server credentials only. Uploaded avatars use the public bucket; group chat attachments are downloaded only through existing permission-checked Django views. Validate with real accounts before launch. **Never expose** `SUPABASE_SECRET_KEY` to JavaScript. Render's filesystem is ephemeral, so local file storage must not be used for production uploads.

**Database migration**: `build.sh` deliberately does not run migrations. After reviewing `python manage.py showmigrations` and `python manage.py migrate --plan`, perform a controlled migration using a secure environment connected to the intended Supabase database, with a backup. Do not run `makemigrations` on production. A Render free instance may not provide interactive shell access; you can run the migration from your own terminal with the same production `DATABASE_URL`, after approval.

**Google OAuth**: configure the real HTTPS callback in Google Cloud, typically `https://<host>/accounts/google/login/callback/`. Verify `django.contrib.sites` domain and provider setup after database migration. Do not assume OAuth is fixed merely by adding variables. **User-requested Google redirect bug is a separate pre-deployment phase.**

**GitHub OAuth**: configure the callback `https://<host>/github/callback/` in GitHub's settings. The GitHub App private PEM can be pasted into `GITHUB_APP_PRIVATE_KEY`; local development can continue using `GITHUB_APP_PRIVATE_KEY_PATH`. Do not commit the PEM.

**Email**: the default console backend does not send real verification/reset emails. Configure a real transactional email service. Some free hosts restrict outbound SMTP ports; verify connectivity before launch, or implement an HTTP-based email API provider in the later app-fix phase.

**Custom domain later**: update DNS in Render, `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS`, Google and GitHub callback URLs, and the Django Site domain. Same-origin WebSockets then use the new domain without JS changes.

## Outstanding verification (must be completed before deployment)

1. Install project requirements in a real Python 3.12 virtual environment; run Django system checks, migrations dry-run, tests, and collectstatic. The supplied package was syntax-checked but no live credentials or external services were available to test here.
2. Test real Supabase Storage avatar uploads and **private** group attachment upload/download, access denial, and deletion. Existing files on local disk are not automatically migrated to Supabase.
3. Test WebSocket authorized/unauthorized connections and membership revocation using real Redis and `AllowedHostsOriginValidator`.
4. Review Google sign-in callback/redirect behavior and user-requested CSS changes in the next phase.
5. Confirm free-plan restrictions, email delivery, and domain before launch. Enable HSTS only after HTTPS/domain verification (`DJANGO_HSTS_SECONDS`).
6. Do not commit, push, or deploy without explicit approval.
