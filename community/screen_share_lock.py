"""
PostgreSQL advisory locking for CodeView screen-sharing operations.

Purpose:
- Prevent concurrent approval and recovery operations.
- Coordinate multiple Django workers.
- Avoid holding a database transaction open during LiveKit calls.

Important:
Every screen-sharing permission-changing operation must use
this lock for the protection to work.
"""

from contextlib import contextmanager

from django.core.exceptions import ValidationError
from django.db import connections


# A dedicated namespace for CodeView screen-sharing locks.
# The meeting ID is used as the second advisory-lock key.
LOCK_NAMESPACE = 726431


@contextmanager
def screen_share_operation_lock(meeting_id):
    """
    Acquire a PostgreSQL session-level advisory lock.

    The lock is held until the context manager exits.

    Example:

        with screen_share_operation_lock(meeting_id):
            # Perform one screen-sharing operation.
            pass

    This function is synchronous. Do not call it directly
    from an asynchronous Django view.
    """

    meeting_id = int(meeting_id)

    if meeting_id <= 0 or meeting_id > 2147483647:
        raise ValidationError(
            "Invalid meeting ID for screen-sharing lock."
        )

    connection = connections["default"]

    if connection.vendor != "postgresql":
        raise ValidationError(
            "Screen-sharing locks require PostgreSQL."
        )

    # Open the database connection before acquiring the lock.
    connection.ensure_connection()

    # Acquire the lock without waiting.
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_try_advisory_lock(%s, %s)",
            [LOCK_NAMESPACE, meeting_id],
        )

        acquired = cursor.fetchone()[0]

    if not acquired:
        raise ValidationError(
            "Another screen-sharing operation is in progress."
        )

    try:
        yield

    finally:
        # Release the advisory lock using the same
        # PostgreSQL database connection.
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_advisory_unlock(%s, %s)",
                [LOCK_NAMESPACE, meeting_id],
            )

            released = cursor.fetchone()[0]

        if not released:
            raise RuntimeError(
                "Screen-sharing advisory lock was not released."
            )