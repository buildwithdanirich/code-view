"""Email utilities for ColabVerse account verification and recovery."""

from django.conf import settings
from django.core.mail import EmailMessage, get_connection


def send_account_email(subject, body, recipient):
    """
    Send ColabVerse account emails.

    Used for:
    - Email verification.
    - Password recovery.
    - Future account notifications.

    Django uses the MAILERS configuration in settings.py.
    """

    # Get Django's configured email connection.
    connection = get_connection()

    # Use the sender identity configured in settings.py.
    sender = settings.CODEVIEW_EMAIL_FROM

    # Create the email with ColabVerse as the sender.
    email = EmailMessage(
        subject=subject,
        body=body,
        from_email=sender,
        to=[recipient],
        connection=connection,
    )

    # Send the email and raise an exception if delivery fails.
    return email.send(fail_silently=False)