/**
 * CodeView — Screen-Sharing Request Controller
 *
 * Responsibilities:
 * 1. Submit screen-sharing requests.
 * 2. Cancel pending requests.
 * 3. Display request status.
 * 4. Prepare creator approval/rejection controls.
 *
 * Security:
 * - Django validates group membership and permissions.
 * - This file never grants LiveKit publishing permissions.
 * - Approval remains disabled until the secure backend is ready.
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

    const requestUrl =
        panel.dataset.screenShareRequestUrl;

    const cancelUrlTemplate =
        panel.dataset.screenShareCancelUrlTemplate;

    const rejectUrlTemplate =
        panel.dataset.screenShareRejectUrlTemplate;

    if (
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
    // 3. REQUEST STATE
    // =====================================================

    let pendingRequestId = null;

    let busy = false;

    // The existing meeting controller manages LiveKit.
    // This controller only manages Django requests.

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
            .find((value) =>
                value.startsWith("csrftoken=")
            );

        if (!cookie) {
            return "";
        }

        return decodeURIComponent(
            cookie.substring("csrftoken=".length)
        );
    }

    // =====================================================
    // 5. SEND DJANGO REQUEST
    // =====================================================

    async function postRequest(url) {
        const response = await fetch(url, {
            method: "POST",

            credentials: "same-origin",

            headers: {
                "X-CSRFToken": getCsrfToken(),

                "X-Requested-With": "XMLHttpRequest"
            }
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
    // 6. STATUS MESSAGE
    // =====================================================

    function setStatus(message) {
        requestStatus.textContent = message;
    }

    // =====================================================
    // 7. UPDATE MEMBER BUTTONS
    // =====================================================

    function updateMemberControls() {
        const hasPendingRequest =
            pendingRequestId !== null;

        requestButton.hidden = hasPendingRequest;

        cancelButton.hidden = !hasPendingRequest;

        requestButton.disabled =
            busy || hasPendingRequest;

        cancelButton.disabled =
            busy || !hasPendingRequest;
    }

    // =====================================================
    // 8. REQUEST SCREEN SHARING
    // =====================================================

    async function requestScreenSharing() {
        if (busy || pendingRequestId !== null) {
            return;
        }

        busy = true;

        updateMemberControls();

        setStatus(
            "Submitting screen-sharing request..."
        );

        try {
            const data = await postRequest(
                requestUrl
            );

            if (
                !data.request ||
                data.request.id == null
            ) {
                throw new Error(
                    "The server did not return a request ID."
                );
            }

            pendingRequestId = data.request.id;

            setStatus(
                "Request submitted. Waiting for the meeting creator."
            );

        } catch (error) {
            console.error(
                "CodeView screen-sharing request error:",
                error
            );

            setStatus(
                error.message ||
                "Unable to request screen sharing."
            );

        } finally {
            busy = false;

            updateMemberControls();
        }
    }

    // =====================================================
    // 9. CANCEL SCREEN-SHARING REQUEST
    // =====================================================

    async function cancelScreenSharingRequest() {
        if (busy || pendingRequestId === null) {
            return;
        }

        busy = true;

        updateMemberControls();

        setStatus("Cancelling request...");

        try {
            const url = cancelUrlTemplate.replace(
                /\/0\/(?=$|[?#])/,
                `/${encodeURIComponent(pendingRequestId)}/`
            );

            if (url === cancelUrlTemplate) {
                throw new Error(
                    "Invalid cancellation URL configuration."
                );
            }

            await postRequest(url);

            pendingRequestId = null;

            setStatus(
                "Screen-sharing request cancelled."
            );

        } catch (error) {
            console.error(
                "CodeView cancellation error:",
                error
            );

            setStatus(
                error.message ||
                "Unable to cancel request."
            );

        } finally {
            busy = false;

            updateMemberControls();
        }
    }

    // =====================================================
    // 10. CREATOR REQUEST DISPLAY
    // =====================================================

    function clearCreatorRequests() {
        requestList.replaceChildren();

        noRequests.hidden = false;
    }

    /*
     * The creator's request list will be populated
     * after Django exposes the permission-status endpoint.
     *
     * Do not fabricate requests in the browser.
     *
     * Approval remains disabled until the LiveKit
     * permission transition is secure.
     */

    // =====================================================
    // 11. BUTTON EVENTS
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
    // 12. INITIALIZE
    // =====================================================

    updateMemberControls();

    clearCreatorRequests();

    console.log(
        "CodeView screen-sharing request controller initialized."
    );
});