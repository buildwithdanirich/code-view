# CodeView V1

Independent Django-based developer collaboration platform. This project does **not** include a browser IDE, Docker, sandboxes, runners, code execution, or a Code Board.

## Existing modules

- User registration and login
- Public, approval-required and private development groups
- Membership requests, discussions, chat and attachments
- Read-only GitHub repository connection and browser (requires security and browser verification)
- Meeting-room UI (real-time video, screen sharing and capacity enforcement require verification and further implementation)

Private development groups target **15 people including the owner**. Meeting capacity remains **10 concurrent participants initially**.

## Fresh installation

1. Create a **new empty PostgreSQL database** dedicated to V1. Never point this project at the original CodeView database.
2. Keep your existing `.env` outside the ZIP, with `DJANGO_SECRET_KEY`, `CODEVIEW_DB_PASSWORD`, and the V1 database name/user.
3. Install dependencies: `python3 -m pip install -r requirements.txt`.
4. Generate new migrations: `python3 manage.py makemigrations`.
5. Apply migrations: `python3 manage.py migrate`.
6. Run checks: `python3 manage.py check`.
7. Start: `python3 -m daphne -b 127.0.0.1 -p 8000 config.asgi:application`.

**Do not use this fresh migration history against the existing migrated database.** Reset/create a separate empty database first. The old migration files are intentionally excluded, while migration package `__init__.py` files are retained. Django will generate new initial migrations from the current models.

## Next phases

1. Cleanup and fresh database verification
2. Groups, membership and permissions
3. GitHub authorization and repository browser verification
4. Chat and attachments
5. WebRTC meetings and screen sharing
6. Collaborative whiteboard
7. Security and deployment

Production readiness is **not yet established**. In particular, use Redis-backed Channels and a TURN/SFU strategy for production meetings, review file access controls, and remove or rotate any credentials that were previously shared in documentation.
