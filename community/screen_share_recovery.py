"""
Recovery for interrupted CodeView screen-sharing approvals.

Purpose:
- Inspect incomplete screen-sharing approvals.
- Revoke temporary LiveKit screen-sharing permissions.
- Restore the meeting creator's permission when safe.
- Release the database slot only after verification.

Security:
- Recovery fails closed.
- Uncertain operations remain blocked.
- This module does not automatically run recovery.
- Reconnection protection must be completed separately.
"""

import logging

from asgiref.sync import sync_to_async

from django.core.exceptions import ValidationError
from django.db import transaction

from livekit import api

from .meeting_service import _credentials

from .models import GroupMeeting


logger = logging.getLogger(__name__)


# ============================================================
# 1. LIVEKIT PUBLISHING PERMISSIONS
# ============================================================

NORMAL_SOURCES = [
    "microphone",
    "camera",
]

SCREEN_SOURCES = [
    "microphone",
    "camera",
    "screen_share",
    "screen_share_audio",
]


def _permission(sources):
    """
    Build LiveKit participant permissions.

    A participant can continue using their microphone
    and camera even when screen sharing is disabled.
    """

    return api.ParticipantPermission(
        can_subscribe=True,
        can_publish=True,
        can_publish_data=True,
        can_publish_sources=sources,
    )


# ============================================================
# 2. READ THE INCOMPLETE APPROVAL
# ============================================================

def _get_recovery_snapshot(meeting_id):
    """
    Read the current meeting state.

    Only interrupted approvals in the 'granting'
    state are handled by this recovery operation.
    """

    meeting = (
        GroupMeeting.objects
        .get(pk=meeting_id)
    )

    if meeting.status != "active":
        raise ValidationError(
            "Recovery requires an active meeting."
        )

    if meeting.screen_share_state != "granting":
        raise ValidationError(
            "The meeting is not awaiting approval recovery."
        )

    if meeting.active_screen_sharer_id is None:
        raise ValidationError(
            "The incomplete approval has no presenter."
        )

    return {
        "meeting_id": meeting.pk,
        "room_name": str(meeting.room_name),
        "creator_id": meeting.started_by_id,
        "presenter_id": meeting.active_screen_sharer_id,
    }


# ============================================================
# 3. INSPECT LIVEKIT PARTICIPANTS
# ============================================================

async def _list_participants(room_client, room_name):
    """
    Get the current participants from LiveKit.

    Returns participants indexed by their identity.
    """

    response = await room_client.list_participants(
        api.ListParticipantsRequest(
            room=room_name,
        )
    )

    return {
        participant.identity: participant
        for participant in response.participants
    }


def _has_screen_track(participant):
    """
    Check whether a participant is publishing
    a screen-sharing track.
    """

    screen_sources = {
        api.TrackSource.SCREEN_SHARE,
        api.TrackSource.SCREEN_SHARE_AUDIO,
    }

    return any(
        track.source in screen_sources
        for track in participant.tracks
    )


def _can_publish_screen(participant):
    """
    Check whether LiveKit reports screen-publishing
    permission for a participant.

    An unrestricted publishing permission also
    counts as screen-sharing permission.
    """

    permission = participant.permission

    if permission is None:
        return True

    if not permission.can_publish:
        return False

    sources = set(permission.can_publish_sources)

    # An empty source restriction means publishing
    # is not restricted to specific track sources.
    if not sources:
        return True

    return bool(
        {
            api.TrackSource.SCREEN_SHARE,
            api.TrackSource.SCREEN_SHARE_AUDIO,
        }.intersection(sources)
    )


# ============================================================
# 4. UPDATE PARTICIPANT PERMISSIONS
# ============================================================

async def _update_permission(
    room_client,
    room_name,
    identity,
    sources,
):
    """
    Update an existing LiveKit participant.

    This does not disconnect the participant.
    """

    await room_client.update_participant(
        api.UpdateParticipantRequest(
            room=room_name,
            identity=str(identity),
            permission=_permission(sources),
        )
    )


# ============================================================
# 5. RELEASE THE DATABASE RESERVATION
# ============================================================

def _release_recovered_slot(snapshot):
    """
    Release the reserved slot after LiveKit verification.

    Lock the meeting row to avoid overwriting another
    database transition.
    """

    with transaction.atomic():

        meeting = (
            GroupMeeting.objects
            .select_for_update()
            .get(pk=snapshot["meeting_id"])
        )

        if meeting.status != "active":
            raise ValidationError(
                "The meeting ended during recovery."
            )

        if meeting.screen_share_state != "granting":
            raise ValidationError(
                "The screen-sharing state changed during recovery."
            )

        if (
            meeting.active_screen_sharer_id
            != snapshot["presenter_id"]
        ):
            raise ValidationError(
                "The reserved presenter changed during recovery."
            )

        meeting.active_screen_sharer = None
        meeting.screen_share_state = "idle"

        meeting.save(
            update_fields=[
                "active_screen_sharer",
                "screen_share_state",
            ]
        )

        return meeting


