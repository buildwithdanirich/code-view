"""
Verified LiveKit webhook receiver for CodeView.

Responsibilities:
- Receive webhook events from LiveKit.
- Verify webhook signatures.
- Identify approved screen-sharing presenters.
- Handle unexpected presenter disconnections.
- Trigger the existing disconnect recovery coordinator.

Security:
- Never trust an unverified webhook.
- Never expose LiveKit credentials.
- Never release permissions based only on a webhook event.
- Check the current meeting state before attempting recovery.
- Let the recovery coordinator inspect current LiveKit state.
- Use the existing PostgreSQL advisory lock during recovery.
- Do not allow an old event to directly change meeting permissions.

Important:
The recovery coordinator must still be protected against
stale LiveKit tokens and concurrent reconnections before
this feature is considered production-ready.
"""

import inspect
import logging

from asgiref.sync import sync_to_async
from django.http import (
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseNotAllowed,
)
from django.views.decorators.csrf import csrf_exempt

from livekit import api

from .meeting_service import _credentials
from .models import GroupMeeting
from .screen_share_disconnect import (
    recover_disconnected_screen_presenter,
)


logger = logging.getLogger(__name__)


# ============================================================
# 1. LIVEKIT WEBHOOK VERIFICATION
# ============================================================

def _get_webhook_receiver():
    """
    Create the official LiveKit webhook receiver.

    The API key and secret come from the existing
    CodeView LiveKit configuration.

    LiveKit webhook authorization must be verified
    before the event is processed.
    """

    # Reuse the same credentials as the meeting service.
    _, api_key, api_secret = _credentials()

    if not api_key or not api_secret:
        raise RuntimeError(
            "LiveKit webhook credentials are not configured."
        )

    verifier = api.TokenVerifier(
        api_key,
        api_secret,
    )

    return api.WebhookReceiver(
        verifier,
    )


# ============================================================
# 2. FIND ACTIVE CODEVIEW MEETING
# ============================================================

def _find_active_meeting(room_name):
    """
    Find the active CodeView meeting associated
    with a LiveKit room.

    Unknown and inactive rooms are ignored.

    This function accesses Django's database,
    so the async webhook calls it through
    sync_to_async().
    """

    if not room_name:
        return None

    return (
        GroupMeeting.objects
        .filter(
            room_name=room_name,
            status="active",
        )
        .first()
    )


# ============================================================
# 3. HANDLE PARTICIPANT DISCONNECTION
# ============================================================

async def _handle_participant_left(event):
    """
    Handle a verified LiveKit participant_left event.

    Only the approved screen-sharing presenter
    is relevant to disconnect recovery.

    This handler does not directly modify LiveKit
    permissions or the meeting database.

    Instead, it calls the recovery coordinator,
    which must recheck the current state.
    """

    # --------------------------------------------------------
    # STEP 1: EXTRACT ROOM AND PARTICIPANT
    # --------------------------------------------------------

    room = getattr(
        event,
        "room",
        None,
    )

    participant = getattr(
        event,
        "participant",
        None,
    )

    if room is None or participant is None:

        logger.warning(
            "Ignoring incomplete LiveKit participant_left event."
        )

        return

    room_name = getattr(
        room,
        "name",
        "",
    )

    participant_identity = getattr(
        participant,
        "identity",
        "",
    )

    participant_sid = getattr(
        participant,
        "sid",
        "",
    )

    if not room_name or not participant_identity:

        logger.warning(
            "Ignoring LiveKit event with missing room or identity."
        )

        return

    # --------------------------------------------------------
    # STEP 2: FIND THE ACTIVE MEETING
    # --------------------------------------------------------

    meeting = await sync_to_async(
        _find_active_meeting,
        thread_sensitive=True,
    )(room_name)

    if meeting is None:
        return

    # --------------------------------------------------------
    # STEP 3: CHECK SCREEN-SHARING STATE
    # --------------------------------------------------------

    # Only approved presenters are handled here.
    #
    # Interrupted approvals in the "granting" state
    # are handled by screen_share_recovery.py.

    if meeting.screen_share_state != "ready":
        return

    presenter_id = meeting.active_screen_sharer_id

    if presenter_id is None:
        return

    # --------------------------------------------------------
    # STEP 4: VERIFY PARTICIPANT IDENTITY
    # --------------------------------------------------------

    # CodeView uses Django user primary keys
    # as LiveKit participant identities.

    if str(presenter_id) != str(participant_identity):
        return

    # --------------------------------------------------------
    # STEP 5: LOG THE DISCONNECTION
    # --------------------------------------------------------

    logger.info(
        (
            "Approved screen presenter left LiveKit: "
            "meeting=%s identity=%s sid=%s"
        ),
        meeting.pk,
        participant_identity,
        participant_sid,
    )

    # --------------------------------------------------------
    # STEP 6: START DISCONNECT RECOVERY
    # --------------------------------------------------------

    # The recovery coordinator is responsible for:
    #
    # 1. Acquiring the PostgreSQL advisory lock.
    # 2. Rechecking the meeting state.
    # 3. Inspecting LiveKit participants.
    # 4. Detecting whether the presenter reconnected.
    # 5. Verifying no screen tracks remain.
    # 6. Restoring creator permissions when safe.
    # 7. Verifying the resulting permissions.
    # 8. Updating the database.

    result = await recover_disconnected_screen_presenter(
        meeting_id=meeting.pk,
        presenter_identity=participant_identity,
        participant_sid=participant_sid,
    )

    # --------------------------------------------------------
    # STEP 7: RECORD THE RESULT
    # --------------------------------------------------------

    if result.get("recovered"):

        logger.info(
            (
                "Screen-sharing disconnect recovery completed: "
                "meeting=%s presenter=%s"
            ),
            meeting.pk,
            participant_identity,
        )

    else:

        logger.info(
            (
                "Screen-sharing disconnect recovery skipped: "
                "meeting=%s presenter=%s reason=%s"
            ),
            meeting.pk,
            participant_identity,
            result.get("reason", "Not applicable."),
        )


