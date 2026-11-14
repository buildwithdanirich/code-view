"""Email transport configured through environment variables; no secrets in code."""
import os
from django.conf import settings
from django.core.mail import EmailMessage, get_connection
from django.core.exceptions import ImproperlyConfigured


def send_account_email(subject, body, recipient):
    backend = os.environ.get("CODEVIEW_EMAIL_BACKEND", "")
    if not backend:
        if not settings.DEBUG:
            raise ImproperlyConfigured("Configure CODEVIEW_EMAIL_BACKEND for production email.")
        backend = "django.core.mail.backends.console.EmailBackend"
    options = {"backend": backend}
    if backend == "django.core.mail.backends.smtp.EmailBackend":
        options.update({
            "host": os.environ.get("CODEVIEW_EMAIL_HOST", ""),
            "port": int(os.environ.get("CODEVIEW_EMAIL_PORT", "587")),
            "username": os.environ.get("CODEVIEW_EMAIL_USER", ""),
            "password": os.environ.get("CODEVIEW_EMAIL_PASSWORD", ""),
            "use_tls": os.environ.get("CODEVIEW_EMAIL_USE_TLS", "true").lower() == "true",
            "use_ssl": os.environ.get("CODEVIEW_EMAIL_USE_SSL", "false").lower() == "true",
            "timeout": 15,
        })
    connection = get_connection(**options)
    sender = os.environ.get("CODEVIEW_EMAIL_FROM", "CodeView <no-reply@localhost>")
    EmailMessage(subject, body, sender, [recipient], connection=connection).send(fail_silently=False)
