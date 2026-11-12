"""
Screen-sharing approval coordination for CodeView.

This module reserves the screen-sharing slot in PostgreSQL.

Important:
- Reserving a slot does not grant LiveKit permission.
- LiveKit permissions must be updated before approval is finalized.
- A failed or interrupted transition must not silently free the slot.
- Only the meeting creator can approve screen-sharing requests.
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

    PostgreSQL row locking prevents concurrent approvals
    from reserving the same meeting simultaneously.
    """

    with transaction.atomic():

        # ----------------------------------------------------
        # Step 1: Verify the creator belongs to an active
        # meeting in the requested group.
        # ----------------------------------------------------

        meeting = _active_meeting_for_member(
            group_id,
            creator_id,
        )

        # ----------------------------------------------------
        # Step 2: Lock the meeting row.
        # ----------------------------------------------------

        meeting = (
            GroupMeeting.objects
            .select_for_update()
            .get(pk=meeting.pk)
        )

        # ----------------------------------------------------
        # Step 3: Verify meeting ownership.
        # ----------------------------------------------------

        if meeting.started_by_id != creator_id:
            raise PermissionDenied(
                "Only the meeting creator can approve requests."
            )

        if meeting.status != "active":
            raise ValidationError(
                "This meeting has ended."
            )

        # ----------------------------------------------------
        # Step 4: Verify the screen-sharing slot is free.
        # ----------------------------------------------------

        if (
            meeting.screen_share_state != "idle"
            or meeting.active_screen_sharer_id is not None
        ):
            raise ValidationError(
                "Screen-sharing permission is currently occupied."
            )

        # ----------------------------------------------------
        # Step 5: Lock the selected screen-sharing request.
        # ----------------------------------------------------

        screen_request = (
            MeetingScreenShareRequest.objects
            .select_for_update()
            .get(
                pk=request_id,
                meeting=meeting,
            )
        )

        # ----------------------------------------------------
        # Step 6: Validate request status.
        # ----------------------------------------------------

        if screen_request.status != "pending":
            raise ValidationError(
                "This request is no longer pending."
            )

        # ----------------------------------------------------
        # Step 7: Prevent creator self-approval.
        # ----------------------------------------------------

        if screen_request.requested_by_id == creator_id:
            raise ValidationError(
                "The meeting creator does not need approval."
            )

        # ----------------------------------------------------
        # Step 8: Reserve the screen-sharing slot.
        # ----------------------------------------------------

        meeting.active_screen_sharer_id = (
            screen_request.requested_by_id
        )

        # The LiveKit operation has not completed yet.
        # The frontend must not enable screen sharing.
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
    Finalize approval after LiveKit confirms permissions.

    The calling service must first:

    1. Confirm the creator is not actively sharing.
    2. Revoke the creator's screen publication permission.
    3. Grant screen publication permission to the presenter.
    4. Verify no other participant can share.
    """

    with transaction.atomic():

        # ----------------------------------------------------
        # Step 1: Lock the meeting.
        # ----------------------------------------------------

        meeting = (
            GroupMeeting.objects
            .select_for_update()
            .get(pk=meeting_id)
        )

        # ----------------------------------------------------
        # Step 2: Verify the meeting remains active.
        # ----------------------------------------------------

        if meeting.status != "active":
            raise ValidationError(
                "The meeting ended during approval."
            )

        # ----------------------------------------------------
        # Step 3: Verify the reserved state.
        # ----------------------------------------------------

        if meeting.screen_share_state != "granting":
            raise ValidationError(
                "Screen-sharing approval state has changed."
            )

        if meeting.active_screen_sharer_id != presenter_id:
            raise ValidationError(
                "The reserved presenter has changed."
            )

        # ----------------------------------------------------
        # Step 4: Verify creator identity.
        # ----------------------------------------------------

        if meeting.started_by_id != creator_id:
            raise PermissionDenied(
                "Only the meeting creator can approve requests."
            )

        # ----------------------------------------------------
        # Step 5: Prevent creator self-approval.
        # ----------------------------------------------------

        if creator_id == presenter_id:
            raise ValidationError(
                "The meeting creator cannot approve themselves."
            )

        # ----------------------------------------------------
        # Step 6: Lock the original request.
        # ----------------------------------------------------

        screen_request = (
            MeetingScreenShareRequest.objects
            .select_for_update()
            .get(
                pk=request_id,
                meeting=meeting,
                requested_by_id=presenter_id,
            )
        )

        # ----------------------------------------------------
        # Step 7: Reject stale or duplicate approvals.
        # ----------------------------------------------------

        if screen_request.status != "pending":
            raise ValidationError(
                "This request is no longer pending."
            )

        # ----------------------------------------------------
        # Step 8: Record the approved request.
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # Step 9: Mark the screen-sharing slot ready.
        # ----------------------------------------------------

        meeting.screen_share_state = "ready"

        meeting.save(
            update_fields=[
                "screen_share_state",
            ]
        )

        return screen_request