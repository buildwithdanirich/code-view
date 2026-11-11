"""
CodeView — GitHub Repository Connection Permission Requests.

Rules:
1. Only private development group members can request permission.
2. Group owners do not need approval.
3. Only the current group owner can approve or reject requests.
4. Approvals belong to a specific membership and ownership period.
5. Approval does not automatically replace the group's repository.

Real-time notifications:
1. Notify the owner when a new request is created.
2. Notify the requesting member when approved or rejected.
3. Send notifications only after successful database commits.
"""

import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import (
    GroupMeeting,
    GroupMember,
    ProjectGroup,
    RepositoryConnectionRequest,
)


logger = logging.getLogger(__name__)


# ============================================================
# 1. OWNER REPOSITORY NOTIFICATION HELPER
# ============================================================

def send_repository_notification(group_id, data):
    """
    Notify the group owner about a new repository request.

    This function runs after the database transaction commits.
    """

    try:
        # Get Django Channels' configured channel layer.
        channel_layer = get_channel_layer()

        if channel_layer is None:
            logger.warning(
                "Repository notification skipped: "
                "no channel layer is configured."
            )
            return

        # This must match RepositoryNotificationConsumer.
        notification_group = (
            f"group_repository_owner_{group_id}"
        )

        # Send the notification to the owner's WebSocket.
        async_to_sync(channel_layer.group_send)(
            notification_group,
            {
                "type": "repository.notification",
                "data": data,
            },
        )

    except Exception:
        # Notification failures must not undo saved requests.
        logger.exception(
            "Failed to send repository notification "
            "for group %s.",
            group_id,
        )


# ============================================================
# 2. MEMBER REPOSITORY DECISION NOTIFICATION HELPER
# ============================================================

def send_repository_member_notification(
    group_id,
    user_id,
    membership_generation,
    data,
):
    """
    Notify one member about an approval or rejection.

    The notification is delivered only to the specified
    authenticated member and membership generation.
    """

    try:
        # Get Django Channels' configured channel layer.
        channel_layer = get_channel_layer()

        if channel_layer is None:
            logger.warning(
                "Member repository notification skipped: "
                "no channel layer is configured."
            )
            return

        # Each member has a separate notification channel.
        # This name must match RepositoryMemberNotificationConsumer.
        notification_group = (
            f"group_repository_member_{group_id}_{user_id}"
        )

        # Send the decision to the requesting member.
        async_to_sync(channel_layer.group_send)(
            notification_group,
            {
                "type": "repository.decision",

                # The consumer checks this before delivering.
                "membership_generation": membership_generation,

                # Information sent to the browser.
                "data": data,
            },
        )

    except Exception:
        # A WebSocket failure must not undo an approval/rejection.
        logger.exception(
            "Failed to send repository decision notification "
            "for group %s and user %s.",
            group_id,
            user_id,
        )


# ============================================================
# 3. MEMBER REQUESTS REPOSITORY CONNECTION
# ============================================================

