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


async def _broadcast_meeting_event(meeting, event_type):
    """Best-effort delivery; notifications never contain LiveKit secrets."""
    layer = get_channel_layer()
    if layer is None:
        logger.warning("No channel layer configured for meeting notifications")
        return
    data = {
        "type": event_type,
        "group_id": meeting.group_id,
        "meeting_id": meeting.pk,
    }
    if event_type == "meeting_started":
        data["started_by"] = meeting.started_by_id
        data["meeting_url"] = reverse(
            "meeting_room", kwargs={"group_id": meeting.group_id}
        )
    try:
        await layer.group_send(
            f"group_meeting_notifications_{meeting.group_id}",
            {"type": "meeting.notification", "data": data},
        )
    except Exception:
        # A notification outage must not turn a successful LiveKit operation
        # into an apparent failure and tempt the user to repeat it.
        logger.exception("Unable to broadcast %s for meeting %s", event_type, meeting.pk)


def _credentials():
    """Keep LiveKit secrets on the Django server, never in browser code."""
    url = getattr(settings, "LIVEKIT_URL", "").strip()
    key = getattr(settings, "LIVEKIT_API_KEY", "").strip()
    secret = getattr(settings, "LIVEKIT_API_SECRET", "").strip()
    if not all((url, key, secret)):
        raise ValidationError("LiveKit credentials are not configured.")
    if not url.startswith("wss://"):
        raise ValidationError("LiveKit requires a secure wss:// URL.")
    return url, key, secret


def _is_member(group, user_id):
    """The owner is a member even if their membership row is missing."""
    return group.owner_id == user_id or GroupMember.objects.filter(
        group_id=group.pk, user_id=user_id
    ).exists()


def _private_group_for_member(group_id, user_id):
    """Reject outsiders and non-development communities."""
    group = ProjectGroup.objects.get(pk=group_id)
    if not group.is_private:
        raise PermissionDenied("Meetings are for private development groups only.")
    if not _is_member(group, user_id):
        raise PermissionDenied("Only current group members can use meetings.")
    return group


def _reserve_meeting(group_id, user_id):
    """Serialize start requests by locking the parent group row."""
    with transaction.atomic():
        group = ProjectGroup.objects.select_for_update().get(pk=group_id)
        if not group.is_private or not _is_member(group, user_id):
            raise PermissionDenied("Only current private group members can start meetings.")
        if GroupMeeting.objects.filter(group=group, status="active").exists():
            raise ValidationError("This group already has an active meeting.")
        return GroupMeeting.objects.create(
            group=group, started_by_id=user_id, status="active"
        )


def _mark_ended(meeting_id):
    """Close a meeting record, without changing historical creator data."""
    with transaction.atomic():
        meeting = GroupMeeting.objects.select_for_update().get(pk=meeting_id)
        if meeting.status == "active":
            meeting.status = "ended"
            meeting.ended_at = timezone.now()
            meeting.save(update_fields=["status", "ended_at"])
        return meeting

def _active_meeting_for_member(group_id, user_id):
    group = _private_group_for_member(group_id, user_id)

    # Load the meeting and its group together.
    # Prevents an additional database query inside the async function.
    meeting = (
        GroupMeeting.objects
        .select_related("group")
        .filter(group=group, status="active")
        .first()
    )

    if meeting is None:
        raise ValidationError("This group has no active meeting.")

    return meeting


def _meeting_for_ender(group_id, user_id):
    """Only the caller who started the meeting or its group owner may end it."""
    group = _private_group_for_member(group_id, user_id)
    meeting = GroupMeeting.objects.filter(group=group, status="active").first()
    if meeting is None:
        raise ValidationError("This group has no active meeting.")
    if user_id not in (group.owner_id, meeting.started_by_id):
        raise PermissionDenied("Only the meeting creator or group owner can end it.")
    return meeting


async def start_group_meeting(group_id, user):
    """Reserve a DB meeting and create its 10-participant LiveKit room."""
    url, key, secret = _credentials()
    meeting = await sync_to_async(_reserve_meeting, thread_sensitive=True)(
        group_id, user.pk
    )
    try:
        async with api.LiveKitAPI(url, key, secret) as client:
            await client.room.create_room(
                api.CreateRoomRequest(
                    name=str(meeting.room_name),
                    max_participants=10,
                    empty_timeout=300,
                )
            )
    except Exception:
        # Best-effort rollback. An ambiguous remote outcome or process crash
        # still requires a separate reconciliation worker before production.
        await sync_to_async(_mark_ended, thread_sensitive=True)(meeting.pk)
        raise
    await _broadcast_meeting_event(meeting, "meeting_started")
    return meeting


async def join_group_meeting(group_id, user):
    """
    Authorize a current group member and issue a LiveKit token.

    Also return meeting information so the frontend knows
    whether the current developer can end the meeting.
    """

    # Verify LiveKit configuration.
    url, key, secret = _credentials()

    # Verify that the developer belongs to the private group
    # and that an active meeting exists.
    meeting = await sync_to_async(
        _active_meeting_for_member,
        thread_sensitive=True,
    )(group_id, user.pk)

    # Generate a short-lived LiveKit access token.
    token = (
        api.AccessToken(key, secret)
        .with_identity(str(user.pk))
        .with_name(user.get_username())
        .with_ttl(timedelta(seconds=600))
        .with_grants(
            api.VideoGrants(
                room_join=True,
                room=str(meeting.room_name),
                can_publish=True,
                can_subscribe=True,
            )
        )
        .to_jwt()
    )

    # The meeting creator and group owner can end the call.
    # Django will independently enforce this permission
    # when the developer requests to end the meeting.
    can_end_meeting = (
        user.pk == meeting.started_by_id
        or user.pk == meeting.group.owner_id
    )

    # Return the credentials and meeting information.
    return {
        "url": url,
        "token": token,
        "room_name": str(meeting.room_name),
        "meeting_id": meeting.pk,
        "started_by": meeting.started_by_id,
        "can_end_meeting": can_end_meeting,
    }


async def end_group_meeting(group_id, user):
    """Delete the LiveKit room, then mark the meeting ended in the DB."""
    url, key, secret = _credentials()
    meeting = await sync_to_async(_meeting_for_ender, thread_sensitive=True)(
        group_id, user.pk
    )
    async with api.LiveKitAPI(url, key, secret) as client:
        await client.room.delete_room(
            api.DeleteRoomRequest(room=str(meeting.room_name))
        )
    await sync_to_async(_mark_ended, thread_sensitive=True)(meeting.pk)
    await _broadcast_meeting_event(meeting, "meeting_ended")
    return True


def get_active_group_meeting(group_id, user):
    """Read the active meeting after checking current membership."""
    return _active_meeting_for_member(group_id, user.pk)