# ============================================================
# 6. RECOVER INTERRUPTED APPROVAL
# ============================================================

async def recover_screen_share_approval(meeting_id):
    """
    Attempt to recover an interrupted approval.

    Recovery order:

    1. Read the database reservation.
    2. Inspect LiveKit participants.
    3. Revoke the presenter's screen permission.
    4. Verify the presenter no longer has permission.
    5. Restore the creator's screen permission.
    6. Verify the resulting LiveKit state.
    7. Release the PostgreSQL reservation.

    This operation intentionally requires both participants
    to remain connected.

    If either participant is missing or any operation fails,
    the database reservation remains blocked.

    IMPORTANT:
    This is a recovery building block, not a complete
    production recovery system. It must not be invoked
    concurrently with approval or another recovery attempt.
    """

    snapshot = await sync_to_async(
        _get_recovery_snapshot,
        thread_sensitive=True,
    )(meeting_id)

    url, key, secret = _credentials()

    room_name = snapshot["room_name"]

    creator_identity = str(snapshot["creator_id"])
    presenter_identity = str(snapshot["presenter_id"])

    try:

        async with api.LiveKitAPI(
            url,
            key,
            secret,
        ) as client:

            room_client = client.room

            # --------------------------------------------
            # Step 1: Inspect current participants.
            # --------------------------------------------

            participants = await _list_participants(
                room_client,
                room_name,
            )

            creator = participants.get(
                creator_identity
            )

            presenter = participants.get(
                presenter_identity
            )

            if creator is None or presenter is None:
                raise ValidationError(
                    "Both participants must be connected for this recovery operation."
                )

            # --------------------------------------------
            # Step 2: Check existing screen tracks.
            # --------------------------------------------

            if any(
                _has_screen_track(participant)
                for participant in participants.values()
            ):
                raise ValidationError(
                    "Screen sharing must stop before recovery."
                )

            # --------------------------------------------
            # Step 3: Revoke presenter permission.
            # --------------------------------------------

            await _update_permission(
                room_client,
                room_name,
                presenter_identity,
                NORMAL_SOURCES,
            )

            # --------------------------------------------
            # Step 4: Verify presenter revocation.
            # --------------------------------------------

            participants = await _list_participants(
                room_client,
                room_name,
            )

            presenter = participants.get(
                presenter_identity
            )

            if presenter is None:
                raise ValidationError(
                    "Presenter disconnected during recovery."
                )

            if _can_publish_screen(presenter):
                raise ValidationError(
                    "Presenter screen permission was not revoked."
                )

            # --------------------------------------------
            # Step 5: Restore creator permission.
            # --------------------------------------------

            creator = participants.get(
                creator_identity
            )

            if creator is None:
                raise ValidationError(
                    "Creator disconnected during recovery."
                )

            await _update_permission(
                room_client,
                room_name,
                creator_identity,
                SCREEN_SOURCES,
            )

            # --------------------------------------------
            # Step 6: Verify final LiveKit permissions.
            # --------------------------------------------

            participants = await _list_participants(
                room_client,
                room_name,
            )

            creator = participants.get(
                creator_identity
            )

            presenter = participants.get(
                presenter_identity
            )

            if creator is None or presenter is None:
                raise ValidationError(
                    "A participant disconnected during verification."
                )

            if not _can_publish_screen(creator):
                raise ValidationError(
                    "Creator permission was not restored."
                )

            if _can_publish_screen(presenter):
                raise ValidationError(
                    "Presenter still has screen-sharing permission."
                )

            # Other connected participants must not have
            # screen-sharing permission either.
            for identity, participant in participants.items():

                if identity == creator_identity:
                    continue

                if _can_publish_screen(participant):
                    raise ValidationError(
                        "Another participant has screen-sharing permission."
                    )

            if any(
                _has_screen_track(participant)
                for participant in participants.values()
            ):
                raise ValidationError(
                    "A screen track appeared during recovery."
                )

        # --------------------------------------------
        # Step 7: Release the database reservation.
        # --------------------------------------------

        meeting = await sync_to_async(
            _release_recovered_slot,
            thread_sensitive=True,
        )(snapshot)

        logger.info(
            "Screen-sharing recovery completed: meeting=%s",
            meeting_id,
        )

        return {
            "success": True,
            "meeting_id": meeting.pk,
            "screen_share_state": meeting.screen_share_state,
        }

    except Exception:

        # Never clear the reservation when recovery
        # cannot verify a safe LiveKit state.
        logger.exception(
            "Screen-sharing recovery failed: meeting=%s",
            meeting_id,
        )

        raise