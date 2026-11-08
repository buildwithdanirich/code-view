"""
Django views for CodeView private development group invitations.

Features:
    1. Send invitations.
    2. Display received invitations in an HTML page.
    3. Accept invitations.
    4. Decline invitations.
    5. Support JSON responses for API clients.

Security:
    - Login is required.
    - Changes require POST requests.
    - Django CSRF protection applies.
    - Only private group owners can invite developers.
    - Invitation services enforce membership and capacity rules.
"""

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from .models import ProjectGroup, GroupInvitation
from .permissions import can_invite_group_members

from .invitations import (
    send_group_invitation,
    accept_group_invitation,
    decline_group_invitation,
    get_pending_invitations,
)


# Use Django's configured user model.
User = get_user_model()


# ============================================================
# 1. RESPONSE HELPERS
# ============================================================

def wants_json_response(request):
    """
    Determine whether the client explicitly requests JSON.

    Normal browser navigation:
        Return an HTML page.

    JavaScript/API requests:
        Return JSON.
    """

    accept_header = request.headers.get("Accept", "")

    return (
        "application/json" in accept_header
        or request.headers.get("X-Requested-With") == "XMLHttpRequest"
    )


def error_message(error):
    """
    Convert a Django validation error into readable text.
    """

    if hasattr(error, "messages"):
        return " ".join(error.messages)

    return str(error)


def invitation_response(
    request,
    success,
    message,
    redirect_url,
    status=200,
    extra_data=None,
):
    """
    Return JSON for API clients or redirect normal HTML forms.

    This prevents browsers from displaying raw JSON
    after submitting invitation forms.
    """

    response_data = {
        "success": success,
    }

    if success:
        response_data["message"] = message
    else:
        response_data["error"] = message

    if extra_data:
        response_data.update(extra_data)

    # Return JSON when explicitly requested.
    if wants_json_response(request):
        return JsonResponse(
            response_data,
            status=status,
        )

    # Store a notification for the next HTML page.
    if success:
        messages.success(request, message)
    else:
        messages.error(request, message)

    # Redirect after POST to avoid duplicate submissions on refresh.
    return redirect(redirect_url)


# ============================================================
# 2. SEND GROUP INVITATION
# ============================================================

@login_required
@require_POST
def send_invitation_view(request, group_id):
    """
    Allow the owner of a private group to invite a developer.

    Expected POST field:
        user_id

    The invitation service validates:
        - Private group status.
        - Group ownership.
        - Existing membership.
        - Duplicate invitations.
        - Group capacity.
    """

    group = get_object_or_404(
        ProjectGroup,
        pk=group_id,
    )

    # Reject requests from anyone except the private group owner.
    if not can_invite_group_members(group, request.user):
        raise PermissionDenied(
            "Only the private group owner can send invitations."
        )

    # Return to the members tab after submitting.
    group_url = (
        reverse("group_detail", args=[group.id])
        + "#group-members"
    )

    # Read the selected developer's ID.
    user_id = request.POST.get("user_id", "").strip()

    if not user_id:
        return invitation_response(
            request=request,
            success=False,
            message="Please select a developer to invite.",
            redirect_url=group_url,
            status=400,
        )

    # Validate the developer ID before querying the database.
    try:
        user_id = int(user_id)

        if user_id <= 0:
            raise ValueError

    except (TypeError, ValueError):
        return invitation_response(
            request=request,
            success=False,
            message="Invalid developer ID.",
            redirect_url=group_url,
            status=400,
        )

    # Find the registered developer.
    invited_user = User.objects.filter(
        pk=user_id,
    ).first()

    if invited_user is None:
        return invitation_response(
            request=request,
            success=False,
            message="Developer not found.",
            redirect_url=group_url,
            status=404,
        )

    try:
        # The service creates and validates the invitation.
        invitation = send_group_invitation(
            group=group,
            invited_by=request.user,
            invited_user=invited_user,
        )

    except ValidationError as error:
        return invitation_response(
            request=request,
            success=False,
            message=error_message(error),
            redirect_url=group_url,
            status=400,
        )

    except IntegrityError:
        return invitation_response(
            request=request,
            success=False,
            message="An invitation already exists for this developer.",
            redirect_url=group_url,
            status=409,
        )

    return invitation_response(
        request=request,
        success=True,
        message=(
            f"Invitation sent to "
            f"{invited_user.get_username()} successfully."
        ),
        redirect_url=group_url,
        extra_data={
            "invitation": {
                "id": invitation.pk,
                "group_id": invitation.group_id,
                "invited_user_id": invitation.invited_user_id,
                "status": invitation.status,
            },
        },
    )


