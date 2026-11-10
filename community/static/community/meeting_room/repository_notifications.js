/*
 * CodeView — Real-Time Repository Connection Requests
 *
 * Responsibilities:
 * 1. Connect the group owner to the notification WebSocket.
 * 2. Detect new repository connection requests.
 * 3. Automatically update the owner's approval list.
 * 4. Preserve Django-generated Approve and Reject forms.
 * 5. Reconnect after temporary connection failures.
 *
 * Security:
 * - Django verifies group ownership.
 * - Django generates the approval/rejection URLs and CSRF tokens.
 * - JavaScript never grants repository permissions.
 */

document.addEventListener("DOMContentLoaded", () => {

    // ========================================================
    // 1. FIND THE OWNER'S APPROVAL SECTION
    // ========================================================

    const approvalSection = document.getElementById(
        "repository-approval-requests"
    );

    // Get the WebSocket URL provided by Django.
    const socketPath = (
        document.body.dataset.repositoryNotificationSocketUrl
    );

    // Only the group owner should have this section and URL.
    if (!socketPath || !approvalSection) {
        return;
    }

    // ========================================================
    // 2. PREPARE THE WEBSOCKET CONNECTION
    // ========================================================

    const protocol = window.location.protocol === "https:"
        ? "wss:"
        : "ws:";

    const socketUrl = (
        `${protocol}//${window.location.host}${socketPath}`
    );

    let notificationSocket = null;

    let reconnectTimer = null;

    let reconnectAttempts = 0;

    let pageIsClosing = false;

    // Prevent duplicate request events from triggering
    // unnecessary updates.
    const receivedRequestIds = new Set();

    // Prevent simultaneous requests to refresh the list.
    let refreshInProgress = false;

    // Remember whether another update is needed.
    let refreshAgain = false;

    // ========================================================
    // 3. FETCH THE LATEST REPOSITORY REQUESTS
    // ========================================================

    async function refreshApprovalSection() {

        // Avoid overlapping fetch requests.
        if (refreshInProgress) {
            refreshAgain = true;
            return;
        }

        refreshInProgress = true;

        try {

            // Request the latest meeting room HTML from Django.
            const response = await fetch(
                window.location.href,
                {
                    method: "GET",
                    credentials: "same-origin",
                    cache: "no-store",
                    redirect: "error",
                    headers: {
                        "X-Requested-With": "XMLHttpRequest",
                    },
                }
            );

            if (!response.ok) {
                throw new Error(
                    `Failed to refresh requests: ${response.status}`
                );
            }

            // Read the server-rendered meeting room.
            const html = await response.text();

            // Parse the HTML without changing the current page.
            const parser = new DOMParser();

            const updatedDocument = parser.parseFromString(
                html,
                "text/html"
            );

            // Find the latest repository approval section.
            const updatedSection = updatedDocument.getElementById(
                "repository-approval-requests"
            );

            // If the section is missing, do not change the page.
            if (!updatedSection) {
                throw new Error(
                    "Repository approval section was not found."
                );
            }

            // Stop if the owner has left the meeting room.
            if (pageIsClosing) {
                return;
            }

            // ====================================================
            // REMOVE THE OLD REQUEST CARDS
            // ====================================================

            const existingCards = approvalSection.querySelectorAll(
                ".repository-approval-request"
            );

            existingCards.forEach((card) => {
                card.remove();
            });

            // Remove the previous empty-state message.
            const emptyMessages = Array.from(
                approvalSection.children
            ).filter((element) => {

                return (
                    element.tagName === "P" &&
                    element.textContent.includes(
                        "No pending repository connection requests."
                    )
                );
            });

            emptyMessages.forEach((message) => {
                message.remove();
            });

            // ====================================================
            // INSERT THE LATEST REQUEST CARDS
            // ====================================================

            const updatedCards = updatedSection.querySelectorAll(
                ".repository-approval-request"
            );

            if (updatedCards.length > 0) {

                // Use the forms rendered by Django.
                // Their POST URLs and CSRF tokens remain intact.
                updatedCards.forEach((card) => {

                    const importedCard = document.importNode(
                        card,
                        true
                    );

                    approvalSection.appendChild(importedCard);
                });

            } else {

                // Display the empty state when no requests exist.
                const emptyMessage = document.createElement("p");

                emptyMessage.textContent = (
                    "No pending repository connection requests."
                );

                approvalSection.appendChild(emptyMessage);
            }

            console.log(
                "Repository connection requests updated."
            );

        } catch (error) {

            // Keep the existing list if the update fails.
            console.error(
                "Failed to update repository requests:",
                error
            );

        } finally {

            refreshInProgress = false;

            // Fetch again if another event arrived
            // while the previous request was running.
            if (refreshAgain && !pageIsClosing) {

                refreshAgain = false;

                refreshApprovalSection();
            }
        }
    }

    // ========================================================
    // 4. HANDLE NEW REPOSITORY REQUEST EVENTS
    // ========================================================

    function handleRepositoryRequest(data) {

        // Only process new repository request events.
        if (
            !data ||
            data.type !== "repository_request_created"
        ) {
            return;
        }

        const requestId = Number(data.request_id);

        // Ignore invalid request IDs.
        if (
            !Number.isSafeInteger(requestId) ||
            requestId <= 0
        ) {
            return;
        }

        // Ignore events already handled during this session.
        if (receivedRequestIds.has(requestId)) {
            return;
        }

        receivedRequestIds.add(requestId);

        // Automatically refresh the approval list.
        // No notification popup or extra buttons are needed.
        refreshApprovalSection();
    }

    // ========================================================
    // 5. CONNECT TO DJANGO CHANNELS
    // ========================================================

    function connectNotifications() {

        if (pageIsClosing) {
            return;
        }

        notificationSocket = new WebSocket(socketUrl);

        notificationSocket.addEventListener("open", () => {

            console.log(
                "Repository request WebSocket connected."
            );

            reconnectAttempts = 0;

            // Catch up on requests created while disconnected.
            refreshApprovalSection();
        });

        notificationSocket.addEventListener("message", (event) => {

            let data;

            try {

                data = JSON.parse(event.data);

            } catch (error) {

                console.error(
                    "Invalid repository request event."
                );

                return;
            }

            handleRepositoryRequest(data);
        });

        notificationSocket.addEventListener("close", (event) => {

            console.log(
                "Repository request WebSocket disconnected."
            );

            if (pageIsClosing) {
                return;
            }

            // Stop reconnecting after authorization failures.
            if (
                event.code === 4401 ||
                event.code === 4403
            ) {
                return;
            }

            // Increase the delay after each failed connection.
            reconnectAttempts += 1;

            const delay = Math.min(
                1000 * (2 ** Math.min(reconnectAttempts, 5)),
                30000
            );

            reconnectTimer = window.setTimeout(
                connectNotifications,
                delay
            );
        });

        notificationSocket.addEventListener("error", () => {

            console.error(
                "Repository request WebSocket error."
            );
        });
    }

    // ========================================================
    // 6. CLEAN UP WHEN THE PAGE CLOSES
    // ========================================================

    window.addEventListener("pagehide", () => {

        pageIsClosing = true;

        // Stop pending reconnection attempts.
        if (reconnectTimer !== null) {
            window.clearTimeout(reconnectTimer);
        }

        // Close the WebSocket connection.
        if (notificationSocket) {
            notificationSocket.close();
        }
    });

    // ========================================================
    // 7. START LISTENING
    // ========================================================

    connectNotifications();

});