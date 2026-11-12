"""
LiveKit screen-sharing approval coordination for CodeView.

Responsibilities:
- Validate the meeting and creator.
- Acquire the meeting's PostgreSQL advisory lock.
- Reserve the screen-sharing slot.
- Verify LiveKit participants and published tracks.
- Revoke the creator's screen-sharing permission.
- Grant the approved member screen-sharing permission.
- Finalize approval in PostgreSQL.
- Broadcast the approval event.

Security:
- Only the meeting creator can approve requests.
- Only one cooperating permission operation can run per meeting.
- Approval fails if someone is already sharing.
- Failed operations leave the reservation blocked.
- This module must not be exposed through an HTTP endpoint yet.
"""

import logging

from asgiref.sync import sync_to_async
from django.core.exceptions import ValidationError
from livekit import api

from .meeting_service import (
    _active_meeting_for_member,
    _broadcast_screen_request_event,
    _credentials,
)

from .screen_share_approval import (
    finalize_screen_share_approval,
    reserve_screen_share_approval,
)

from .screen_share_lock import screen_share_operation_lock


logger = logging.getLogger(__name__)


# ============================================================
# 1. LIVEKIT PERMISSION CONFIGURATION
# ============================================================

# Normal participants can publish microphone and camera.
# LiveKit expects TrackSource enum values, not strings.
NORMAL_SOURCES = [
    api.TrackSource.MICROPHONE,
    api.TrackSource.CAMERA,
]

# An approved presenter can additionally publish screen
# video and screen audio.
SCREEN_SOURCES = [
    api.TrackSource.MICROPHONE,
    api.TrackSource.CAMERA,
    api.TrackSource.SCREEN_SHARE,
    api.TrackSource.SCREEN_SHARE_AUDIO,
]


# ============================================================
# 2. DETECT SCREEN-SHARING TRACKS
# ============================================================

def _is_screen_track(track):
    """
    Determine whether a LiveKit track is a screen track.

    Camera and microphone tracks are not screen sharing.
    """

    return track.source in (
        api.TrackSource.SCREEN_SHARE,
        api.TrackSource.SCREEN_SHARE_AUDIO,
    )


def _has_active_screen_track(participants):
    """
    Check all connected participants for screen tracks.

    Returns True if anyone is currently publishing
    a screen-sharing track.
    """

    return any(
        _is_screen_track(track)
        for participant in participants.values()
        for track in participant.tracks
    )


# ============================================================
# 3. GET LIVEKIT PARTICIPANTS
# ============================================================

async def _participant_list(room_client, room_name):
    """
    Retrieve the currently connected LiveKit participants.

    Return a dictionary indexed by participant identity.
    """

    result = await room_client.list_participants(
        api.ListParticipantsRequest(
            room=room_name,
        )
    )

    return {
        participant.identity: participant
        for participant in result.participants
    }


# ============================================================
# 4. UPDATE LIVEKIT PERMISSIONS
# ============================================================

async def _set_publish_sources(
    room_client,
    room_name,
    identity,
    sources,
):
    """
    Update a connected participant's publishing permissions.

    Camera and microphone permissions remain enabled.

    Screen-sharing permissions are controlled by the
    supplied source list.
    """

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


# ============================================================
# 5. GET MEETING ID FOR LOCKING
# ============================================================

def _get_approval_meeting_id(group_id, creator_id):
    """
    Find the active meeting for the requesting creator.

    This function only identifies the meeting.

    The reservation function performs authoritative
    permission checks after the operation lock is acquired.
    """

    meeting = _active_meeting_for_member(
        group_id,
        creator_id,
    )

    return meeting.pk


# ============================================================
# 6. COORDINATE SCREEN-SHARING APPROVAL
# ============================================================

