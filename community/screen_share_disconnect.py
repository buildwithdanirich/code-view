"""
Recover screen-sharing permission after an unexpected disconnect.

This module handles approved presenters who disconnect while
a meeting is in the "ready" screen-sharing state.

It does not replace recovery of interrupted approvals.

Security:
- Uses the existing PostgreSQL advisory lock.
- Rechecks the meeting's current database state.
- Inspects LiveKit before changing permissions.
- Rejects stale disconnect events.
- Does not restore permissions if the presenter reconnected.
- Verifies LiveKit permissions before updating the database.
- Fails closed when the result cannot be verified.

Important:
This coordinator is one part of reconnect security.
LiveKit token issuance and reconnection enforcement must
also be secured before production deployment.
"""

import logging

from asgiref.sync import sync_to_async
from django.core.exceptions import ValidationError
from django.db import transaction
from livekit import api

from .meeting_service import _credentials
from .models import GroupMeeting
from .screen_share_lock import screen_share_operation_lock

from .screen_share_recovery import (
    NORMAL_SOURCES,
    SCREEN_SOURCES,
    _can_publish_screen,
    _has_screen_track,
    _list_participants,
    _update_permission,
)


logger = logging.getLogger(__name__)


# ============================================================
# 1. READ CURRENT MEETING STATE
# ============================================================

def _get_disconnect_snapshot(meeting_id, presenter_identity):
    """
    Read the current meeting state.

    Only an active meeting with an approved presenter
    is eligible for disconnect recovery.

    Return None when the event is no longer relevant.
    """

    meeting = (
        GroupMeeting.objects
        .filter(pk=meeting_id)
        .first()
    )

    if meeting is None:
        return None

    if meeting.status != "active":
        return None

    if meeting.screen_share_state != "ready":
        return None

    if meeting.active_screen_sharer_id is None:
        return None

    # A webhook for a different developer must never
    # change the current presenter's permission.
    if (
        str(meeting.active_screen_sharer_id)
        != str(presenter_identity)
    ):
        return None

    return {
        "meeting_id": meeting.pk,
        "room_name": str(meeting.room_name),
        "creator_id": meeting.started_by_id,
        "presenter_id": meeting.active_screen_sharer_id,
    }


# ============================================================
# 2. VERIFY THE ROOM'S CURRENT STATE
# ============================================================

def _verify_presenter_disconnected(
    participants,
    presenter_identity,
):
    """
    Confirm that the approved presenter is not connected.

    An old participant_left webhook may arrive after
    the developer has already reconnected.

    If the identity is present, recovery must stop.
    """

    return str(presenter_identity) not in participants


def _verify_no_active_screen_sharing(participants):
    """
    Ensure no connected participant is publishing
    a screen-sharing track.
    """

    return not any(
        _has_screen_track(participant)
        for participant in participants.values()
    )


def _verify_only_creator_can_share(
    participants,
    creator_identity,
):
    """
    Verify that only the meeting creator has
    screen-sharing publishing permission.
    """

    creator = participants.get(
        str(creator_identity)
    )

    if creator is None:
        return False

    if not _can_publish_screen(creator):
        return False

    for identity, participant in participants.items():

        if identity == str(creator_identity):
            continue

        if _can_publish_screen(participant):
            return False

    return True


# ============================================================
# 3. RESTORE DATABASE STATE
# ============================================================

def _complete_disconnect_recovery(snapshot):
    """
    Clear the approved presenter after LiveKit
    permission verification succeeds.

    The meeting operation advisory lock must already
    be held by the caller.

    Row locking protects the final database update.
    """

    with transaction.atomic():

        meeting = (
            GroupMeeting.objects
            .select_for_update()
            .get(pk=snapshot["meeting_id"])
        )

        if meeting.status != "active":
            raise ValidationError(
                "The meeting ended during disconnect recovery."
            )

        if meeting.screen_share_state != "ready":
            raise ValidationError(
                "Screen-sharing state changed during recovery."
            )

        if (
            meeting.active_screen_sharer_id
            != snapshot["presenter_id"]
        ):
            raise ValidationError(
                "The approved presenter changed during recovery."
            )

        if meeting.started_by_id != snapshot["creator_id"]:
            raise ValidationError(
                "The meeting creator changed during recovery."
            )

        if str(meeting.room_name) != snapshot["room_name"]:
            raise ValidationError(
                "The LiveKit room changed during recovery."
            )

        # Release the approved presenter.
        meeting.active_screen_sharer = None

        # Return the meeting to its normal sharing state.
        meeting.screen_share_state = "idle"

        meeting.save(
            update_fields=[
                "active_screen_sharer",
                "screen_share_state",
            ]
        )

        return meeting


# ============================================================
# 4. RECOVER UNEXPECTED PRESENTER DISCONNECTION
# ============================================================

