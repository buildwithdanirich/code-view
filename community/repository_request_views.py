"""
Handle GitHub repository connection permission requests.

Rules:
- Only members of private development groups can request permission.
- Group owners do not need approval.
- Only the current group owner can approve or reject requests.
- An approval belongs to one membership and ownership period.
- Approval does not immediately replace the group's repository.

Real-time notifications:
- Notify the group owner when a new request is created.
- Notify the requesting member when a decision is made.
- Send events only after successful database commits.
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
    GroupMember,
    ProjectGroup,
    RepositoryConnectionRequest,
)


logger = logging.getLogger(__name__)


# ============================================================
# REAL-TIME NOTIFICATION HELPER
# ============================================================

def send_repository_notification(group_id, data):
    """
    Send a repository notification to the group's owner.

    This helper is called after the database transaction
    successfully commits.

    The WebSocket consumer independently checks ownership
    before forwarding the event to the browser.
    """

    try:
        # Get the configured Django Channels layer.
        channel_layer = get_channel_layer()

        if channel_layer is None:
            logger.warning(
                "Repository notification skipped: "
                "no channel layer is configured."
            )
            return

        # This name must match RepositoryNotificationConsumer.
        notification_group = (
            f"group_repository_owner_{group_id}"
        )

        # Send the event to connected owner WebSockets.
        async_to_sync(channel_layer.group_send)(
            notification_group,
            {
                "type": "repository.notification",
                "data": data,
            },
        )

    except Exception:
        # A notification failure must not undo a successfully
        # saved repository request or approval decision.
        logger.exception(
            "Failed to send repository notification "
            "for group %s.",
            group_id,
        )


# ============================================================
# 1. MEMBER REQUESTS REPOSITORY CONNECTION
# ============================================================

@login_required
@require_POST
def request_repository_connection(request, group_id):
    """
    Allow a group member to request permission to connect
    a GitHub repository.
    """

    with transaction.atomic():

        # Lock the group to coordinate membership and owner changes.
        group = get_object_or_404(
            ProjectGroup.objects.select_for_update(),
            pk=group_id,
        )

        # Only private development groups support repositories.
        if not group.is_private:
            return HttpResponseForbidden(
                "Repository connections are only available "
                "to private development groups."
            )

        # The owner can connect repositories without approval.
        if group.owner_id == request.user.id:
            messages.info(
                request,
                "You own this group and do not need approval.",
            )

            return redirect(
                "meeting_room",
                group_id=group.id,
            )

        # Check whether the developer belongs to the group.
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

            # An old request cannot grant permission after
            # the member rejoins or group ownership changes.
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

            # Invalidate an outdated request before creating a new one.
            existing_request.status = "cancelled"
            existing_request.save(
                update_fields=["status"],
            )

        # Create a new request for the current membership period.
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

        # Prepare a minimal event payload.
        # The owner-only consumer verifies authorization.
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

        # Notify only after the outer transaction commits.
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
# 2. GROUP OWNER APPROVES REQUEST
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

        if not group.is_private or group.owner_id != request.user.id:
            return HttpResponseForbidden(
                "Only the private group owner can approve requests."
            )

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

        # Check that the member still belongs to the group.
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
            # Expire the invalid request.
            connection_request.status = "cancelled"
            connection_request.save(update_fields=["status"])

            messages.error(
                request,
                "This request is no longer valid.",
            )

            return redirect(
                "meeting_room",
                group_id=group.id,
            )

        # Record the approval.
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
# 3. GROUP OWNER REJECTS REQUEST
# ============================================================

@login_required
@require_POST
def reject_repository_connection(request, group_id, request_id):
    """
    Allow the current group owner to reject a pending
    repository connection request.
    """

    with transaction.atomic():

        group = get_object_or_404(
            ProjectGroup.objects.select_for_update(),
            pk=group_id,
        )

        if not group.is_private or group.owner_id != request.user.id:
            return HttpResponseForbidden(
                "Only the private group owner can reject requests."
            )

        connection_request = get_object_or_404(
            RepositoryConnectionRequest.objects.select_for_update(),
            pk=request_id,
            group=group,
        )

        if connection_request.status != "pending":
            messages.error(
                request,
                "This repository request is no longer pending.",
            )

            return redirect(
                "meeting_room",
                group_id=group.id,
            )

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

    messages.success(
        request,
        "Repository connection request rejected.",
    )

    return redirect(
        "meeting_room",
        group_id=group.id,
    )