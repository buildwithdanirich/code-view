"""
HTTP endpoints for CodeView private group meetings.

The views handle browser requests.
The meeting service handles permissions and LiveKit operations.

All meeting actions require:
- An authenticated developer.
- An HTTP POST request.
- Django CSRF protection.
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
from django.views.decorators.http import require_POST

from .meeting_service import (
    start_group_meeting,
    join_group_meeting,
    end_group_meeting,
)

logger = logging.getLogger(__name__)


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


@login_required
@require_POST
def join_meeting_view(request, group_id):
    """
    Join an existing meeting.

    The service checks current membership before issuing
    a short-lived LiveKit access token.
    """

    try:
        credentials = async_to_sync(join_group_meeting)(
            group_id,
            request.user,
        )

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