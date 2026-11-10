"use strict";

/*
 * CodeView — Private Group Meeting Notifications
 *
 * Responsibilities:
 * 1. Connect to the group's meeting notification WebSocket.
 * 2. Display a Join Meeting alert when a meeting starts.
 * 3. Hide the alert when that meeting ends.
 * 4. Reconnect after temporary network interruptions.
 *
 * Security:
 * - Django Channels authorizes WebSocket connections.
 * - This file never handles LiveKit API secrets or room tokens.
 * - The meeting page must independently authorize joining.
 */

document.addEventListener("DOMContentLoaded", () => {
    // ---------------------------------------------------------
    // 1. FIND THE EXISTING HTML ELEMENTS
    // ---------------------------------------------------------

    const socketUrl = document.body.dataset.meetingNotificationSocketUrl;

    const notification = document.getElementById(
        "group-meeting-notification"
    );

    const title = document.getElementById(
        "group-meeting-notification-title"
    );

    const message = document.getElementById(
        "group-meeting-notification-message"
    );

    const joinButton = document.getElementById(
        "group-meeting-notification-join"
    );

    const dismissButton = document.getElementById(
        "group-meeting-notification-dismiss"
    );

    // Public groups and non-members have no meeting notification UI.
    if (
        !socketUrl ||
        !notification ||
        !title ||
        !message ||
        !joinButton ||
        !dismissButton
    ) {
        return;
    }

    // ---------------------------------------------------------
    // 2. CONNECTION STATE
    // ---------------------------------------------------------

    let socket = null;

    let reconnectTimer = null;

    let reconnectAttempts = 0;

    let activeMeetingId = null;

    let dismissedMeetingId = null;

    let shouldReconnect = true;

    const MAX_RECONNECT_DELAY = 30000;

    // ---------------------------------------------------------
    // 3. SHOW A MEETING NOTIFICATION
    // ---------------------------------------------------------

    function showMeetingNotification(data) {
        const meetingId = String(data.meeting_id);

        // Do not redisplay a meeting the developer already dismissed.
        if (dismissedMeetingId === meetingId) {
            return;
        }

        activeMeetingId = meetingId;

        title.textContent = "🔴 Group Meeting Started";

        message.textContent =
            "A developer has started a voice/video meeting.";

        /*
         * The HTML already contains a Django-generated meeting URL.
         * Keep that trusted URL rather than inserting an arbitrary
         * URL received over the WebSocket.
         */

        joinButton.textContent = "Join Meeting";

        notification.hidden = false;
    }

    // ---------------------------------------------------------
    // 4. HIDE A MEETING NOTIFICATION
    // ---------------------------------------------------------

    function hideMeetingNotification() {
        notification.hidden = true;

        activeMeetingId = null;
    }

    // ---------------------------------------------------------
    // 5. PROCESS WEBSOCKET EVENTS
    // ---------------------------------------------------------

    function handleMeetingEvent(data) {
        if (!data || typeof data !== "object") {
            return;
        }

        if (data.meeting_id === undefined || data.meeting_id === null) {
            return;
        }

        if (data.type === "meeting_started") {
            showMeetingNotification(data);
            return;
        }

        if (data.type === "meeting_ended") {
            const endedMeetingId = String(data.meeting_id);

            /*
             * Only hide the alert for the meeting that ended.
             * An old event must not remove a newer meeting alert.
             */

            if (activeMeetingId === endedMeetingId) {
                hideMeetingNotification();
            }

            if (dismissedMeetingId === endedMeetingId) {
                dismissedMeetingId = null;
            }
        }
    }

    // ---------------------------------------------------------
    // 6. RECONNECT WITH EXPONENTIAL BACKOFF
    // ---------------------------------------------------------

    function scheduleReconnect() {
        if (!shouldReconnect || reconnectTimer !== null) {
            return;
        }

        reconnectAttempts += 1;

        const delay = Math.min(
            1000 * Math.pow(2, reconnectAttempts - 1),
            MAX_RECONNECT_DELAY
        );

        reconnectTimer = window.setTimeout(() => {
            reconnectTimer = null;
            connectWebSocket();
        }, delay);
    }

    // ---------------------------------------------------------
    // 7. CONNECT TO DJANGO CHANNELS
    // ---------------------------------------------------------

    function connectWebSocket() {
        if (!shouldReconnect) {
            return;
        }

        // Avoid creating multiple simultaneous connections.
        if (
            socket &&
            (
                socket.readyState === WebSocket.OPEN ||
                socket.readyState === WebSocket.CONNECTING
            )
        ) {
            return;
        }

        let connection;

        try {
            connection = new WebSocket(socketUrl);
        } catch (error) {
            console.error(
                "CodeView: Unable to open meeting notification socket.",
                error
            );

            scheduleReconnect();
            return;
        }

        socket = connection;

        connection.addEventListener("open", () => {
            if (socket !== connection) {
                return;
            }

            reconnectAttempts = 0;

            console.info(
                "CodeView: Meeting notification connection established."
            );
        });

        connection.addEventListener("message", (event) => {
            if (socket !== connection) {
                return;
            }

            try {
                const data = JSON.parse(event.data);

                handleMeetingEvent(data);
            } catch (error) {
                console.error(
                    "CodeView: Invalid meeting notification received.",
                    error
                );
            }
        });

        connection.addEventListener("close", (event) => {
            if (socket !== connection) {
                return;
            }

            socket = null;

            /*
             * 4401 = authentication required
             * 4403 = membership/access denied
             *
             * Do not reconnect indefinitely when the server
             * explicitly rejects the developer's access.
             */

            if (event.code === 4401 || event.code === 4403) {
                shouldReconnect = false;
                hideMeetingNotification();
                return;
            }

            scheduleReconnect();
        });

        connection.addEventListener("error", () => {
            console.warn(
                "CodeView: Meeting notification connection interrupted."
            );

            // The close handler will schedule reconnection.
            connection.close();
        });
    }

    // ---------------------------------------------------------
    // 8. DISMISS BUTTON
    // ---------------------------------------------------------

    dismissButton.addEventListener("click", () => {
        if (activeMeetingId !== null) {
            dismissedMeetingId = activeMeetingId;
        }

        hideMeetingNotification();
    });

    // ---------------------------------------------------------
    // 9. CLEAN UP WHEN LEAVING THE PAGE
    // ---------------------------------------------------------

    window.addEventListener("pagehide", () => {
        shouldReconnect = false;

        if (reconnectTimer !== null) {
            window.clearTimeout(reconnectTimer);
            reconnectTimer = null;
        }

        if (socket) {
            socket.close();
            socket = null;
        }
    });

    // ---------------------------------------------------------
    // 10. START LISTENING
    // ---------------------------------------------------------

    connectWebSocket();
});