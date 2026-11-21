# ColabVerse source review and changes

This package is based on the uploaded `ColabVerse_Review.zip` (262 archive entries). It is **not** a verified production deployment.

## Changes made
- Added Render Blueprint (`render.yaml`) and build script (`build.sh`), with Daphne ASGI startup and manual environment-secret placeholders.
- Changed `config/settings.py` to accept Supabase `DATABASE_URL`, use Upstash `REDIS_URL` for Channels, and configure WhiteNoise for static assets.
- Added production Supabase Storage backend for public avatars and private group attachments, preserving local storage in development.
- Added `AllowedHostsOriginValidator` around WebSocket authentication in `config/asgi.py`.
- Added GitHub App PEM text environment-variable support with local path fallback.
- Corrected misplaced `ProjectGroup.clean()`, `save()`, and `__str__()` method indentation found in the uploaded source.
- Added missing pinned packages to `requirements.txt` (dj-database-url, channels_redis, redis, supabase, storage3, whitenoise).
- Strengthened `.gitignore`, supplied safe `.env.example`, and documented setup, credentials, and manual migration steps.

## Not changed / not claimed fixed
- CSS/design and Google redirect issue are explicitly deferred until the requested next phase.
- No production secrets or real Supabase credentials are included.
- Existing backup files and local user media were excluded from the deliverable ZIP; keep your own backups separately.
- Live network behavior, integration tests, and OAuth callback cannot be verified without running the project in a configured environment.
- No migrations were applied, no Git changes pushed, and no deployment performed.

## Important risks to test
- Render free web services can sleep, breaking long-lived WebSockets.
- Supabase storage backend is newly introduced and requires integration testing with the existing buckets.
- The source archive included a group-model indentation error; verify group creation and membership behavior against existing tests.
- Production mail must be configured; the console backend is not sufficient for real users.
