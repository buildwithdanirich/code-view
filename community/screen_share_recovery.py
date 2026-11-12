"""
Screen-sharing permission recovery for CodeView.

Responsibilities:
- Recover interrupted screen-sharing approvals.
- Prevent recovery and approval from running simultaneously.
- Inspect current LiveKit participants and permissions.
- Revoke the presenter's screen-sharing permission.
- Restore the creator's permission when safe.
- Release the database reservation after verification.

Security:
- Uses a PostgreSQL advisory lock.
- Fails closed when LiveKit state cannot be verified.
- Never releases the database slot after an uncertain failure.
- Does not automatically run recovery.
- Reconnection protection must be implemented separately.
"""

import logging

from asgiref.sync import sync_to_async
from django.core.exceptions import ValidationError
from django.db import transaction
from livekit import api

from .meeting_service import _credentials
from .models import GroupMeeting
from .screen_share_lock import screen_share_operation_lock


logger = logging.getLogger(__name__)


# ============================================================
# 1. LIVEKIT PERMISSION CONFIGURATION
# ============================================================

# Normal meeting participants can use their microphone
# and camera, but cannot publish screen-sharing tracks.
NORMAL_SOURCES = [
    api.TrackSource.MICROPHONE,
    api.TrackSource.CAMERA,
]

# The meeting creator can publish microphone, camera,
# screen video, and screen audio when permission is restored.
SCREEN_SOURCES = [
    api.TrackSource.MICROPHONE,
    api.TrackSource.CAMERA,
    api.TrackSource.SCREEN_SHARE,
    api.TrackSource.SCREEN_SHARE_AUDIO,
]


def _permission(sources):
    """
    Build LiveKit publishing permissions.

    Developers retain microphone and camera access
    when screen sharing is disabled.
    """

    return api.ParticipantPermission(
        can_subscribe=True,
        can_publish=True,
        can_publish_data=True,
        can_publish_sources=sources,
    )


# ============================================================
# 2. READ RECOVERY STATE
# ============================================================

