"""
HTTP endpoints for CodeView private group meetings.

The views handle browser requests.
The meeting service handles permissions and LiveKit operations.

Meeting actions require:
- An authenticated developer.
- An HTTP POST request.
- Django CSRF protection.

Meeting status checks require:
- An authenticated developer.
- An HTTP GET request.
- Accepted membership in the private group.
"""

import logging

from asgiref.sync import async_to_sync

from django.contrib.auth.decorators import login_required

from django.core.exceptions import (
    ObjectDoesNotExist,
    PermissionDenied,
    ValidationError,
)

from django.http import JsonResponse

from django.views.decorators.http import (
    require_GET,
    require_POST,
)

from .meeting_service import (
    start_group_meeting,
    join_group_meeting,
    end_group_meeting,
)

from .models import (
    GroupMeeting,
    ProjectGroup,
)

from .permissions import is_group_member


logger = logging.getLogger(__name__)


# ============================================================
# 1. MEETING ERROR HANDLING
# ============================================================

def _meeting_error_response(error):
    """
    Convert expected meeting errors into safe JSON responses.

    Do not expose internal server errors or LiveKit credentials.
    """

    if isinstance(error, PermissionDenied):
        return JsonResponse(
            {
                "success": False,
                "error": str(error),
            },
            status=403,
        )

    if isinstance(error, ObjectDoesNotExist):
        return JsonResponse(
            {
                "success": False,
                "error": "The requested group or meeting was not found.",
            },
            status=404,
        )

    if isinstance(error, ValidationError):
        return JsonResponse(
            {
                "success": False,
                "error": "; ".join(error.messages),
            },
            status=400,
        )

    # Unexpected errors are logged on the server.
    # Never expose internal exception details to the browser.
    logger.exception(
        "Unexpected private group meeting error",
        exc_info=error,
    )

    return JsonResponse(
        {
            "success": False,
            "error": "The meeting request could not be completed.",
        },
        status=500,
    )


# ============================================================
# 2. START MEETING
# ============================================================

@login_required
@require_POST
def start_meeting_view(request, group_id):
    """
    Start a meeting.

    Any accepted private group member may start a call.
    """

    try:
        meeting = async_to_sync(start_group_meeting)(
            group_id,
            request.user,
        )

    except Exception as error:
        return _meeting_error_response(error)

    return JsonResponse(
        {
            "success": True,
            "message": "Meeting started successfully.",
            "meeting": {
                "id": meeting.pk,
                "group_id": meeting.group_id,
                "room_name": str(meeting.room_name),
                "status": meeting.status,
                "started_by": meeting.started_by_id,
                "started_at": meeting.started_at.isoformat(),
            },
        },
        status=201,
    )


# ============================================================
# 3. JOIN MEETING
# ============================================================

@login_required
@require_POST
def join_meeting_view(request, group_id):
    """
    Join an existing meeting.

    The service checks current membership before issuing
    a short-lived LiveKit access token.

    If no active meeting exists, return HTTP 404 with a
    specific error code so the frontend can start one.
    """

    try:
        credentials = async_to_sync(join_group_meeting)(
            group_id,
            request.user,
        )

    except ValidationError as error:

        if error.messages == [
            "This group has no active meeting."
        ]:
            return JsonResponse(
                {
                    "success": False,
                    "error": "This group has no active meeting.",
                    "code": "no_active_meeting",
                },
                status=404,
            )

        return _meeting_error_response(error)

    except Exception as error:
        return _meeting_error_response(error)

    return JsonResponse(
        {
            "success": True,
            "message": "Meeting access granted.",
            "meeting": credentials,
        },
        status=200,
    )


# ============================================================
# 4. END MEETING
# ============================================================

@login_required
@require_POST
def end_meeting_view(request, group_id):
    """
    End the active meeting for everyone.

    Only the meeting creator or group owner may do this.
    """

    try:
        async_to_sync(end_group_meeting)(
            group_id,
            request.user,
        )

    except Exception as error:
        return _meeting_error_response(error)

    return JsonResponse(
        {
            "success": True,
            "message": "Meeting ended successfully.",
        },
        status=200,
    )


# ============================================================
# 5. CHECK MEETING STATUS
# ============================================================

@login_required
@require_GET
def meeting_status_view(request, group_id):
    """
    Check whether a private group has an active meeting.

    This endpoint is used by the repository-lock JavaScript.

    Security:
    - Only authenticated developers can access it.
    - Only accepted group members can check the status.
    - The response does not expose LiveKit credentials.
    """

    # --------------------------------------------------------
    # 1. Find the requested group.
    # --------------------------------------------------------

    try:
        group = ProjectGroup.objects.get(
            pk=group_id,
        )

    except ProjectGroup.DoesNotExist:
        return JsonResponse(
            {
                "success": False,
                "error": "Group not found.",
            },
            status=404,
        )

    # --------------------------------------------------------
    # 2. Ensure this is a private development group.
    # --------------------------------------------------------

    if not group.is_private:
        return JsonResponse(
            {
                "success": False,
                "error": "Meeting status is only available for private groups.",
            },
            status=403,
        )

    # --------------------------------------------------------
    # 3. Verify group membership.
    # --------------------------------------------------------

    if not is_group_member(group, request.user):
        return JsonResponse(
            {
                "success": False,
                "error": "You must belong to this group.",
            },
            status=403,
        )

    # --------------------------------------------------------
    # 4. Check PostgreSQL for an active meeting.
    # --------------------------------------------------------

    meeting_active = GroupMeeting.objects.filter(
        group=group,
        status="active",
    ).exists()

    # --------------------------------------------------------
    # 5. Return the current meeting status.
    # --------------------------------------------------------

    response = JsonResponse(
        {
            "success": True,
            "meeting_active": meeting_active,
            "repository_locked": meeting_active,
        },
        status=200,
    )

    # Prevent browsers or proxies from caching stale lock status.
    response["Cache-Control"] = "no-store"

    return response