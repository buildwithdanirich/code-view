/**
 * CodeView — Screen-Sharing Request Controller
 *
 * Responsibilities:
 * 1. Show screen-sharing controls to connected meeting members.
 * 2. Retrieve permission state from Django.
 * 3. Submit and cancel screen-sharing requests.
 * 4. Display pending requests to the meeting creator.
 * 5. Allow the creator to reject requests.
 * 6. Hide controls when the LiveKit connection ends.
 *
 * Security:
 * - Django validates membership and permissions.
 * - JavaScript never grants LiveKit publishing permissions.
 * - Screen-sharing approval remains disabled until secure
 *   LiveKit permission coordination is verified.
 */

document.addEventListener("DOMContentLoaded", () => {
    "use strict";

    // =====================================================
    // 1. HTML ELEMENTS
    // =====================================================

    const panel = document.getElementById(
        "livekit-meeting-panel"
    );

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
        console.error(
            "CodeView: Screen-sharing request elements are missing."
        );

        return;
    }

    // =====================================================
    // 2. DJANGO ENDPOINTS
    // =====================================================

    const stateUrl = panel.dataset.screenShareStateUrl;

    const requestUrl = panel.dataset.screenShareRequestUrl;

    const cancelUrlTemplate =
        panel.dataset.screenShareCancelUrlTemplate;

    const rejectUrlTemplate =
        panel.dataset.screenShareRejectUrlTemplate;

    if (
        !stateUrl ||
        !requestUrl ||
        !cancelUrlTemplate ||
        !rejectUrlTemplate
    ) {
        console.error(
            "CodeView: Screen-sharing endpoints are missing."
        );

        return;
    }

    // =====================================================
    // 3. CONTROLLER STATE
    // =====================================================

    let connected = false;

    let meetingId = null;

    let isMeetingCreator = false;

    let pendingRequestId = null;

    let busy = false;

    let permissionState = null;

    let pollingTimer = null;

    let connectionGeneration = 0;

    const POLLING_INTERVAL_MS = 3000;

    // =====================================================
    // 4. CSRF PROTECTION
    // =====================================================

    function getCsrfToken() {
        const input = document.querySelector(
            'input[name="csrfmiddlewaretoken"]'
        );

        if (input && input.value) {
            return input.value;
        }

        const cookie = document.cookie
            .split(";")
            .map((value) => value.trim())
            .find((value) => value.startsWith("csrftoken="));

        if (!cookie) {
            return "";
        }

        return decodeURIComponent(
            cookie.substring("csrftoken=".length)
        );
    }

    // =====================================================
    // 5. HTTP REQUESTS
    // =====================================================

    async function getPermissionState() {
        const response = await fetch(stateUrl, {
            method: "GET",
            credentials: "same-origin",
            cache: "no-store",
            headers: {
                "X-Requested-With": "XMLHttpRequest",
            },
        });

        let data;

        try {
            data = await response.json();
        } catch {
            throw new Error(
                "The server returned an invalid response."
            );
        }

        if (!response.ok || data.success !== true) {
            throw new Error(
                data.error || "Unable to retrieve permissions."
            );
        }

        return data;
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

        let data;

        try {
            data = await response.json();
        } catch {
            throw new Error(
                "The server returned an invalid response."
            );
        }

        if (!response.ok || data.success !== true) {
            throw new Error(
                data.error || "The request failed."
            );
        }

        return data;
    }

    // =====================================================
    // 6. DISPLAY STATUS
    // =====================================================

    function setStatus(message) {
        requestStatus.textContent = message;
    }

    // =====================================================
    // 7. BUILD REQUEST URL
    // =====================================================

     function buildRequestUrl(template, requestId) {
        // Convert the request ID into a number.
        const id = Number(requestId);

        // Ensure the ID is a valid positive integer.
        if (!Number.isSafeInteger(id) || id <= 0) {
            throw new Error(
                "Invalid screen-sharing request ID."
            );
        }

        // Replace Django's placeholder with the actual request ID.
        const url = template.replace(
            /\/0\/(?=reject\/|cancel\/)/,
            `/${encodeURIComponent(id)}/`
        );

        // Ensure the URL was successfully updated.
        if (url === template) {
            throw new Error(
                "Invalid screen-sharing URL configuration."
            );
        }

        return url;
    }

    // =====================================================
    // 8. UPDATE MEMBER CONTROLS
    // =====================================================

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

    // =====================================================
    // 9. DISPLAY CREATOR REQUESTS
    // =====================================================

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

            if (
                !name ||
                !approveButton ||
                !rejectButton
            ) {
                continue;
            }

            // textContent prevents HTML injection from usernames.
            name.textContent =
                request.requested_by__username ||
                "Group member";

            // Approval remains disabled until the secure
            // LiveKit permission-granting flow is verified.
            approveButton.disabled = true;

            approveButton.title =
                "Approval is not available yet.";

            rejectButton.disabled = busy;

            rejectButton.addEventListener(
                "click",
                () => rejectScreenSharingRequest(request.id)
            );

            requestList.appendChild(fragment);
        }
    }

    // =====================================================
    // 10. UPDATE THE PERMISSION INTERFACE
    // =====================================================

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

    // =====================================================
    // 11. REFRESH PERMISSIONS FROM DJANGO
    // =====================================================

    async function refreshPermissionState() {
        if (!connected) {
            return;
        }

        const generation = connectionGeneration;

        try {
            const data = await getPermissionState();

            // Ignore responses from an earlier connection.
            if (
                !connected ||
                generation !== connectionGeneration
            ) {
                return;
            }

            // Never display permissions for another meeting.
            if (
                meetingId !== null &&
                String(data.meeting_id) !== String(meetingId)
            ) {
                setStatus(
                    "Meeting permissions changed. Rejoin the meeting."
                );

                permissionState = null;

                updatePermissionInterface();

                return;
            }

            permissionState = data;

            isMeetingCreator =
                data.is_meeting_creator === true;

            pendingRequestId =
                data.my_pending_request_id ?? null;

            updatePermissionInterface();

        } catch (error) {
            if (
                !connected ||
                generation !== connectionGeneration
            ) {
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

    // =====================================================
    // 12. SUBMIT SCREEN-SHARING REQUEST
    // =====================================================

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

        updateMemberControls();

        setStatus("Submitting screen-sharing request...");

        try {
            const data = await postRequest(requestUrl);

            if (
                !data.request ||
                data.request.id == null
            ) {
                throw new Error(
                    "The server did not return a request ID."
                );
            }

            if (
                !connected ||
                generation !== connectionGeneration
            ) {
                return;
            }

            pendingRequestId = data.request.id;

            setStatus(
                "Request submitted. Waiting for the meeting creator."
            );

            await refreshPermissionState();

        } catch (error) {
            if (
                connected &&
                generation === connectionGeneration
            ) {
                console.error(
                    "CodeView screen-sharing request error:",
                    error
                );

                setStatus(
                    error.message ||
                    "Unable to request screen sharing."
                );
            }

        } finally {
            busy = false;

            updateMemberControls();
        }
    }

    // =====================================================
    // 13. CANCEL SCREEN-SHARING REQUEST
    // =====================================================

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

        updateMemberControls();

        setStatus("Cancelling request...");

        try {
            const url = buildRequestUrl(
                cancelUrlTemplate,
                pendingRequestId
            );

            await postRequest(url);

            if (
                !connected ||
                generation !== connectionGeneration
            ) {
                return;
            }

            pendingRequestId = null;

            setStatus("Screen-sharing request cancelled.");

            await refreshPermissionState();

        } catch (error) {
            if (
                connected &&
                generation === connectionGeneration
            ) {
                console.error(
                    "CodeView cancellation error:",
                    error
                );

                setStatus(
                    error.message ||
                    "Unable to cancel request."
                );
            }

        } finally {
            busy = false;

            updateMemberControls();
        }
    }

    // =====================================================
    // 14. REJECT SCREEN-SHARING REQUEST
    // =====================================================

    async function rejectScreenSharingRequest(requestId) {
        if (
            !connected ||
            !isMeetingCreator ||
            busy
        ) {
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

            if (
                !connected ||
                generation !== connectionGeneration
            ) {
                return;
            }

            setStatus("Screen-sharing request rejected.");

            await refreshPermissionState();

        } catch (error) {
            if (
                connected &&
                generation === connectionGeneration
            ) {
                console.error(
                    "CodeView rejection error:",
                    error
                );

                setStatus(
                    error.message ||
                    "Unable to reject request."
                );
            }

        } finally {
            busy = false;

            updatePermissionInterface();
        }
    }

    // =====================================================
    // 15. POLLING
    // =====================================================

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

    // =====================================================
    // 16. LIVEKIT CONNECTION EVENTS
    // =====================================================

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

    // =====================================================
    // 17. BUTTON EVENTS
    // =====================================================

    requestButton.addEventListener(
        "click",
        requestScreenSharing
    );

    cancelButton.addEventListener(
        "click",
        cancelScreenSharingRequest
    );

    // =====================================================
    // 18. INITIALIZE
    // =====================================================

    updatePermissionInterface();

    console.log(
        "CodeView screen-sharing request controller initialized."
    );
});