def _get_recovery_snapshot(meeting_id):
    """
    Read an interrupted approval from PostgreSQL.

    Only active meetings in the 'granting' state
    are eligible for this recovery operation.
    """

    meeting = GroupMeeting.objects.get(
        pk=meeting_id,
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
    Retrieve connected LiveKit participants.

    Return a dictionary indexed by participant identity.
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
    a screen-sharing video or audio track.
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
    Check whether LiveKit permits screen sharing.

    An empty source restriction means unrestricted
    publishing when can_publish=True.
    """

    permission = participant.permission

    # Fail closed when permission information is missing.
    if permission is None:
        return True

    if not permission.can_publish:
        return False

    sources = set(
        permission.can_publish_sources
    )

    if not sources:
        return True

    screen_sources = {
        api.TrackSource.SCREEN_SHARE,
        api.TrackSource.SCREEN_SHARE_AUDIO,
    }

    return bool(
        screen_sources.intersection(sources)
    )


def _verify_no_screen_tracks(participants):
    """
    Ensure nobody is currently publishing a screen track.

    Recovery must stop if screen sharing is active.
    """

    return not any(
        _has_screen_track(participant)
        for participant in participants.values()
    )


# ============================================================
# 4. UPDATE LIVEKIT PERMISSIONS
# ============================================================

async def _update_permission(
    room_client,
    room_name,
    identity,
    sources,
):
    """
    Update a connected participant's publishing permissions.

    The participant remains connected to the meeting.
    """

    await room_client.update_participant(
        api.UpdateParticipantRequest(
            room=room_name,
            identity=str(identity),
            permission=_permission(sources),
        )
    )


# ============================================================
# 5. RELEASE RECOVERED DATABASE SLOT
# ============================================================

def _release_recovered_slot(snapshot):
    """
    Release the screen-sharing reservation.

    PostgreSQL row locking prevents another database
    transaction from modifying the meeting simultaneously.

    The caller must already have completed LiveKit
    permission verification.
    """

    with transaction.atomic():

        meeting = (
            GroupMeeting.objects
            .select_for_update()
            .get(
                pk=snapshot["meeting_id"],
            )
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

        if meeting.started_by_id != snapshot["creator_id"]:
            raise ValidationError(
                "The meeting creator changed during recovery."
            )

        if str(meeting.room_name) != snapshot["room_name"]:
            raise ValidationError(
                "The meeting room changed during recovery."
            )

        # Clear the reserved presenter.
        meeting.active_screen_sharer = None

        # Allow future screen-sharing requests.
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
    Recover an interrupted screen-sharing approval.

    Workflow:

    1. Acquire PostgreSQL advisory lock.
    2. Read the database recovery state.
    3. Inspect LiveKit participants.
    4. Verify nobody is sharing.
    5. Revoke the presenter's screen permission.
    6. Verify revocation.
    7. Restore the creator's screen permission.
    8. Verify all connected participant permissions.
    9. Release the database reservation.
    10. Release the advisory lock.

    This is not yet a complete production recovery system.

    Stale LiveKit tokens and unexpected participant
    reconnections require additional protection.
    """

    # --------------------------------------------------------
    # STEP 1: ACQUIRE MEETING OPERATION LOCK
    # --------------------------------------------------------

    async with screen_share_operation_lock(meeting_id):

        # ----------------------------------------------------
        # STEP 2: READ DATABASE STATE
        # ----------------------------------------------------

        snapshot = await sync_to_async(
            _get_recovery_snapshot,
            thread_sensitive=True,
        )(meeting_id)

        url, key, secret = _credentials()

        room_name = snapshot["room_name"]

        creator_identity = str(
            snapshot["creator_id"]
        )

        presenter_identity = str(
            snapshot["presenter_id"]
        )

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

                creator = participants.get(
                    creator_identity
                )

                presenter = participants.get(
                    presenter_identity
                )

                # --------------------------------------------
                # STEP 4: VERIFY BOTH PARTICIPANTS
                # --------------------------------------------

                if creator is None:
                    raise ValidationError(
                        "The meeting creator must be connected "
                        "before recovery can continue."
                    )

                if presenter is None:
                    raise ValidationError(
                        "The reserved presenter must be connected "
                        "before recovery can continue."
                    )

                if creator_identity == presenter_identity:
                    raise ValidationError(
                        "The creator and presenter cannot "
                        "be the same participant."
                    )

                # --------------------------------------------
                # STEP 5: CHECK ACTIVE SCREEN TRACKS
                # --------------------------------------------

                if not _verify_no_screen_tracks(participants):
                    raise ValidationError(
                        "Screen sharing must stop before recovery."
                    )

                # --------------------------------------------
                # STEP 6: REVOKE PRESENTER PERMISSION
                # --------------------------------------------

                await _update_permission(
                    room_client,
                    room_name,
                    presenter_identity,
                    NORMAL_SOURCES,
                )

                # --------------------------------------------
                # STEP 7: VERIFY PRESENTER REVOCATION
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
                        "The presenter disconnected during recovery."
                    )

                if _can_publish_screen(presenter):
                    raise ValidationError(
                        "Presenter screen-sharing permission "
                        "was not revoked."
                    )

                creator = participants.get(
                    creator_identity
                )

                if creator is None:
                    raise ValidationError(
                        "The creator disconnected during recovery."
                    )

                # Security: no participant should be
                # actively sharing during recovery.
                if not _verify_no_screen_tracks(participants):
                    raise ValidationError(
                        "A screen-sharing track appeared "
                        "during presenter revocation."
                    )

                # --------------------------------------------
                # STEP 8: RESTORE CREATOR PERMISSION
                # --------------------------------------------

                await _update_permission(
                    room_client,
                    room_name,
                    creator_identity,
                    SCREEN_SOURCES,
                )

                # --------------------------------------------
                # STEP 9: VERIFY FINAL LIVEKIT STATE
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

                if creator is None:
                    raise ValidationError(
                        "Creator disconnected during verification."
                    )

                if presenter is None:
                    raise ValidationError(
                        "Presenter disconnected during verification."
                    )

                if not _can_publish_screen(creator):
                    raise ValidationError(
                        "Creator screen-sharing permission "
                        "was not restored."
                    )

                if _can_publish_screen(presenter):
                    raise ValidationError(
                        "Presenter still has screen-sharing permission."
                    )

                # Every other connected participant must
                # remain restricted to camera and microphone.
                for identity, participant in participants.items():

                    if identity == creator_identity:
                        continue

                    if _can_publish_screen(participant):
                        raise ValidationError(
                            "Another participant has "
                            "screen-sharing permission."
                        )

                # No screen track may be active while
                # the recovery operation completes.
                if not _verify_no_screen_tracks(participants):
                    raise ValidationError(
                        "A screen-sharing track appeared "
                        "during recovery."
                    )

            # ------------------------------------------------
            # STEP 10: RELEASE DATABASE RESERVATION
            # ------------------------------------------------

            # The advisory lock is still held here.
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

            # Keep the database reservation blocked.
            #
            # A LiveKit permission update may have succeeded
            # even if the network request failed.
            #
            # Recovery can be retried after inspecting
            # the actual LiveKit permissions.

            logger.exception(
                "Screen-sharing recovery failed: meeting=%s",
                meeting_id,
            )

            raise

    # Exiting the async context releases the advisory lock.