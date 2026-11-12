"""
Screen-sharing approval coordination for CodeView.

This module reserves the screen-sharing slot in PostgreSQL.

Important:
- Reserving a slot does not grant LiveKit permission.
- LiveKit permissions must be updated before approval is finalized.
- A failed or interrupted transition must not silently free the slot.
"""

from django.core.exceptions import (
    PermissionDenied,
    ValidationError,
)

from django.db import transaction

from django.utils import timezone

from .models import (
    GroupMeeting,
    MeetingScreenShareRequest,
)

from .meeting_service import _active_meeting_for_member


# ============================================================
# 1. RESERVE SCREEN-SHARING APPROVAL
# ============================================================

def reserve_screen_share_approval(
    group_id,
    creator_id,
    request_id,
):
    """
    Reserve the screen-sharing slot for one developer.

    Only the meeting creator can approve requests.

    PostgreSQL row locking prevents two concurrent approvals
    from reserving the same meeting simultaneously.
    """

    with transaction.atomic():

        # Verify that the developer belongs to the group.
        meeting = _active_meeting_for_member(
            group_id,
            creator_id,
        )

        # Lock the meeting row until the transaction commits.
        meeting = (
            GroupMeeting.objects
            .select_for_update()
            .get(pk=meeting.pk)
        )

        # Only the meeting creator can approve requests.
        if meeting.started_by_id != creator_id:
            raise PermissionDenied(
                "Only the meeting creator can approve requests."
            )

        # An ended meeting cannot approve screen sharing.
        if meeting.status != "active":
            raise ValidationError(
                "This meeting has ended."
            )

        # The screen-sharing slot must be completely free.
        if (
            meeting.screen_share_state != "idle"
            or meeting.active_screen_sharer_id is not None
        ):
            raise ValidationError(
                "Screen-sharing permission is currently occupied."
            )

        # Find and lock the requested approval.
        screen_request = (
            MeetingScreenShareRequest.objects
            .select_for_update()
            .get(
                pk=request_id,
                meeting=meeting,
            )
        )

        # Only pending requests can be approved.
        if screen_request.status != "pending":
            raise ValidationError(
                "This request is no longer pending."
            )

        # The creator cannot approve their own request.
        if screen_request.requested_by_id == creator_id:
            raise ValidationError(
                "The meeting creator does not need approval."
            )

        # Reserve the slot for the selected developer.
        meeting.active_screen_sharer_id = (
            screen_request.requested_by_id
        )

        # Granting means the LiveKit operation is not complete.
        # The frontend must NOT enable screen sharing yet.
        meeting.screen_share_state = "granting"

        meeting.save(
            update_fields=[
                "active_screen_sharer",
                "screen_share_state",
            ]
        )

        return {
            "meeting_id": meeting.pk,
            "room_name": str(meeting.room_name),
            "creator_id": creator_id,
            "presenter_id": screen_request.requested_by_id,
            "request_id": screen_request.pk,
            "state": meeting.screen_share_state,
        }


# ============================================================
# 2. FINALIZE SUCCESSFUL APPROVAL
# ============================================================

def finalize_screen_share_approval(
    meeting_id,
    request_id,
    creator_id,
    presenter_id,
):
    """
    Finalize an approval after LiveKit confirms permissions.

    The calling service must first:
    1. Confirm the creator is not actively sharing.
    2. Revoke the creator's screen publication permission.
    3. Grant screen publication permission to the presenter.
    """

    with transaction.atomic():

        meeting = (
            GroupMeeting.objects
            .select_for_update()
            .get(pk=meeting_id)
        )

        # Reject stale or conflicting operations.
        if (
            meeting.status != "active"
            or meeting.screen_share_state != "granting"
            or meeting.active_screen_sharer_id != presenter_id
            or meeting.started_by_id != creator_id
        ):
            raise ValidationError(
                "Screen-sharing approval state has changed."
            )

        screen_request = (
            MeetingScreenShareRequest.objects
            .select_for_update()
            .get(
                pk=request_id,
                meeting=meeting,
                requested_by_id=presenter_id,
            )
        )

        if screen_request.status != "pending":
            raise ValidationError(
                "This request is no longer pending."
            )

        # Record the approved request.
        screen_request.status = "approved"
        screen_request.reviewed_by_id = creator_id
        screen_request.reviewed_at = timezone.now()

        screen_request.save(
            update_fields=[
                "status",
                "reviewed_by",
                "reviewed_at",
            ]
        )

        # The selected developer now owns the permission slot.
        meeting.screen_share_state = "ready"

        meeting.save(
            update_fields=[
                "screen_share_state",
            ]
        )

        return screen_request