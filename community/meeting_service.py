"""LiveKit meeting operations for CodeView private development groups.

This service must be called from authenticated Django views. It does not
replace authentication, CSRF protection, webhooks, or recovery workers.
"""

import logging
from datetime import timedelta

from asgiref.sync import sync_to_async
from channels.layers import get_channel_layer
from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from livekit import api

from .models import GroupMeeting, GroupMember, ProjectGroup


logger = logging.getLogger(__name__)


# ============================================================
# 1. LIVEKIT TRACK PERMISSIONS
# ============================================================

# Every accepted meeting participant can publish microphone
# and camera tracks.
MEMBER_PUBLISH_SOURCES = [
    "microphone",
    "camera",
]

# Only the developer who started the meeting can publish
# screen-sharing tracks.
#
# screen_share       = shared screen video
# screen_share_audio = audio captured from the shared screen
CREATOR_PUBLISH_SOURCES = [
    "microphone",
    "camera",
    "screen_share",
    "screen_share_audio",
]


# ============================================================
# 2. MEETING NOTIFICATIONS
# ============================================================

async def _broadcast_meeting_event(meeting, event_type):
    """Best-effort delivery; notifications never contain LiveKit secrets."""

    layer = get_channel_layer()

    if layer is None:
        logger.warning(
            "No channel layer configured for meeting notifications"
        )
        return

    data = {
        "type": event_type,
        "group_id": meeting.group_id,
        "meeting_id": meeting.pk,
    }

    if event_type == "meeting_started":
        data["started_by"] = meeting.started_by_id

        data["meeting_url"] = reverse(
            "meeting_room",
            kwargs={"group_id": meeting.group_id},
        )

    try:
        await layer.group_send(
            f"group_meeting_notifications_{meeting.group_id}",
            {
                "type": "meeting.notification",
                "data": data,
            },
        )

    except Exception:
        # Notification failures must not cause a successful
        # meeting operation to appear unsuccessful.
        logger.exception(
            "Unable to broadcast %s for meeting %s",
            event_type,
            meeting.pk,
        )


# ============================================================
# 3. LIVEKIT CREDENTIALS
# ============================================================

def _credentials():
    """Keep LiveKit secrets on the Django server."""

    url = getattr(
        settings,
        "LIVEKIT_URL",
        "",
    ).strip()

    key = getattr(
        settings,
        "LIVEKIT_API_KEY",
        "",
    ).strip()

    secret = getattr(
        settings,
        "LIVEKIT_API_SECRET",
        "",
    ).strip()

    if not all((url, key, secret)):
        raise ValidationError(
            "LiveKit credentials are not configured."
        )

    if not url.startswith("wss://"):
        raise ValidationError(
            "LiveKit requires a secure wss:// URL."
        )

    return url, key, secret


# ============================================================
# 4. GROUP MEMBERSHIP VALIDATION
# ============================================================

def _is_member(group, user_id):
    """The owner is a member even if their membership row is missing."""

    return (
        group.owner_id == user_id
        or GroupMember.objects.filter(
            group_id=group.pk,
            user_id=user_id,
        ).exists()
    )


def _private_group_for_member(group_id, user_id):
    """Reject outsiders and non-development communities."""

    group = ProjectGroup.objects.get(
        pk=group_id
    )

    if not group.is_private:
        raise PermissionDenied(
            "Meetings are for private development groups only."
        )

    if not _is_member(group, user_id):
        raise PermissionDenied(
            "Only current group members can use meetings."
        )

    return group


# ============================================================
# 5. RESERVE A MEETING
# ============================================================

def _reserve_meeting(group_id, user_id):
    """Serialize start requests by locking the parent group row."""

    with transaction.atomic():

        group = (
            ProjectGroup.objects
            .select_for_update()
            .get(pk=group_id)
        )

        if not group.is_private or not _is_member(
            group,
            user_id,
        ):
            raise PermissionDenied(
                "Only current private group members can start meetings."
            )

        if GroupMeeting.objects.filter(
            group=group,
            status="active",
        ).exists():
            raise ValidationError(
                "This group already has an active meeting."
            )

        return GroupMeeting.objects.create(
            group=group,
            started_by_id=user_id,
            status="active",
        )


# ============================================================
# 6. MARK MEETING AS ENDED
# ============================================================

def _mark_ended(meeting_id):
    """Close a meeting record without changing creator data."""

    with transaction.atomic():

        meeting = (
            GroupMeeting.objects
            .select_for_update()
            .get(pk=meeting_id)
        )

        if meeting.status == "active":

            meeting.status = "ended"
            meeting.ended_at = timezone.now()

            meeting.save(
                update_fields=[
                    "status",
                    "ended_at",
                ]
            )

        return meeting


# ============================================================
# 7. GET ACTIVE MEETING
# ============================================================

def _active_meeting_for_member(group_id, user_id):
    """Return an active meeting after verifying membership."""

    group = _private_group_for_member(
        group_id,
        user_id,
    )

    meeting = (
        GroupMeeting.objects
        .select_related("group")
        .filter(
            group=group,
            status="active",
        )
        .first()
    )

    if meeting is None:
        raise ValidationError(
            "This group has no active meeting."
        )

    return meeting


