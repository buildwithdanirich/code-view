/*
 * CodeView — Real-Time GitHub Repository Synchronization
 *
 * Responsibilities:
 * 1. Connect to the group's repository update WebSocket.
 * 2. Detect successful repository connections or replacements.
 * 3. Automatically refresh the meeting room.
 * 4. Reconnect after temporary WebSocket failures.
 * 5. Stop reconnecting when access is denied.
 *
 * Security:
 * - Django verifies group membership.
 * - The WebSocket event contains no GitHub credentials.
 * - Repository files are accessed through protected Django views.
 */

document.addEventListener("DOMContentLoaded", () => {

    // ========================================================
    // 1. GET THE REPOSITORY UPDATE WEBSOCKET URL
    // ========================================================

    const socketPath = (
        document.body.dataset.repositoryUpdateSocketUrl
    );

    // Do nothing if this page does not support repository updates.
    if (!socketPath) {
        return;
    }

    // ========================================================
    // 2. PREPARE THE WEBSOCKET CONNECTION
    // ========================================================

    // Use secure WebSockets when the website uses HTTPS.
    const protocol = window.location.protocol === "https:"
        ? "wss:"
        : "ws:";

    const socketUrl = (
        `${protocol}//${window.location.host}${socketPath}`
    );

    let repositorySocket = null;

    let reconnectTimer = null;

    let reconnectAttempts = 0;

    let pageIsClosing = false;

    // Prevent multiple reloads for the same event.
    let reloadScheduled = false;

    // ========================================================
    // 3. REFRESH THE MEETING ROOM
    // ========================================================

    function refreshMeetingRoom() {

        // Do not reload if the page is closing.
        if (pageIsClosing) {
            return;
        }

        // Avoid scheduling multiple reloads.
        if (reloadScheduled) {
            return;
        }

        reloadScheduled = true;

        console.log(
            "GitHub repository changed. Refreshing meeting room."
        );

        // Reload the meeting room so Django renders the
        // latest repository information and file explorer.
        window.location.reload();
    }

    // ========================================================
    // 4. HANDLE REPOSITORY UPDATE EVENTS
    // ========================================================

    function handleRepositoryUpdate(data) {

        // Ignore unrelated WebSocket events.
        if (
            !data ||
            data.type !== "repository_updated"
        ) {
            return;
        }

        // The backend has confirmed that the repository changed.
        refreshMeetingRoom();
    }

    // ========================================================
    // 5. CONNECT TO DJANGO CHANNELS
    // ========================================================

    function connectRepositoryUpdates() {

        // Do not reconnect after the page starts closing.
        if (pageIsClosing) {
            return;
        }

        // Create the WebSocket connection.
        repositorySocket = new WebSocket(socketUrl);

        repositorySocket.addEventListener("open", () => {

            console.log(
                "Repository synchronization WebSocket connected."
            );

            // Reset reconnect attempts after a successful connection.
            reconnectAttempts = 0;
        });

        repositorySocket.addEventListener("message", (event) => {

            let data;

            try {

                // Convert the incoming JSON into a JavaScript object.
                data = JSON.parse(event.data);

            } catch (error) {

                console.error(
                    "Invalid repository synchronization event.",
                    error
                );

                return;
            }

            // Process the repository update.
            handleRepositoryUpdate(data);
        });

        repositorySocket.addEventListener("close", (event) => {

            console.log(
                "Repository synchronization WebSocket disconnected."
            );

            if (pageIsClosing) {
                return;
            }

            // Do not reconnect after authentication
            // or authorization failures.
            if (
                event.code === 4401 ||
                event.code === 4403
            ) {
                return;
            }

            // Increase the delay between reconnection attempts.
            // Maximum delay: 30 seconds.
            reconnectAttempts += 1;

            const delay = Math.min(
                1000 * (2 ** Math.min(reconnectAttempts, 5)),
                30000
            );

            reconnectTimer = window.setTimeout(
                connectRepositoryUpdates,
                delay
            );
        });

        repositorySocket.addEventListener("error", () => {

            console.error(
                "Repository synchronization WebSocket error."
            );
        });
    }

    // ========================================================
    // 6. CLEAN UP WHEN THE PAGE CLOSES
    // ========================================================

    window.addEventListener("pagehide", () => {

        pageIsClosing = true;

        // Cancel pending reconnection attempts.
        if (reconnectTimer !== null) {
            window.clearTimeout(reconnectTimer);
        }

        // Close the WebSocket connection.
        if (repositorySocket) {
            repositorySocket.close();
        }
    });

    // ========================================================
    // 7. START REPOSITORY SYNCHRONIZATION
    // ========================================================

    connectRepositoryUpdates();

});