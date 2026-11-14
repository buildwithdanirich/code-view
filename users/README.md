# CodeView users app

Drop this `users/` folder into the existing Django project. Existing `register`, `login`, and `logout` URL names are preserved. No migrations are needed; this app uses the existing Django User table.

## Email settings (environment variables)

For local development with `DEBUG=True`, emails are printed in the `runserver` terminal by default. Copy the verification/reset URL from that terminal to test the flow.

For real emails, configure a provider's SMTP details in your shell or private `.env` (never commit it):

- `CODEVIEW_EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend`
- `CODEVIEW_EMAIL_HOST` (your SMTP server)
- `CODEVIEW_EMAIL_PORT=587`
- `CODEVIEW_EMAIL_USER` (SMTP username)
- `CODEVIEW_EMAIL_PASSWORD` (SMTP password)
- `CODEVIEW_EMAIL_FROM` (verified sender address)
- `CODEVIEW_EMAIL_USE_TLS=true`
- `CODEVIEW_EMAIL_USE_SSL=false`

Set `CODEVIEW_EMAIL_USE_TLS=false` and `CODEVIEW_EMAIL_USE_SSL=true` only when using an SSL SMTP port (commonly 465). Production refuses to send signup emails without an explicitly configured backend. Set `DEBUG=False`, HTTPS, secure cookies, and appropriate host settings before deployment.

## Behavior

- New accounts start inactive and require email verification.
- Existing accounts remain unchanged.
- Users can sign in with username or unambiguous email.
- Password reset links expire according to Django's `PASSWORD_RESET_TIMEOUT` (default 3 days).
- GitHub/Google OAuth are **not included**: these require provider configuration and an additional integration.
- The home page is not included; existing redirects to `groups` remain in place.

## Test

`python3 manage.py check`

`python3 manage.py test users`

`python3 manage.py runserver`

Check `/register/`, `/login/`, `/forgot-password/`. Test verification and reset from the terminal's console emails.