# ============================================================
# 4. PROCESS VERIFIED LIVEKIT EVENTS
# ============================================================

async def _process_verified_event(event):
    """
    Route verified LiveKit events to the
    appropriate CodeView handler.

    Only participant_left is handled for now.

    Other verified events are acknowledged
    without changing meeting permissions.
    """

    event_type = getattr(
        event,
        "event",
        "",
    )

    if event_type == "participant_left":

        await _handle_participant_left(
            event,
        )

        return

    logger.debug(
        "Ignoring unrelated LiveKit event: %s",
        event_type,
    )


# ============================================================
# 5. LIVEKIT WEBHOOK ENDPOINT
# ============================================================

@csrf_exempt
async def livekit_webhook_view(request):
    """
    Receive and verify LiveKit webhook events.

    This endpoint is called by LiveKit rather than
    the developer's browser.

    Django CSRF protection is exempted because
    LiveKit does not send Django CSRF tokens.

    LiveKit's signed authorization is verified
    instead.

    Invalid signatures are rejected before
    any event can affect CodeView.
    """

    # --------------------------------------------------------
    # STEP 1: REQUIRE POST
    # --------------------------------------------------------

    if request.method != "POST":

        return HttpResponseNotAllowed(
            ["POST"],
        )

    # --------------------------------------------------------
    # STEP 2: REQUIRE AUTHORIZATION
    # --------------------------------------------------------

    authorization = request.headers.get(
        "Authorization",
        "",
    )

    if not authorization:

        return HttpResponse(
            "Missing LiveKit authorization.",
            status=401,
        )

    # --------------------------------------------------------
    # STEP 3: READ THE ORIGINAL REQUEST BODY
    # --------------------------------------------------------

    try:

        body = request.body.decode(
            "utf-8",
        )

    except UnicodeDecodeError:

        return HttpResponseBadRequest(
            "Invalid webhook encoding."
        )

    # --------------------------------------------------------
    # STEP 4: VERIFY THE WEBHOOK
    # --------------------------------------------------------

    try:

        receiver = _get_webhook_receiver()

        # Some LiveKit SDK versions implement receive()
        # asynchronously.
        #
        # Await the result when necessary.

        event = receiver.receive(
            body,
            authorization,
        )

        if inspect.isawaitable(event):

            event = await event

    except RuntimeError:

        logger.exception(
            "LiveKit webhook configuration error."
        )

        return HttpResponse(
            "Webhook configuration error.",
            status=503,
        )

    except Exception:

        logger.warning(
            "LiveKit webhook verification failed."
        )

        return HttpResponse(
            "Invalid LiveKit webhook.",
            status=401,
        )

    # --------------------------------------------------------
    # STEP 5: PROCESS THE VERIFIED EVENT
    # --------------------------------------------------------

    try:

        await _process_verified_event(
            event,
        )

    except Exception:

        logger.exception(
            "LiveKit webhook processing failed."
        )

        # A retryable response allows LiveKit to
        # attempt delivery again.
        #
        # Recovery operations must be safe to retry.

        return HttpResponse(
            "Webhook processing failed.",
            status=503,
        )

    # --------------------------------------------------------
    # STEP 6: ACKNOWLEDGE SUCCESS
    # --------------------------------------------------------

    return HttpResponse(
        status=200,
    )