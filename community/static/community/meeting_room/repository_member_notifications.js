/*
 * CodeView — Member Repository Decision Notifications
 *
 * Responsibilities:
 * 1. Connect members to their private notification WebSocket.
 * 2. Listen for repository approval or rejection.
 * 3. Refresh the meeting room automatically.
 * 4. Reconnect after temporary network interruptions.
 *
 * Security:
 * Django verifies the authenticated user's membership.
 * JavaScript never grants repository permissions.
 */

document.addEventListener("DOMContentLoaded", () => {

    // ========================================================
    // 1. GET THE MEMBER'S WEBSOCKET URL
    // ========================================================

    const socketPath = (
        document.body.dataset.repositoryMemberNotificationSocketUrl
    );

    // Stop if the page does not provide a member notification URL.
    if (!socketPath) {
        return;
    }

    // Use secure WebSockets when the website uses HTTPS.
    const protocol = window.location.protocol === "https:"
        ? "wss:"
        : "ws:";

    const socketUrl = (
        `${protocol}//${window.location.host}${socketPath}`
    );

    // ========================================================
    // 2. CONNECTION STATE
    // ========================================================

    let notificationSocket = null;

    let reconnectTimer = null;

    let reconnectAttempts = 0;

    let pageIsClosing = false;

    // Prevent multiple refreshes from duplicate events.
    let refreshScheduled = false;

    // ========================================================
    // 3. HANDLE OWNER APPROVAL OR REJECTION
    // ========================================================

    function handleRepositoryDecision(data) {

        // Reject malformed events.
        if (!data || typeof data !== "object") {
            return;
        }

        // Only handle repository approval/rejection events.
        const validEvents = [
            "repository_request_approved",
            "repository_request_rejected",
        ];

        if (!validEvents.includes(data.type)) {
            return;
        }

        // Prevent duplicate page refreshes.
        if (refreshScheduled) {
            return;
        }

        refreshScheduled = true;

        console.log(
            "Repository decision received:",
            data.type
        );

        // Refresh the page to load the latest permissions
        // directly from Django and PostgreSQL.
        window.location.reload();
    }

    // ========================================================
    // 4. CONNECT TO DJANGO CHANNELS
    // ========================================================

    function connectNotifications() {

        // Do not reconnect after the page starts closing.
        if (pageIsClosing || refreshScheduled) {
            return;
        }

        notificationSocket = new WebSocket(socketUrl);

        // Connection established.
        notificationSocket.addEventListener("open", () => {

            console.log(
                "Member repository notification WebSocket connected."
            );

            reconnectAttempts = 0;
        });

        // Receive approval or rejection events.
        notificationSocket.addEventListener("message", (event) => {

            let data;

            try {
                data = JSON.parse(event.data);
            } catch (error) {

                console.error(
                    "Invalid member repository notification received."
                );

                return;
            }

            handleRepositoryDecision(data);
        });

        // Handle disconnected connections.
        notificationSocket.addEventListener("close", (event) => {

            console.log(
                "Member repository notification WebSocket disconnected."
            );

            if (pageIsClosing || refreshScheduled) {
                return;
            }

            // Authentication/authorization failures should
            // not trigger endless reconnection attempts.
            if (event.code === 4401 || event.code === 4403) {
                return;
            }

            // Exponential backoff prevents repeated rapid connections.
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

        // Report connection errors.
        notificationSocket.addEventListener("error", () => {

            console.error(
                "Member repository notification WebSocket error."
            );
        });
    }

    // ========================================================
    // 5. CLEAN UP WHEN THE PAGE CLOSES
    // ========================================================

    window.addEventListener("pagehide", () => {

        pageIsClosing = true;

        // Stop scheduled reconnections.
        if (reconnectTimer !== null) {
            window.clearTimeout(reconnectTimer);
        }

        // Close the existing WebSocket connection.
        if (notificationSocket) {
            notificationSocket.close();
        }
    });

    // ========================================================
    // 6. START LISTENING
    // ========================================================

    connectNotifications();

});