async def coordinate_screen_share_approval(
    group_id,
    creator,
    request_id,
):
    """
    Coordinate screen-sharing approval safely.

    Workflow:

    1. Find the active meeting.
    2. Acquire its PostgreSQL advisory lock.
    3. Reserve the screen-sharing slot.
    4. Inspect connected LiveKit participants.
    5. Confirm nobody is currently sharing.
    6. Revoke the creator's screen permission.
    7. Grant the requesting member screen permission.
    8. Verify the resulting LiveKit state.
    9. Finalize the approval in PostgreSQL.
    10. Release the advisory lock.
    11. Broadcast the approval event.

    If an operation fails after reservation, the database
    remains in 'granting' until recovery reconciles it.

    Important:
    This function is not yet exposed to browser requests.
    """

    # --------------------------------------------------------
    # Step 1: Identify the active meeting.
    # --------------------------------------------------------

    meeting_id = await sync_to_async(
        _get_approval_meeting_id,
        thread_sensitive=True,
    )(
        group_id,
        creator.pk,
    )

    # --------------------------------------------------------
    # Step 2: Acquire the operation lock.
    # --------------------------------------------------------

    async with screen_share_operation_lock(meeting_id):

        # ----------------------------------------------------
        # Step 3: Reserve the screen-sharing slot.
        # ----------------------------------------------------

        reservation = await sync_to_async(
            reserve_screen_share_approval,
            thread_sensitive=True,
        )(
            group_id,
            creator.pk,
            request_id,
        )

        # Verify that the reservation belongs to the meeting
        # protected by our advisory lock.
        if reservation["meeting_id"] != meeting_id:
            raise ValidationError(
                "The active meeting changed during approval."
            )

        room_name = reservation["room_name"]

        creator_id = reservation["creator_id"]
        presenter_id = reservation["presenter_id"]

        # The creator must not approve themselves as
        # a separate screen-sharing presenter.
        if creator_id == presenter_id:
            raise ValidationError(
                "The meeting creator cannot approve "
                "themselves as a separate presenter."
            )

        try:

            # ------------------------------------------------
            # Step 4: Load LiveKit credentials.
            # ------------------------------------------------

            url, key, secret = _credentials()

            async with api.LiveKitAPI(
                url,
                key,
                secret,
            ) as client:

                room_client = client.room

                # --------------------------------------------
                # Step 5: Inspect connected participants.
                # --------------------------------------------

                participants = await _participant_list(
                    room_client,
                    room_name,
                )

                creator_participant = participants.get(
                    str(creator_id)
                )

                presenter_participant = participants.get(
                    str(presenter_id)
                )

                if creator_participant is None:
                    raise ValidationError(
                        "The meeting creator must be connected "
                        "to approve screen sharing."
                    )

                if presenter_participant is None:
                    raise ValidationError(
                        "The requesting member must be connected "
                        "to receive screen-sharing permission."
                    )

                # --------------------------------------------
                # Step 6: Confirm nobody is sharing.
                # --------------------------------------------

                if _has_active_screen_track(participants):
                    raise ValidationError(
                        "Someone is currently sharing a screen. "
                        "Stop sharing before approving another member."
                    )

                # --------------------------------------------
                # Step 7: Revoke creator screen permission.
                # --------------------------------------------

                await _set_publish_sources(
                    room_client,
                    room_name,
                    creator_id,
                    NORMAL_SOURCES,
                )

                # --------------------------------------------
                # Step 8: Grant presenter screen permission.
                # --------------------------------------------

                await _set_publish_sources(
                    room_client,
                    room_name,
                    presenter_id,
                    SCREEN_SOURCES,
                )

                # --------------------------------------------
                # Step 9: Inspect the updated participants.
                # --------------------------------------------

                participants = await _participant_list(
                    room_client,
                    room_name,
                )

                creator_participant = participants.get(
                    str(creator_id)
                )

                presenter_participant = participants.get(
                    str(presenter_id)
                )

                if creator_participant is None:
                    raise ValidationError(
                        "The meeting creator disconnected "
                        "during approval verification."
                    )

                if presenter_participant is None:
                    raise ValidationError(
                        "The approved member disconnected "
                        "during approval verification."
                    )

                # --------------------------------------------
                # Step 10: Check for unexpected screen tracks.
                # --------------------------------------------

                if _has_active_screen_track(participants):
                    raise ValidationError(
                        "A screen-sharing track appeared "
                        "during approval."
                    )

                # --------------------------------------------
                # Step 11: Verify publishing permissions.
                # --------------------------------------------

                from .screen_share_recovery import (
                    _can_publish_screen,
                )

                if _can_publish_screen(creator_participant):
                    raise ValidationError(
                        "The creator still has screen-sharing "
                        "permission after revocation."
                    )

                if not _can_publish_screen(
                    presenter_participant
                ):
                    raise ValidationError(
                        "The approved member did not receive "
                        "screen-sharing permission."
                    )

                # Every other connected participant must
                # remain restricted to camera and microphone.
                for identity, participant in participants.items():

                    if identity == str(presenter_id):
                        continue

                    if _can_publish_screen(participant):
                        raise ValidationError(
                            "Another participant has "
                            "screen-sharing permission."
                        )

            # ------------------------------------------------
            # Step 12: Finalize the database approval.
            # ------------------------------------------------

            screen_request = await sync_to_async(
                finalize_screen_share_approval,
                thread_sensitive=True,
            )(
                reservation["meeting_id"],
                request_id,
                creator_id,
                presenter_id,
            )

        except Exception:

            # Do not release the reserved slot here.
            #
            # A LiveKit permission update may have succeeded
            # even if the network request reported failure.
            #
            # Recovery must inspect and reconcile the
            # actual permissions before returning to idle.
            logger.exception(
                "Screen-sharing approval failed and requires "
                "reconciliation: meeting=%s request=%s",
                meeting_id,
                request_id,
            )

            raise

    # ========================================================
    # 7. BROADCAST APPROVAL AFTER LOCK RELEASE
    # ========================================================

    await _broadcast_screen_request_event(
        screen_request,
        "screen_share_approved",
    )

    logger.info(
        "Screen-sharing approval completed: "
        "meeting=%s presenter=%s request=%s",
        meeting_id,
        presenter_id,
        request_id,
    )

    return screen_request