/*
 * CodeView — Real-Time Repository Notifications
 *
 * Responsibilities:
 * 1. Connect the group owner to the notification WebSocket.
 * 2. Receive new repository connection requests.
 * 3. Display notifications without refreshing.
 * 4. Allow the owner to open the existing approval section.
 * 5. Reconnect after temporary connection failures.
 *
 * Security:
 * The Django WebSocket consumer verifies group ownership.
 * JavaScript does not grant repository permissions.
 */

document.addEventListener("DOMContentLoaded", () => {

    // ========================================================
    // 1. FIND THE NOTIFICATION ELEMENTS
    // ========================================================

    const notificationPanel = document.getElementById(
        "repository-notification-panel"
    );

    const notificationMessage = document.getElementById(
        "repository-notification-message"
    );

    const notificationReview = document.getElementById(
        "repository-notification-review"
    );

    const notificationDismiss = document.getElementById(
        "repository-notification-dismiss"
    );

    const approvalSection = document.getElementById(
        "repository-approval-requests"
    );

    // The server-rendered owner-only interface supplies
    // the notification URL.
    const socketPath = document.body.dataset.repositoryNotificationSocketUrl;

    // Ordinary members do not have these elements or URL.
    if (
        !socketPath ||
        !notificationPanel ||
        !notificationMessage ||
        !notificationReview ||
        !notificationDismiss ||
        !approvalSection
    ) {
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

    // Remember notification IDs already displayed
    // during this page session.
    const receivedRequestIds = new Set();

    // ========================================================
    // 3. DISPLAY A REPOSITORY REQUEST
    // ========================================================

    function displayNotification(data) {

        // Only handle new repository request events.
        if (data.type !== "repository_request_created") {
            return;
        }

        const requestId = Number(data.request_id);

        // Reject malformed request IDs.
        if (
            !Number.isSafeInteger(requestId) ||
            requestId <= 0
        ) {
            return;
        }

        // Avoid showing the same event twice.
        if (receivedRequestIds.has(requestId)) {
            return;
        }

        receivedRequestIds.add(requestId);

        // Display the developer's username safely.
        const username = (
            typeof data.requested_by === "string"
                ? data.requested_by
                : "A group member"
        );

        notificationMessage.textContent = (
            `${username} requested permission to connect ` +
            "a GitHub repository."
        );

        notificationPanel.hidden = false;
    }

    // ========================================================
    // 4. CONNECT TO DJANGO CHANNELS
    // ========================================================

    function connectNotifications() {

        if (pageIsClosing) {
            return;
        }

        notificationSocket = new WebSocket(socketUrl);

        notificationSocket.addEventListener("open", () => {

            console.log(
                "Repository notification WebSocket connected."
            );

            reconnectAttempts = 0;
        });

        notificationSocket.addEventListener("message", (event) => {

            let data;

            try {
                data = JSON.parse(event.data);
            } catch (error) {
                console.error(
                    "Invalid repository notification received."
                );

                return;
            }

            displayNotification(data);
        });

        notificationSocket.addEventListener("close", (event) => {

            console.log(
                "Repository notification WebSocket disconnected."
            );

            // Do not reconnect when the page is closing.
            if (pageIsClosing) {
                return;
            }

            // Authentication and authorization failures
            // require a fresh page load or login.
            if (event.code === 4401 || event.code === 4403) {
                return;
            }

            // Gradually increase the reconnection delay.
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
                "Repository notification WebSocket error."
            );
        });
    }

    // ========================================================
    // 5. REVIEW THE REQUEST
    // ========================================================

    notificationReview.addEventListener("click", () => {

        // Hide the notification.
        notificationPanel.hidden = true;

        // Refresh the existing approval section from Django.
        // Django remains responsible for rendering the
        // current pending requests and their secure forms.
        window.location.reload();
    });

    // ========================================================
    // 6. DISMISS THE NOTIFICATION
    // ========================================================

    notificationDismiss.addEventListener("click", () => {

        // Hide the notification without changing the
        // request's pending status in PostgreSQL.
        notificationPanel.hidden = true;
    });

    // ========================================================
    // 7. CLEAN UP WHEN THE PAGE CLOSES
    // ========================================================

    window.addEventListener("pagehide", () => {

        pageIsClosing = true;

        if (reconnectTimer !== null) {
            window.clearTimeout(reconnectTimer);
        }

        if (notificationSocket) {
            notificationSocket.close();
        }
    });

    // Start listening for repository requests.
    connectNotifications();

});