@login_required
@require_POST
def request_repository_connection(request, group_id):
    """
    Allow a private group member to request permission
    to connect a GitHub repository.
    """

    with transaction.atomic():

        # Lock the group while checking membership and ownership.
        group = get_object_or_404(
            ProjectGroup.objects.select_for_update(),
            pk=group_id,
        )

        # Only private groups support repository connections.
        if not group.is_private:
            return HttpResponseForbidden(
                "Repository connections are only available "
                "to private development groups."
            )

        # Block repository requests during an active meeting.
        if GroupMeeting.objects.filter(
            group=group,
            status="active",
        ).exists():
            return HttpResponseForbidden(
                "Repository connections are locked while "
                "a group meeting is active. "
                "Please wait until the meeting ends."
            )

        # Owners can connect repositories without approval.
        if group.owner_id == request.user.id:
            messages.info(
                request,
                "You own this group and do not need approval.",
            )

            return redirect(
                "meeting_room",
                group_id=group.id,
            )

        # Verify that the developer belongs to this group.
        membership = GroupMember.objects.filter(
            group=group,
            user=request.user,
        ).first()

        if membership is None:
            return HttpResponseForbidden(
                "Only group members can request repository access."
            )

        # Check for an existing pending or approved request.
        existing_request = (
            RepositoryConnectionRequest.objects.filter(
                group=group,
                requested_by=request.user,
                status__in=["pending", "approved"],
            )
            .order_by("-created_at")
            .first()
        )

        if existing_request:

            # Determine whether this request still belongs
            # to the current membership and ownership periods.
            is_current = (
                existing_request.membership_generation
                == membership.membership_generation
                and existing_request.owner_membership_generation
                == group.owner_membership_generation
            )

            if is_current:

                if existing_request.status == "pending":
                    messages.info(
                        request,
                        "Your repository connection request "
                        "is awaiting the group owner's approval.",
                    )

                else:
                    messages.success(
                        request,
                        "Your request is approved. "
                        "You can continue connecting GitHub.",
                    )

                return redirect(
                    "meeting_room",
                    group_id=group.id,
                )

            # Cancel an outdated request.
            existing_request.status = "cancelled"
            existing_request.save(
                update_fields=["status"],
            )

        # Create a new request for this membership period.
        try:
            with transaction.atomic():

                connection_request = (
                    RepositoryConnectionRequest.objects.create(
                        group=group,
                        requested_by=request.user,
                        membership_generation=(
                            membership.membership_generation
                        ),
                        owner_membership_generation=(
                            group.owner_membership_generation
                        ),
                        status="pending",
                    )
                )

        except IntegrityError:
            messages.info(
                request,
                "You already have a repository connection request.",
            )

            return redirect(
                "meeting_room",
                group_id=group.id,
            )

        # Prepare the owner notification.
        notification_data = {
            "type": "repository_request_created",
            "group_id": group.id,
            "request_id": connection_request.id,
            "requested_by": request.user.get_username(),
            "message": (
                "A group member requested permission "
                "to connect a GitHub repository."
            ),
        }

        # Send the notification after PostgreSQL commits.
        transaction.on_commit(
            lambda group_id=group.id, data=notification_data: (
                send_repository_notification(group_id, data)
            )
        )

    messages.success(
        request,
        "Your repository connection request has been sent "
        "to the group owner.",
    )

    return redirect(
        "meeting_room",
        group_id=group.id,
    )


# ============================================================
# 4. GROUP OWNER APPROVES REQUEST
# ============================================================

@login_required
@require_POST
def approve_repository_connection(request, group_id, request_id):
    """
    Allow the current group owner to approve a member's
    repository connection request.
    """

    with transaction.atomic():

        # Lock the group before checking ownership.
        group = get_object_or_404(
            ProjectGroup.objects.select_for_update(),
            pk=group_id,
        )

        # Only the current private group owner can approve.
        if not group.is_private or group.owner_id != request.user.id:
            return HttpResponseForbidden(
                "Only the private group owner can approve requests."
            )

        # Block repository decisions during an active meeting.
        if GroupMeeting.objects.filter(
            group=group,
            status="active",
        ).exists():
            return HttpResponseForbidden(
                "Repository connections are locked while "
                "a group meeting is active. "
                "Please wait until the meeting ends."
            )

        # Lock the request to prevent simultaneous decisions.
        connection_request = get_object_or_404(
            RepositoryConnectionRequest.objects.select_for_update(),
            pk=request_id,
            group=group,
        )

        # Only pending requests can be approved.
        if connection_request.status != "pending":
            messages.error(
                request,
                "This repository request is no longer pending.",
            )

            return redirect(
                "meeting_room",
                group_id=group.id,
            )

        # Verify that the requesting member still belongs
        # to the same membership period.
        membership = GroupMember.objects.filter(
            group=group,
            user=connection_request.requested_by,
        ).first()

        if (
            membership is None
            or membership.membership_generation
            != connection_request.membership_generation
            or group.owner_membership_generation
            != connection_request.owner_membership_generation
        ):

            # An outdated request cannot be approved.
            connection_request.status = "cancelled"
            connection_request.save(
                update_fields=["status"],
            )

            messages.error(
                request,
                "This request is no longer valid.",
            )

            return redirect(
                "meeting_room",
                group_id=group.id,
            )

        # Save the approval in PostgreSQL.
        connection_request.status = "approved"
        connection_request.reviewed_by = request.user
        connection_request.reviewed_at = timezone.now()

        connection_request.save(
            update_fields=[
                "status",
                "reviewed_by",
                "reviewed_at",
            ],
        )

        # ====================================================
        # NOTIFY THE REQUESTING MEMBER
        # ====================================================

        notification_data = {
            "type": "repository_request_approved",
            "group_id": group.id,
            "request_id": connection_request.id,
            "status": "approved",
            "message": (
                "Your repository connection request "
                "has been approved."
            ),
        }

        # Capture the correct member and membership generation.
        member_id = connection_request.requested_by_id
        membership_generation = (
            connection_request.membership_generation
        )

        # Send only after the approval commits successfully.
        transaction.on_commit(
            lambda group_id=group.id,
                   user_id=member_id,
                   generation=membership_generation,
                   data=notification_data: (
                send_repository_member_notification(
                    group_id,
                    user_id,
                    generation,
                    data,
                )
            )
        )

    messages.success(
        request,
        "Repository connection request approved. "
        "The member can now continue to GitHub.",
    )

    return redirect(
        "meeting_room",
        group_id=group.id,
    )