# ============================================================
# 3. VIEW RECEIVED INVITATIONS
# ============================================================

@login_required
@require_GET
def received_invitations_view(request):
    """
    Display invitations received by the logged-in developer.

    Browser requests:
        Render received_invitations.html.

    JSON requests:
        Return invitation details as JSON.

    Developers can only see their own invitations.
    """

    # Fetch only invitations belonging to the current user.
    invitations = get_pending_invitations(
        request.user
    )

    # ========================================================
    # JSON RESPONSE
    # ========================================================

    if wants_json_response(request):

        invitation_list = []

        for invitation in invitations:

            invitation_list.append(
                {
                    "id": invitation.pk,
                    "group_id": invitation.group_id,
                    "group_name": invitation.group.name,
                    "invited_by": invitation.invited_by.get_username(),
                    "status": invitation.status,
                    "created_at": invitation.created_at.isoformat(),
                }
            )

        return JsonResponse(
            {
                "success": True,
                "count": len(invitation_list),
                "invitations": invitation_list,
            }
        )

    # ========================================================
    # HTML RESPONSE
    # ========================================================

    # Send the invitations to the Django HTML template.
    context = {
        "invitations": invitations,
    }

    return render(
        request,
        "community/received_invitations.html",
        context,
    )


# ============================================================
# 4. ACCEPT INVITATION
# ============================================================

@login_required
@require_POST
def accept_invitation_view(request, invitation_id):
    """
    Allow a developer to accept their own invitation.

    The service checks:
        - Invitation ownership.
        - Pending invitation status.
        - Group capacity.
        - Existing membership.

    Successful acceptance creates group membership.
    """

    invitations_url = reverse(
        "received_group_invitations"
    )

    try:
        invitation = accept_group_invitation(
            invitation_id=invitation_id,
            user=request.user,
        )

    except GroupInvitation.DoesNotExist:
        return invitation_response(
            request=request,
            success=False,
            message="Invitation not found.",
            redirect_url=invitations_url,
            status=404,
        )

    except ValidationError as error:
        return invitation_response(
            request=request,
            success=False,
            message=error_message(error),
            redirect_url=invitations_url,
            status=400,
        )

    except IntegrityError:
        return invitation_response(
            request=request,
            success=False,
            message="Unable to accept this invitation.",
            redirect_url=invitations_url,
            status=409,
        )

    # Open the group after accepting the invitation.
    group_url = reverse(
        "group_detail",
        args=[invitation.group_id],
    )

    return invitation_response(
        request=request,
        success=True,
        message="Invitation accepted. Welcome to the group!",
        redirect_url=group_url,
        extra_data={
            "group_id": invitation.group_id,
            "invitation_id": invitation.pk,
            "status": invitation.status,
        },
    )


# ============================================================
# 5. DECLINE INVITATION
# ============================================================

@login_required
@require_POST
def decline_invitation_view(request, invitation_id):
    """
    Allow a developer to decline their own invitation.

    Declining an invitation:
        - Does not create membership.
        - Changes the invitation status to declined.
        - Records the response time.
    """

    invitations_url = reverse(
        "received_group_invitations"
    )

    try:
        invitation = decline_group_invitation(
            invitation_id=invitation_id,
            user=request.user,
        )

    except GroupInvitation.DoesNotExist:
        return invitation_response(
            request=request,
            success=False,
            message="Invitation not found.",
            redirect_url=invitations_url,
            status=404,
        )

    except ValidationError as error:
        return invitation_response(
            request=request,
            success=False,
            message=error_message(error),
            redirect_url=invitations_url,
            status=400,
        )

    return invitation_response(
        request=request,
        success=True,
        message="Invitation declined successfully.",
        redirect_url=invitations_url,
        extra_data={
            "invitation_id": invitation.pk,
            "status": invitation.status,
        },
    )