"""
Safely release an approved screen-sharing presenter in CodeView.

Responsibilities:
- Verify the current approved presenter.
- Serialize permission changes using PostgreSQL.
- Confirm that no screen-sharing tracks are active.
- Revoke the presenter's LiveKit screen permissions.
- Restore the meeting creator's permissions.
- Verify LiveKit before releasing the database reservation.

Security:
- Never trust the browser to grant screen-sharing permission.
- Never release the database reservation before verification.
- Keep the reservation blocked when reconciliation fails.
"""

import logging

from asgiref.sync import sync_to_async
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from livekit import api

from .meeting_service import (
    _active_meeting_for_member,
    _credentials,
)

from .models import GroupMeeting

from .screen_share_livekit import (
    NORMAL_SOURCES,
    SCREEN_SOURCES,
    _has_active_screen_track,
    _participant_list,
    _set_publish_sources,
)

from .screen_share_lock import screen_share_operation_lock

from .screen_share_recovery import _can_publish_screen


logger = logging.getLogger(__name__)


# ============================================================
# 1. IDENTIFY THE ACTIVE MEETING
# ============================================================

def _get_release_meeting_id(group_id, user_id):
    """
    Find the active meeting for an authenticated group member.

    The database state will be checked again after acquiring
    the screen-sharing operation lock.
    """

    meeting = _active_meeting_for_member(
        group_id,
        user_id,
    )

    return meeting.pk


# ============================================================
# 2. VERIFY THE CURRENT PRESENTER
# ============================================================

def _get_release_reservation(
    meeting_id,
    user_id,
):
    """
    Verify that the user owns the approved screen-sharing slot.

    Return the information needed for LiveKit reconciliation.
    """

    with transaction.atomic():

        meeting = (
            GroupMeeting.objects
            .select_for_update()
            .get(pk=meeting_id)
        )

        if meeting.status != "active":
            raise ValidationError(
                "The meeting is no longer active."
            )

        if meeting.screen_share_state != "ready":
            raise ValidationError(
                "There is no completed screen-sharing approval "
                "to release."
            )

        if meeting.active_screen_sharer_id != user_id:
            raise PermissionDenied(
                "Only the approved presenter can release "
                "their screen-sharing permission."
            )

        if meeting.started_by_id == user_id:
            raise ValidationError(
                "The meeting creator does not hold a "
                "delegated screen-sharing slot."
            )

        return {
            "meeting_id": meeting.pk,
            "room_name": str(meeting.room_name),
            "creator_id": meeting.started_by_id,
            "presenter_id": meeting.active_screen_sharer_id,
        }


# ============================================================
# 3. FINALIZE THE DATABASE RELEASE
# ============================================================

def _finalize_screen_share_release(
    meeting_id,
    presenter_id,
):
    """
    Release the database reservation after LiveKit verification.

    The database row is locked to prevent conflicting updates.
    """

    with transaction.atomic():

        meeting = (
            GroupMeeting.objects
            .select_for_update()
            .get(pk=meeting_id)
        )

        if meeting.status != "active":
            raise ValidationError(
                "The meeting ended during screen-sharing release."
            )

        if meeting.screen_share_state != "ready":
            raise ValidationError(
                "The screen-sharing state changed during release."
            )

        if meeting.active_screen_sharer_id != presenter_id:
            raise ValidationError(
                "The approved presenter changed during release."
            )

        meeting.active_screen_sharer = None

        meeting.screen_share_state = "idle"

        meeting.save(
            update_fields=[
                "active_screen_sharer",
                "screen_share_state",
            ]
        )

        return {
            "meeting_id": meeting.pk,
            "group_id": meeting.group_id,
            "screen_share_state": meeting.screen_share_state,
            "active_screen_sharer_id": None,
        }


# ============================================================
# 4. VERIFY THE RESTORED PERMISSIONS
# ============================================================

def _verify_restored_permissions(
    participants,
    creator_id,
    presenter_id,
):
    """
    Verify that the creator is the only connected participant
    who can publish screen-sharing tracks.

    The presenter may already have disconnected.
    """

    creator = participants.get(
        str(creator_id)
    )

    if creator is None:
        raise ValidationError(
            "The meeting creator must be connected "
            "before screen-sharing permission can be restored."
        )

    if not _can_publish_screen(creator):
        raise ValidationError(
            "The creator did not receive screen-sharing permission."
        )

    presenter = participants.get(
        str(presenter_id)
    )

    if (
        presenter is not None
        and _can_publish_screen(presenter)
    ):
        raise ValidationError(
            "The presenter still has screen-sharing permission."
        )

    for identity, participant in participants.items():

        if identity == str(creator_id):
            continue

        if _can_publish_screen(participant):
            raise ValidationError(
                "Another participant still has "
                "screen-sharing permission."
            )


