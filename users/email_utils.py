"""Email utilities for CodeView account verification."""

import os

from django.core.mail import EmailMessage, get_connection


def send_account_email(subject, body, recipient):
    """
    Send verification and password-reset emails.

    Django 6.1 uses the MAILERS configuration in settings.py.
    """

    # Get the default email connection from Django settings.
    # Do not pass a backend name or alias here.
    connection = get_connection()

    # Get the sender address from the environment.
    sender = os.environ.get(
        "CODEVIEW_EMAIL_FROM",
        "CodeView <no-reply@localhost>",
    )

    # Create the email.
    email = EmailMessage(
        subject=subject,
        body=body,
        from_email=sender,
        to=[recipient],
        connection=connection,
    )

    # Send the email and report any delivery errors.
    return email.send(fail_silently=False)