# ============================================================
# 5. GROUP OWNER REJECTS REQUEST
# ============================================================

@login_required
@require_POST
def reject_repository_connection(request, group_id, request_id):
    """
    Allow the current group owner to reject a pending
    repository connection request.
    """

    with transaction.atomic():

        # Lock the group before checking ownership.
        group = get_object_or_404(
            ProjectGroup.objects.select_for_update(),
            pk=group_id,
        )

        # Only the current private group owner can reject.
        if not group.is_private or group.owner_id != request.user.id:
            return HttpResponseForbidden(
                "Only the private group owner can reject requests."
            )

        # Block repository decisions during an active meeting.
        if GroupMeeting.objects.filter(
            group=group,
            status="active",
        ).exists():
            return HttpResponseForbidden(
                "Repository connections are locked while "
                "a group meeting is active. "
                "Please wait until the meeting ends."
            )

        # Lock the request to prevent simultaneous decisions.
        connection_request = get_object_or_404(
            RepositoryConnectionRequest.objects.select_for_update(),
            pk=request_id,
            group=group,
        )

        # Only pending requests can be rejected.
        if connection_request.status != "pending":
            messages.error(
                request,
                "This repository request is no longer pending.",
            )

            return redirect(
                "meeting_room",
                group_id=group.id,
            )

        # Save the rejection in PostgreSQL.
        connection_request.status = "rejected"
        connection_request.reviewed_by = request.user
        connection_request.reviewed_at = timezone.now()

        connection_request.save(
            update_fields=[
                "status",
                "reviewed_by",
                "reviewed_at",
            ],
        )

        # ====================================================
        # NOTIFY THE REQUESTING MEMBER
        # ====================================================

        notification_data = {
            "type": "repository_request_rejected",
            "group_id": group.id,
            "request_id": connection_request.id,
            "status": "rejected",
            "message": (
                "Your repository connection request "
                "has been rejected."
            ),
        }

        member_id = connection_request.requested_by_id
        membership_generation = (
            connection_request.membership_generation
        )

        # Send only after PostgreSQL commits the rejection.
        transaction.on_commit(
            lambda group_id=group.id,
                   user_id=member_id,
                   generation=membership_generation,
                   data=notification_data: (
                send_repository_member_notification(
                    group_id,
                    user_id,
                    generation,
                    data,
                )
            )
        )

    messages.success(
        request,
        "Repository connection request rejected.",
    )

    return redirect(
        "meeting_room",
        group_id=group.id,
    )