async def recover_disconnected_screen_presenter(
    meeting_id,
    presenter_identity,
    participant_sid=None,
):
    """
    Recover screen-sharing permission when an approved
    presenter unexpectedly leaves a LiveKit meeting.

    Workflow:

    1. Acquire the meeting's PostgreSQL advisory lock.
    2. Read the current approved presenter.
    3. Inspect connected LiveKit participants.
    4. Ignore the event if the presenter reconnected.
    5. Verify that nobody is sharing their screen.
    6. Restore the creator's LiveKit permission.
    7. Verify the resulting LiveKit state.
    8. Recheck the presenter is still disconnected.
    9. Clear the database reservation.

    This function must be called only after the webhook
    signature has been verified.
    """

    if not presenter_identity:
        raise ValidationError(
            "A presenter identity is required."
        )

    # --------------------------------------------------------
    # STEP 1: ACQUIRE MEETING OPERATION LOCK
    # --------------------------------------------------------

    async with screen_share_operation_lock(meeting_id):

        # ----------------------------------------------------
        # STEP 2: READ CURRENT MEETING STATE
        # ----------------------------------------------------

        snapshot = await sync_to_async(
            _get_disconnect_snapshot,
            thread_sensitive=True,
        )(
            meeting_id,
            presenter_identity,
        )

        if snapshot is None:
            return {
                "success": True,
                "recovered": False,
                "reason": "Event is no longer applicable.",
            }

        room_name = snapshot["room_name"]

        creator_identity = str(
            snapshot["creator_id"]
        )

        presenter_identity = str(
            snapshot["presenter_id"]
        )

        if creator_identity == presenter_identity:
            raise ValidationError(
                "The creator cannot be the approved presenter."
            )

        url, key, secret = _credentials()

        try:

            # ------------------------------------------------
            # STEP 3: CONNECT TO LIVEKIT
            # ------------------------------------------------

            async with api.LiveKitAPI(
                url,
                key,
                secret,
            ) as client:

                room_client = client.room

                participants = await _list_participants(
                    room_client,
                    room_name,
                )

                # --------------------------------------------
                # STEP 4: CHECK FOR RECONNECTION
                # --------------------------------------------

                if not _verify_presenter_disconnected(
                    participants,
                    presenter_identity,
                ):

                    logger.info(
                        "Skipping disconnect recovery: "
                        "presenter is connected. "
                        "meeting=%s presenter=%s sid=%s",
                        meeting_id,
                        presenter_identity,
                        participant_sid,
                    )

                    return {
                        "success": True,
                        "recovered": False,
                        "reason": "Presenter is connected.",
                    }

                # --------------------------------------------
                # STEP 5: VERIFY THE CREATOR IS CONNECTED
                # --------------------------------------------

                creator = participants.get(
                    creator_identity
                )

                if creator is None:
                    raise ValidationError(
                        "The meeting creator must be connected "
                        "before permission can be restored."
                    )

                # --------------------------------------------
                # STEP 6: CHECK ACTIVE SCREEN TRACKS
                # --------------------------------------------

                if not _verify_no_active_screen_sharing(
                    participants,
                ):
                    raise ValidationError(
                        "Another screen-sharing track is active."
                    )

                # --------------------------------------------
                # STEP 7: RESTORE CREATOR PERMISSION
                # --------------------------------------------

                await _update_permission(
                    room_client,
                    room_name,
                    creator_identity,
                    SCREEN_SOURCES,
                )

                # --------------------------------------------
                # STEP 8: VERIFY LIVEKIT PERMISSIONS
                # --------------------------------------------

                participants = await _list_participants(
                    room_client,
                    room_name,
                )

                # The presenter may have reconnected while
                # the LiveKit permission update was running.
                if not _verify_presenter_disconnected(
                    participants,
                    presenter_identity,
                ):
                    raise ValidationError(
                        "The presenter reconnected during recovery."
                    )

                if not _verify_no_active_screen_sharing(
                    participants,
                ):
                    raise ValidationError(
                        "Screen sharing started during recovery."
                    )

                if not _verify_only_creator_can_share(
                    participants,
                    creator_identity,
                ):
                    raise ValidationError(
                        "LiveKit publishing permissions "
                        "could not be verified."
                    )

                # --------------------------------------------
                # STEP 9: RECHECK CURRENT PARTICIPANTS
                # --------------------------------------------

                participants = await _list_participants(
                    room_client,
                    room_name,
                )

                if not _verify_presenter_disconnected(
                    participants,
                    presenter_identity,
                ):
                    raise ValidationError(
                        "Presenter reconnected before completion."
                    )

                if not _verify_no_active_screen_sharing(
                    participants,
                ):
                    raise ValidationError(
                        "Screen sharing resumed before completion."
                    )

                if not _verify_only_creator_can_share(
                    participants,
                    creator_identity,
                ):
                    raise ValidationError(
                        "Final LiveKit permission verification failed."
                    )

            # ------------------------------------------------
            # STEP 10: UPDATE DATABASE
            # ------------------------------------------------

            # The advisory lock remains held here.
            meeting = await sync_to_async(
                _complete_disconnect_recovery,
                thread_sensitive=True,
            )(snapshot)

            logger.info(
                "Disconnected screen presenter recovered: "
                "meeting=%s presenter=%s sid=%s",
                meeting_id,
                presenter_identity,
                participant_sid,
            )

            return {
                "success": True,
                "recovered": True,
                "meeting_id": meeting.pk,
                "screen_share_state": meeting.screen_share_state,
            }

        except Exception:

            # Do not clear the database reservation when
            # LiveKit permission state is uncertain.
            #
            # The creator may already have received permission
            # before a later verification failed.
            #
            # A subsequent recovery or reconciliation operation
            # must inspect the actual LiveKit state.

            logger.exception(
                "Disconnected presenter recovery failed: "
                "meeting=%s presenter=%s",
                meeting_id,
                presenter_identity,
            )

            raise