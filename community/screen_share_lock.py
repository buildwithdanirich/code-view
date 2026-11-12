"""
PostgreSQL advisory locks for CodeView screen sharing.

Purpose:
- Prevent simultaneous screen-sharing permission operations.
- Coordinate multiple Django workers.
- Keep a PostgreSQL lock active during LiveKit operations.
- Release locks when operations finish or fail.

Uses psycopg 3 asynchronous connections.
"""

import logging

from contextlib import asynccontextmanager

import psycopg

from django.core.exceptions import ValidationError
from django.db import connections


logger = logging.getLogger(__name__)


# PostgreSQL advisory-lock namespace.
LOCK_NAMESPACE = 726431

# PostgreSQL advisory-lock keys use signed 32-bit integers.
MAX_MEETING_ID = 2147483647


# ============================================================
# 1. VALIDATE MEETING ID
# ============================================================

def _validate_meeting_id(meeting_id):
    """
    Validate the meeting ID before acquiring its lock.
    """

    if isinstance(meeting_id, bool):
        raise ValidationError("Invalid meeting ID.")

    try:
        meeting_id = int(meeting_id)

    except (TypeError, ValueError, OverflowError):
        raise ValidationError("Invalid meeting ID.")

    if not 0 < meeting_id <= MAX_MEETING_ID:
        raise ValidationError(
            "Meeting ID is outside the supported lock range."
        )

    return meeting_id


# ============================================================
# 2. GET POSTGRESQL CONNECTION PARAMETERS
# ============================================================

def _postgres_connection_params():
    """
    Read PostgreSQL connection settings from Django.

    Django may configure a synchronous cursor factory.

    Since this module creates an independent asynchronous
    connection, that synchronous cursor factory must not
    be passed to psycopg.AsyncConnection.
    """

    connection = connections["default"]

    if connection.vendor != "postgresql":
        raise ValidationError(
            "Screen-sharing locks require PostgreSQL."
        )

    # Copy the parameters to avoid modifying Django's settings.
    params = connection.get_connection_params().copy()

    # Remove Django's synchronous cursor factory.
    #
    # Otherwise, AsyncConnection.cursor() may return
    # django.db.backends.postgresql.base.Cursor instead
    # of psycopg.AsyncCursor.
    params.pop("cursor_factory", None)

    return params


# ============================================================
# 3. ACQUIRE ASYNCHRONOUS POSTGRESQL LOCK
# ============================================================

@asynccontextmanager
async def screen_share_operation_lock(meeting_id):
    """
    Acquire a PostgreSQL advisory lock for one meeting.

    Example:

        async with screen_share_operation_lock(meeting_id):
            await update_livekit_permissions()

    The lock remains active throughout the protected
    asynchronous operation.

    If another connection owns the same lock, the new
    operation is rejected immediately.
    """

    # Step 1: Validate the meeting ID.
    meeting_id = _validate_meeting_id(meeting_id)

    # Step 2: Get the PostgreSQL connection parameters.
    params = _postgres_connection_params()

    # Step 3: Open a dedicated asynchronous connection.
    connection = await psycopg.AsyncConnection.connect(
        **params,
        autocommit=True,
    )

    acquired = False

    try:

        # Step 4: Acquire the advisory lock.
        async with connection.cursor() as cursor:

            await cursor.execute(
                "SELECT pg_try_advisory_lock(%s, %s)",
                (LOCK_NAMESPACE, meeting_id),
            )

            result = await cursor.fetchone()

            acquired = bool(result and result[0])

        if not acquired:
            raise ValidationError(
                "Another screen-sharing operation is in progress."
            )

        logger.info(
            "Screen-sharing lock acquired: meeting=%s",
            meeting_id,
        )

        # Step 5: Run the protected operation.
        yield

    finally:

        # Step 6: Release the lock.
        if acquired:

            try:

                async with connection.cursor() as cursor:

                    await cursor.execute(
                        "SELECT pg_advisory_unlock(%s, %s)",
                        (LOCK_NAMESPACE, meeting_id),
                    )

                    result = await cursor.fetchone()

                    if not result or not result[0]:
                        logger.error(
                            "Advisory lock release was not confirmed: "
                            "meeting=%s",
                            meeting_id,
                        )

            except Exception:

                logger.exception(
                    "Failed to explicitly release advisory lock: "
                    "meeting=%s",
                    meeting_id,
                )

        # Step 7: Close the dedicated connection.
        #
        # PostgreSQL automatically releases any remaining
        # session-level advisory locks when this connection
        # closes.
        await connection.close()

        logger.info(
            "Screen-sharing lock connection closed: meeting=%s",
            meeting_id,
        )