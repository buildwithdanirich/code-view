"""LiveKit permission coordination for CodeView screen-sharing approvals.

This is a backend-only integration stage. Do not expose it through an HTTP
endpoint until reconnection, rollback/recovery and concurrency tests pass.
"""

import logging

from asgiref.sync import sync_to_async
from django.core.exceptions import ValidationError
from livekit import api

from .meeting_service import _credentials, _broadcast_screen_request_event
from .screen_share_approval import (
    reserve_screen_share_approval,
    finalize_screen_share_approval,
)

logger = logging.getLogger(__name__)

# Normal camera/microphone publishing remains available to everyone.
NORMAL_SOURCES = ["microphone", "camera"]
SCREEN_SOURCES = NORMAL_SOURCES + ["screen_share", "screen_share_audio"]


def _is_screen_track(track):
    """Check actual published LiveKit track sources, not a UI flag."""
    return track.source in (
        api.TrackSource.SCREEN_SHARE,
        api.TrackSource.SCREEN_SHARE_AUDIO,
    )


async def _participant_list(room_client, room_name):
    result = await room_client.list_participants(
        api.ListParticipantsRequest(room=room_name)
    )
    return {p.identity: p for p in result.participants}


async def _set_publish_sources(room_client, room_name, identity, sources):
    """Update an existing participant's server-side publishing permission."""
    await room_client.update_participant(
        api.UpdateParticipantRequest(
            room=room_name,
            identity=str(identity),
            permission=api.ParticipantPermission(
                can_subscribe=True,
                can_publish=True,
                can_publish_data=True,
                can_publish_sources=sources,
            ),
        )
    )


async def coordinate_screen_share_approval(group_id, creator, request_id):
    """Attempt approval, failing closed if LiveKit and PostgreSQL diverge.

    The creator must be connected and not publishing a screen track. The
    selected member must also be connected. A disconnected participant is
    not approved because updating their LiveKit permissions is impossible.

    This function intentionally has no HTTP route yet.
    """
    url, key, secret = _credentials()

    # Reservation verifies accepted membership, creator authority and a
    # pending request under PostgreSQL row locks.
    reservation = await sync_to_async(
        reserve_screen_share_approval, thread_sensitive=True
    )(group_id, creator.pk, request_id)

    room_name = reservation["room_name"]
    presenter_id = reservation["presenter_id"]
    creator_id = reservation["creator_id"]

    try:
        async with api.LiveKitAPI(url, key, secret) as client:
            room_client = client.room
            participants = await _participant_list(room_client, room_name)
            creator_participant = participants.get(str(creator_id))
            presenter_participant = participants.get(str(presenter_id))

            if creator_participant is None:
                raise ValidationError(
                    "The meeting creator must be connected to approve sharing."
                )
            if presenter_participant is None:
                raise ValidationError(
                    "The requesting member must be connected to receive permission."
                )

            # Check both participants: never approve while either has a
            # published screen track. Other participants are not supposed
            # to have screen permission, but inspect them as defense-in-depth.
            if any(
                _is_screen_track(track)
                for participant in participants.values()
                for track in participant.tracks
            ):
                raise ValidationError(
                    "Someone is currently sharing a screen. Stop sharing first."
                )

            # Revoke creator first. A failure after this point leaves the
            # database in 'granting' for explicit reconciliation.
            await _set_publish_sources(
                room_client, room_name, creator_id, NORMAL_SOURCES
            )
            await _set_publish_sources(
                room_client, room_name, presenter_id, SCREEN_SOURCES
            )

            # A second read catches an obvious race with a newly published
            # track, but is not a substitute for LiveKit webhook enforcement.
            participants = await _participant_list(room_client, room_name)
            if any(
                _is_screen_track(track)
                for identity, participant in participants.items()
                if identity != str(presenter_id)
                for track in participant.tracks
            ):
                raise ValidationError(
                    "Another screen publication was detected during approval."
                )

        screen_request = await sync_to_async(
            finalize_screen_share_approval, thread_sensitive=True
        )(
            reservation["meeting_id"],
            request_id,
            creator_id,
            presenter_id,
        )

    except Exception:
        # Deliberately do NOT set the state back to idle: a LiveKit update
        # may have succeeded even if its response was lost. Recovery must
        # inspect actual participant permissions and tracks before release.
        logger.exception(
            "Screen-share approval requires reconciliation: meeting=%s request=%s",
            reservation["meeting_id"],
            request_id,
        )
        raise

    await _broadcast_screen_request_event(
        screen_request, "screen_share_approved"
    )
    return screen_request