# ============================================================
# 5. COORDINATE THE PERMISSION RELEASE
# ============================================================

async def coordinate_screen_share_release(
    group_id,
    user,
):
    """
    Release an approved presenter's screen-sharing slot.

    The caller must be authenticated.

    This operation:
    1. Acquires the meeting operation lock.
    2. Validates the approved presenter.
    3. Checks for active screen tracks.
    4. Revokes presenter screen permission.
    5. Restores creator screen permission.
    6. Verifies LiveKit.
    7. Releases the PostgreSQL reservation.

    Any failure before database finalization leaves the
    screen-sharing reservation blocked.
    """

    # --------------------------------------------------------
    # Step 1. Find the active meeting.
    # --------------------------------------------------------

    meeting_id = await sync_to_async(
        _get_release_meeting_id,
        thread_sensitive=True,
    )(
        group_id,
        user.pk,
    )

    # --------------------------------------------------------
    # Step 2. Serialize screen-sharing operations.
    # --------------------------------------------------------

    async with screen_share_operation_lock(meeting_id):

        # ----------------------------------------------------
        # Step 3. Verify the approved presenter.
        # ----------------------------------------------------

        reservation = await sync_to_async(
            _get_release_reservation,
            thread_sensitive=True,
        )(
            meeting_id,
            user.pk,
        )

        room_name = reservation["room_name"]

        creator_id = reservation["creator_id"]

        presenter_id = reservation["presenter_id"]

        try:

            # ------------------------------------------------
            # Step 4. Connect to the LiveKit server.
            # ------------------------------------------------

            url, key, secret = _credentials()

            async with api.LiveKitAPI(
                url,
                key,
                secret,
            ) as client:

                room_client = client.room

                # --------------------------------------------
                # Step 5. Inspect connected participants.
                # --------------------------------------------

                participants = await _participant_list(
                    room_client,
                    room_name,
                )

                # --------------------------------------------
                # Step 6. Confirm sharing has stopped.
                # --------------------------------------------

                if _has_active_screen_track(participants):
                    raise ValidationError(
                        "A screen-sharing track is still active. "
                        "Stop sharing before releasing permission."
                    )

                creator = participants.get(
                    str(creator_id)
                )

                if creator is None:
                    raise ValidationError(
                        "The meeting creator must be connected "
                        "before permission can be restored."
                    )

                # --------------------------------------------
                # Step 7. Revoke presenter permission.
                # --------------------------------------------

                presenter = participants.get(
                    str(presenter_id)
                )

                if presenter is not None:

                    await _set_publish_sources(
                        room_client,
                        room_name,
                        presenter_id,
                        NORMAL_SOURCES,
                    )

                # --------------------------------------------
                # Step 8. Verify presenter revocation.
                # --------------------------------------------

                participants = await _participant_list(
                    room_client,
                    room_name,
                )

                presenter = participants.get(
                    str(presenter_id)
                )

                if (
                    presenter is not None
                    and _can_publish_screen(presenter)
                ):
                    raise ValidationError(
                        "Presenter permission revocation "
                        "could not be verified."
                    )

                if _has_active_screen_track(participants):
                    raise ValidationError(
                        "Screen sharing restarted during release."
                    )

                # --------------------------------------------
                # Step 9. Restore creator permission.
                # --------------------------------------------

                if str(creator_id) not in participants:
                    raise ValidationError(
                        "The meeting creator disconnected "
                        "during permission restoration."
                    )

                await _set_publish_sources(
                    room_client,
                    room_name,
                    creator_id,
                    SCREEN_SOURCES,
                )

                # --------------------------------------------
                # Step 10. Verify the final LiveKit state.
                # --------------------------------------------

                participants = await _participant_list(
                    room_client,
                    room_name,
                )

                if _has_active_screen_track(participants):
                    raise ValidationError(
                        "An unexpected screen-sharing track "
                        "appeared during permission restoration."
                    )

                _verify_restored_permissions(
                    participants,
                    creator_id,
                    presenter_id,
                )

            # ------------------------------------------------
            # Step 11. Release the database reservation.
            # ------------------------------------------------

            result = await sync_to_async(
                _finalize_screen_share_release,
                thread_sensitive=True,
            )(
                meeting_id,
                presenter_id,
            )

        except Exception:

            logger.exception(
                "Screen-sharing release failed: "
                "meeting=%s presenter=%s",
                meeting_id,
                presenter_id,
            )

            # Do not clear the reservation.
            #
            # LiveKit may have applied a permission change
            # even if the request subsequently failed.
            #
            # A reconciliation operation must verify
            # permissions before the slot is reused.

            raise

    logger.info(
        "Screen-sharing permission released: "
        "meeting=%s presenter=%s",
        meeting_id,
        presenter_id,
    )

    return result