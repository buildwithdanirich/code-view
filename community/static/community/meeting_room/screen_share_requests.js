/**
 * CodeView screen-sharing request controller.
 *
 * Handles:
 * - Requesting screen-sharing permission
 * - Cancelling pending requests
 * - Rejecting pending requests
 * - Preparing the Approve action
 * - Polling Django for permission changes
 * - Notifying the LiveKit controller
 *
 * Security:
 * Django and LiveKit enforce actual permissions.
 * Approval stays disabled until lifecycle safeguards are complete.
 */

document.addEventListener("DOMContentLoaded", () => {
    "use strict";

    // -----------------------------------------------------
    // 1. HTML ELEMENTS
    // -----------------------------------------------------

    const panel = document.getElementById("livekit-meeting-panel");

    const permissionSection = document.getElementById(
        "livekit-screen-share-permissions"
    );

    const memberActions = document.getElementById(
        "livekit-screen-share-member-actions"
    );

    const requestButton = document.getElementById(
        "livekit-request-screen-share"
    );

    const cancelButton = document.getElementById(
        "livekit-cancel-screen-share-request"
    );

    const requestStatus = document.getElementById(
        "livekit-screen-share-request-status"
    );

    const creatorRequests = document.getElementById(
        "livekit-screen-share-creator-requests"
    );

    const requestList = document.getElementById(
        "livekit-screen-share-request-list"
    );

    const noRequests = document.getElementById(
        "livekit-screen-share-no-requests"
    );

    const requestTemplate = document.getElementById(
        "livekit-screen-share-request-template"
    );

    if (
        !panel ||
        !permissionSection ||
        !memberActions ||
        !requestButton ||
        !cancelButton ||
        !requestStatus ||
        !creatorRequests ||
        !requestList ||
        !noRequests ||
        !requestTemplate
    ) {
        console.error("CodeView: Missing screen-sharing elements.");
        return;
    }

    // -----------------------------------------------------
    // 2. DJANGO URLS
    // -----------------------------------------------------

    const stateUrl = panel.dataset.screenShareStateUrl;
    const requestUrl = panel.dataset.screenShareRequestUrl;

    const approveUrlTemplate =
        panel.dataset.screenShareApproveUrlTemplate;

    const rejectUrlTemplate =
        panel.dataset.screenShareRejectUrlTemplate;

    const cancelUrlTemplate =
        panel.dataset.screenShareCancelUrlTemplate;

    // Enable the meeting creator's Approve button.
    // Django remains responsible for authorization.
    const APPROVAL_ENABLED = true;

    if (
        !stateUrl ||
        !requestUrl ||
        !approveUrlTemplate ||
        !rejectUrlTemplate ||
        !cancelUrlTemplate
    ) {
        console.error("CodeView: Missing screen-sharing URLs.");
        return;
    }

    // -----------------------------------------------------
    // 3. STATE
    // -----------------------------------------------------

    let connected = false;
    let meetingId = null;
    let isMeetingCreator = false;
    let pendingRequestId = null;
    let permissionState = null;
    let busy = false;
    let pollingTimer = null;
    let connectionGeneration = 0;

    const POLLING_INTERVAL_MS = 3000;

    // -----------------------------------------------------
    // 4. CSRF TOKEN
    // -----------------------------------------------------

    function getCsrfToken() {
        const input = document.querySelector(
            'input[name="csrfmiddlewaretoken"]'
        );

        if (input?.value) {
            return input.value;
        }

        const cookie = document.cookie
            .split(";")
            .map(value => value.trim())
            .find(value => value.startsWith("csrftoken="));

        return cookie
            ? decodeURIComponent(cookie.substring("csrftoken=".length))
            : "";
    }

    // -----------------------------------------------------
    // 5. HTTP REQUESTS
    // -----------------------------------------------------

    async function readResponse(response) {
        let data;

        try {
            data = await response.json();
        } catch {
            throw new Error("The server returned an invalid response.");
        }

        if (!response.ok || data.success !== true) {
            throw new Error(data.error || "The request failed.");
        }

        return data;
    }

    async function getPermissionState() {
        const response = await fetch(stateUrl, {
            method: "GET",
            credentials: "same-origin",
            cache: "no-store",
            headers: {
                "X-Requested-With": "XMLHttpRequest",
            },
        });

        return readResponse(response);
    }

    async function postRequest(url) {
        const response = await fetch(url, {
            method: "POST",
            credentials: "same-origin",
            headers: {
                "X-CSRFToken": getCsrfToken(),
                "X-Requested-With": "XMLHttpRequest",
            },
        });

        return readResponse(response);
    }

    // -----------------------------------------------------
    // 6. HELPERS
    // -----------------------------------------------------

    function setStatus(message) {
        requestStatus.textContent = message;
    }

    
    // Keep the permission message synchronized with Django.
    function updatePermissionStatus() {

        // Do not update while disconnected or processing.
        if (!connected || busy || !permissionState) {
            return;
        }

        const state = permissionState.screen_share_state;

        const approved =
            permissionState.can_share_screen === true;

        const waiting = pendingRequestId !== null;

        // Show the creator's permission status.
        if (isMeetingCreator) {

            const count = Array.isArray(permissionState.pending_requests)
                ? permissionState.pending_requests.length
                : 0;

            if (state !== "idle") {

                setStatus(
                    "Screen-sharing permission is currently assigned."
                );

            } else if (count > 0) {

                setStatus(
                    `${count} screen-sharing request${count === 1 ? "" : "s"} waiting for approval.`
                );

            } else {

                setStatus(
                    "No pending screen-sharing requests."
                );
            }

            return;
        }

        // Developer B has received approval.
        if (approved) {

            setStatus(
                "Permission approved. You can share your screen."
            );

            return;
        }

        // Developer B is waiting for approval.
        if (waiting) {

            setStatus(
                "Request submitted. Waiting for the meeting creator."
            );

            return;
        }

        // Another developer currently has permission.
        if (state !== "idle") {

            setStatus(
                "Screen sharing is currently unavailable."
            );

            return;
        }

        // Nobody is sharing, and Developer B can request.
        setStatus(
            "You can request permission to share your screen."
        );
    }

    function buildRequestUrl(template, requestId) {
        const id = Number(requestId);

        if (!Number.isSafeInteger(id) || id <= 0) {
            throw new Error("Invalid screen-sharing request ID.");
        }

        const url = template.replace(
            /\/0\/(?=approve\/|reject\/|cancel\/)/,
            `/${encodeURIComponent(id)}/`
        );

        if (url === template) {
            throw new Error("Invalid screen-sharing URL configuration.");
        }

        return url;
    }

    function isCurrentConnection(generation) {
        return connected && generation === connectionGeneration;
    }

    // -----------------------------------------------------
    // 7. MEMBER CONTROLS
    // -----------------------------------------------------

    function updateMemberControls() {
        const isMember = connected && !isMeetingCreator;

        const hasPendingRequest = pendingRequestId !== null;

        const sharingAvailable =
            permissionState?.screen_share_state === "idle";

        const approvedToShare =
            permissionState?.can_share_screen === true;

        memberActions.hidden = !isMember;

        requestButton.hidden =
            hasPendingRequest || approvedToShare;

        cancelButton.hidden = !hasPendingRequest;

        requestButton.disabled =
            !isMember ||
            busy ||
            hasPendingRequest ||
            !sharingAvailable ||
            approvedToShare;

        cancelButton.disabled =
            !isMember ||
            busy ||
            !hasPendingRequest;
    }

    // -----------------------------------------------------
    // 8. CREATOR REQUESTS
    // -----------------------------------------------------

    function clearCreatorRequests() {
        requestList.replaceChildren();
        noRequests.hidden = false;
    }

    function renderCreatorRequests(requests) {
        clearCreatorRequests();

        if (!Array.isArray(requests) || requests.length === 0) {
            return;
        }

        noRequests.hidden = true;

        for (const request of requests) {
            const fragment = requestTemplate.content.cloneNode(true);

            const name = fragment.querySelector(
                ".livekit-screen-share-request-name"
            );

            const approveButton = fragment.querySelector(
                ".livekit-approve-screen-share"
            );

            const rejectButton = fragment.querySelector(
                ".livekit-reject-screen-share"
            );

            if (!name || !approveButton || !rejectButton) {
                continue;
            }

            // Prevent HTML injection from usernames.
            name.textContent =
                request.requested_by__username || "Group member";

            approveButton.disabled =
                !APPROVAL_ENABLED ||
                busy ||
                permissionState?.screen_share_state !== "idle";

            approveButton.title = APPROVAL_ENABLED
                ? "Approve this screen-sharing request."
                : "Approval is unavailable until security checks are complete.";

            approveButton.addEventListener("click", () => {
                approveScreenSharingRequest(request.id);
            });

            rejectButton.disabled = busy;

            rejectButton.addEventListener("click", () => {
                rejectScreenSharingRequest(request.id);
            });

            requestList.appendChild(fragment);
        }
    }

    // -----------------------------------------------------
    // 9. UPDATE INTERFACE
    // -----------------------------------------------------

    function updatePermissionInterface() {
        permissionSection.hidden = !connected;

        if (!connected) {
            memberActions.hidden = true;
            creatorRequests.hidden = true;
            clearCreatorRequests();
            return;
        }

        creatorRequests.hidden = !isMeetingCreator;

        updateMemberControls();

        if (isMeetingCreator) {
            renderCreatorRequests(
                permissionState?.pending_requests || []
            );
        } else {
            clearCreatorRequests();
        }
    }

    // -----------------------------------------------------
    // 10. REFRESH PERMISSIONS
    // -----------------------------------------------------

    async function refreshPermissionState() {
        if (!connected) {
            return;
        }

        const generation = connectionGeneration;

        try {
            const data = await getPermissionState();

            if (!isCurrentConnection(generation)) {
                return;
            }

            if (
                meetingId !== null &&
                String(data.meeting_id) !== String(meetingId)
            ) {
                permissionState = null;

                setStatus(
                    "Meeting permissions changed. Rejoin the meeting."
                );

                updatePermissionInterface();
                return;
            }

            permissionState = data;

            isMeetingCreator =
                data.is_meeting_creator === true;

            pendingRequestId =
                data.my_pending_request_id ?? null;

            updatePermissionInterface();

            updatePermissionStatus();

            // Notify the LiveKit UI.
            // This event does not grant publishing permission.
            document.dispatchEvent(
                new CustomEvent(
                    "codeview:screen-share-permission-changed",
                    {
                        detail: {
                            meetingId: data.meeting_id,
                            canShareScreen:
                                data.can_share_screen === true,
                            isMeetingCreator:
                                data.is_meeting_creator === true,
                            screenShareState:
                                data.screen_share_state,
                        },
                    }
                )
            );

        } catch (error) {
            if (!isCurrentConnection(generation)) {
                return;
            }

            console.error(
                "CodeView permission refresh error:",
                error
            );

            setStatus(
                error.message || "Unable to refresh permissions."
            );
        }
    }

    // -----------------------------------------------------
    // 11. REQUEST SCREEN SHARING
    // -----------------------------------------------------

    async function requestScreenSharing() {
        if (
            !connected ||
            isMeetingCreator ||
            busy ||
            pendingRequestId !== null ||
            permissionState?.screen_share_state !== "idle"
        ) {
            return;
        }

        busy = true;

        const generation = connectionGeneration;

        updatePermissionInterface();
        setStatus("Submitting screen-sharing request...");

        try {
            const data = await postRequest(requestUrl);

            if (!data.request || data.request.id == null) {
                throw new Error(
                    "The server did not return a request ID."
                );
            }

            if (!isCurrentConnection(generation)) {
                return;
            }

            pendingRequestId = data.request.id;

            setStatus(
                "Request submitted. Waiting for the meeting creator."
            );

            await refreshPermissionState();

        } catch (error) {
            if (isCurrentConnection(generation)) {
                console.error(
                    "CodeView screen-sharing request error:",
                    error
                );

                setStatus(
                    error.message || "Unable to request screen sharing."
                );
            }

        } finally {
            busy = false;

            updatePermissionInterface();

            updatePermissionStatus();
        }
    }

    // -----------------------------------------------------
    // 12. CANCEL REQUEST
    // -----------------------------------------------------

    async function cancelScreenSharingRequest() {
        if (
            !connected ||
            busy ||
            pendingRequestId === null
        ) {
            return;
        }

        busy = true;

        const generation = connectionGeneration;

        updatePermissionInterface();
        setStatus("Cancelling request...");

        try {
            const url = buildRequestUrl(
                cancelUrlTemplate,
                pendingRequestId
            );

            await postRequest(url);

            if (!isCurrentConnection(generation)) {
                return;
            }

            pendingRequestId = null;

            setStatus("Screen-sharing request cancelled.");

            await refreshPermissionState();

        } catch (error) {
            if (isCurrentConnection(generation)) {
                console.error("CodeView cancellation error:", error);

                setStatus(
                    error.message || "Unable to cancel request."
                );
            }

        } finally {
            busy = false;
            updatePermissionInterface();
            updatePermissionStatus();    
        }
    }

    // -----------------------------------------------------
    // 13. REJECT REQUEST
    // -----------------------------------------------------

    async function rejectScreenSharingRequest(requestId) {
        if (!connected || !isMeetingCreator || busy) {
            return;
        }

        busy = true;

        const generation = connectionGeneration;

        updatePermissionInterface();
        setStatus("Rejecting screen-sharing request...");

        try {
            const url = buildRequestUrl(
                rejectUrlTemplate,
                requestId
            );

            await postRequest(url);

            if (!isCurrentConnection(generation)) {
                return;
            }

            setStatus("Screen-sharing request rejected.");

            await refreshPermissionState();

        } catch (error) {
            if (isCurrentConnection(generation)) {
                console.error("CodeView rejection error:", error);

                setStatus(
                    error.message || "Unable to reject request."
                );
            }

        } finally {
            busy = false;
            updatePermissionInterface();
            updatePermissionStatus();
        }
    }

    // -----------------------------------------------------
    // 14. APPROVE REQUEST
    // -----------------------------------------------------

    async function approveScreenSharingRequest(requestId) {
        // Approval remains disabled until the backend
        // reconnection and recovery safeguards are complete.
        if (
            !APPROVAL_ENABLED ||
            !connected ||
            !isMeetingCreator ||
            busy ||
            permissionState?.screen_share_state !== "idle"
        ) {
            return;
        }

        busy = true;

        const generation = connectionGeneration;

        updatePermissionInterface();
        setStatus("Approving screen-sharing request...");

        try {
            const url = buildRequestUrl(
                approveUrlTemplate,
                requestId
            );

            await postRequest(url);

            if (!isCurrentConnection(generation)) {
                return;
            }

            setStatus("Screen-sharing request approved.");

            await refreshPermissionState();

        } catch (error) {
            if (isCurrentConnection(generation)) {
                console.error("CodeView approval error:", error);

                setStatus(
                    error.message || "Unable to approve request."
                );
            }

        } finally {
            busy = false;
            updatePermissionInterface();
            updatePermissionStatus();
        }
    }

    // -----------------------------------------------------
    // 15. POLLING
    // -----------------------------------------------------

    function stopPolling() {
        if (pollingTimer !== null) {
            clearInterval(pollingTimer);
            pollingTimer = null;
        }
    }

    function startPolling() {
        stopPolling();

        pollingTimer = setInterval(
            refreshPermissionState,
            POLLING_INTERVAL_MS
        );
    }

    // -----------------------------------------------------
    // 16. LIVEKIT CONNECTION EVENTS
    // -----------------------------------------------------

    document.addEventListener(
        "codeview:meeting-connected",
        async (event) => {
            connectionGeneration += 1;

            connected = true;

            meetingId = event.detail?.meetingId ?? null;

            isMeetingCreator =
                event.detail?.isMeetingCreator === true;

            pendingRequestId = null;
            permissionState = null;
            busy = false;

            setStatus("Loading screen-sharing permissions...");

            updatePermissionInterface();

            await refreshPermissionState();

            if (connected) {
                startPolling();
            }
        }
    );

    document.addEventListener(
        "codeview:meeting-disconnected",
        () => {
            connectionGeneration += 1;

            connected = false;
            meetingId = null;
            isMeetingCreator = false;
            pendingRequestId = null;
            permissionState = null;
            busy = false;

            stopPolling();

            setStatus("");
            updatePermissionInterface();
        }
    );

    // -----------------------------------------------------
    // 17. BUTTON EVENTS
    // -----------------------------------------------------

    requestButton.addEventListener(
        "click",
        requestScreenSharing
    );

    cancelButton.addEventListener(
        "click",
        cancelScreenSharingRequest
    );

    // -----------------------------------------------------
    // 18. INITIALIZE
    // -----------------------------------------------------

    updatePermissionInterface();

    console.log(
        "CodeView screen-sharing request controller initialized."
    );
});