# ============================================================
# 8. VERIFY MEETING END PERMISSION
# ============================================================

def _meeting_for_ender(group_id, user_id):
    """Only the meeting creator or group owner may end it."""

    group = _private_group_for_member(
        group_id,
        user_id,
    )

    meeting = (
        GroupMeeting.objects
        .filter(
            group=group,
            status="active",
        )
        .first()
    )

    if meeting is None:
        raise ValidationError(
            "This group has no active meeting."
        )

    if user_id not in (
        group.owner_id,
        meeting.started_by_id,
    ):
        raise PermissionDenied(
            "Only the meeting creator or group owner can end it."
        )

    return meeting


# ============================================================
# 9. START GROUP MEETING
# ============================================================

async def start_group_meeting(group_id, user):
    """Reserve a meeting and create its 10-participant LiveKit room."""

    url, key, secret = _credentials()

    meeting = await sync_to_async(
        _reserve_meeting,
        thread_sensitive=True,
    )(
        group_id,
        user.pk,
    )

    try:

        async with api.LiveKitAPI(
            url,
            key,
            secret,
        ) as client:

            await client.room.create_room(
                api.CreateRoomRequest(
                    name=str(meeting.room_name),
                    max_participants=10,
                    empty_timeout=300,
                )
            )

    except Exception:

        # Best-effort rollback.
        #
        # A remote timeout or process crash may still require
        # reconciliation before production deployment.
        await sync_to_async(
            _mark_ended,
            thread_sensitive=True,
        )(
            meeting.pk
        )

        raise

    await _broadcast_meeting_event(
        meeting,
        "meeting_started",
    )

    return meeting


# ============================================================
# 10. JOIN GROUP MEETING
# ============================================================

async def join_group_meeting(group_id, user):
    """Authorize a member and issue a permission-restricted token."""

    # Verify LiveKit configuration.
    url, key, secret = _credentials()

    # Verify membership and locate the active meeting.
    meeting = await sync_to_async(
        _active_meeting_for_member,
        thread_sensitive=True,
    )(
        group_id,
        user.pk,
    )

    # --------------------------------------------------------
    # Identify meeting creator
    # --------------------------------------------------------

    is_meeting_creator = (
        user.pk == meeting.started_by_id
    )

    # --------------------------------------------------------
    # Screen-sharing permission
    # --------------------------------------------------------

    # Only the person who started this meeting can share.
    can_share_screen = is_meeting_creator

    if can_share_screen:

        publish_sources = CREATOR_PUBLISH_SOURCES.copy()

    else:

        publish_sources = MEMBER_PUBLISH_SOURCES.copy()

    # --------------------------------------------------------
    # Generate LiveKit token
    # --------------------------------------------------------

    token = (
        api.AccessToken(
            key,
            secret,
        )
        .with_identity(
            str(user.pk)
        )
        .with_name(
            user.get_username()
        )
        .with_ttl(
            timedelta(seconds=600)
        )
        .with_grants(
            api.VideoGrants(
                room_join=True,

                room=str(
                    meeting.room_name
                ),

                # Allow camera and microphone publication.
                can_publish=True,

                # Restrict the sources participants can publish.
                #
                # The meeting creator can publish screen tracks.
                # Other members cannot.
                can_publish_sources=publish_sources,

                # Everyone can watch and listen to others.
                can_subscribe=True,
            )
        )
        .to_jwt()
    )

    # --------------------------------------------------------
    # Meeting termination permission
    # --------------------------------------------------------

    # Both the group owner and the meeting creator
    # can end the meeting for everyone.
    can_end_meeting = (
        is_meeting_creator
        or user.pk == meeting.group.owner_id
    )

    # --------------------------------------------------------
    # Return meeting information
    # --------------------------------------------------------

    return {
        "url": url,
        "token": token,
        "room_name": str(meeting.room_name),
        "meeting_id": meeting.pk,

        # Meeting creator's database ID.
        "started_by": meeting.started_by_id,

        # Used by the frontend to display meeting controls.
        "can_end_meeting": can_end_meeting,

        # NEW: Used by the frontend to control screen sharing.
        "can_share_screen": can_share_screen,
    }


# ============================================================
# 11. END GROUP MEETING
# ============================================================

async def end_group_meeting(group_id, user):
    """Delete the LiveKit room, then mark the meeting ended."""

    url, key, secret = _credentials()

    meeting = await sync_to_async(
        _meeting_for_ender,
        thread_sensitive=True,
    )(
        group_id,
        user.pk,
    )

    async with api.LiveKitAPI(
        url,
        key,
        secret,
    ) as client:

        await client.room.delete_room(
            api.DeleteRoomRequest(
                room=str(meeting.room_name)
            )
        )

    await sync_to_async(
        _mark_ended,
        thread_sensitive=True,
    )(
        meeting.pk
    )

    await _broadcast_meeting_event(
        meeting,
        "meeting_ended",
    )

    return True


# ============================================================
# 12. READ ACTIVE MEETING
# ============================================================

def get_active_group_meeting(group_id, user):
    """Read the active meeting after checking membership."""

    return _active_meeting_for_member(
        group_id,
        user.pk,
    )