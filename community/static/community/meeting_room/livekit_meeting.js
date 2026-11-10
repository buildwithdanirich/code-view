/**
 * CodeView — LiveKit video and voice meetings.
 *
 * Responsibilities:
 * 1. Start or join a private group meeting through Django.
 * 2. Connect to LiveKit using credentials issued by Django.
 * 3. Display local and remote participants.
 * 4. Control microphone and camera.
 * 5. Leave without ending the meeting.
 * 6. End the meeting through Django when authorized.
 *
 * Security:
 * - Django checks group membership and meeting permissions.
 * - LiveKit access tokens are obtained from Django, not stored here.
 * - POST requests include Django's CSRF token.
 */

import {
    Room,
    RoomEvent,
    Track,
} from "livekit-client";


document.addEventListener("DOMContentLoaded", () => {
    "use strict";

    // --------------------------------------------------
    // 1. Find the existing HTML elements.
    // --------------------------------------------------

    const videoButton = document.getElementById("livekit-video-call");
    const voiceButton = document.getElementById("livekit-voice-call");
    const panel = document.getElementById("livekit-meeting-panel");

    const title = document.getElementById("livekit-meeting-title");
    const status = document.getElementById("livekit-meeting-status");
    const participants = document.getElementById("livekit-participants");

    const microphoneButton = document.getElementById(
        "livekit-toggle-microphone"
    );

    const cameraButton = document.getElementById(
        "livekit-toggle-camera"
    );

    const leaveButton = document.getElementById(
        "livekit-leave-meeting"
    );

    const endButton = document.getElementById(
        "livekit-end-meeting"
    );

    const closeButton = document.getElementById(
        "livekit-close-panel"
    );

    // Do nothing if this script loads on another page.
    if (
        !videoButton ||
        !voiceButton ||
        !panel ||
        !title ||
        !status ||
        !participants ||
        !microphoneButton ||
        !cameraButton ||
        !leaveButton ||
        !endButton ||
        !closeButton
    ) {
        return;
    }

    // Django endpoint URLs supplied by the HTML template.
    const startUrl = panel.dataset.startUrl;
    const joinUrl = panel.dataset.joinUrl;
    const endUrl = panel.dataset.endUrl;

    if (!startUrl || !joinUrl || !endUrl) {
        console.error("CodeView: Meeting URLs are missing.");
        status.textContent = "Meeting configuration is incomplete.";
        return;
    }

    // --------------------------------------------------
    // 2. Store the current meeting state.
    // --------------------------------------------------

    let room = null;
    let busy = false;
    let meetingMode = null;
    let meetingCreatorId = null;

    const currentUserId = Number(
        document.body.dataset.currentUserId
    );

    // A group owner may also end meetings. The backend
    // remains responsible for enforcing that permission.
    const isGroupOwner =
        panel.dataset.canEndMeeting === "true";

    // --------------------------------------------------
    // 3. Read Django's CSRF token.
    // --------------------------------------------------

    function getCsrfToken() {
        // Prefer the token rendered by Django in an existing form.
        const csrfInput = document.querySelector(
            'input[name="csrfmiddlewaretoken"]'
        );

        if (csrfInput && csrfInput.value) {
            return csrfInput.value;
        }

        // Fall back to Django's CSRF cookie.
        const cookie = document.cookie
            .split(";")
            .map((item) => item.trim())
            .find((item) => item.startsWith("csrftoken="));

        if (!cookie) {
            return "";
        }

        return decodeURIComponent(cookie.substring("csrftoken=".length));
    }

    // --------------------------------------------------
    // 4. Send a protected POST request to Django.
    // --------------------------------------------------

    async function postMeetingRequest(url) {
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
                "The server returned an invalid meeting response."
            );
        }

        if (!response.ok || data.success !== true) {
            const error = new Error(
                data.error || "The meeting request failed."
            );

            error.status = response.status;

            throw error;
        }

        return data;
    }

    // --------------------------------------------------
    // 5. Update the meeting interface.
    // --------------------------------------------------

    function setStatus(message) {
        status.textContent = message;
    }

    function updateControls() {
        const connected =
            room !== null &&
            room.state === "connected";

        const microphoneEnabled =
            connected &&
            room.localParticipant.isMicrophoneEnabled;

        const cameraEnabled =
            connected &&
            room.localParticipant.isCameraEnabled;

        microphoneButton.disabled = !connected || busy;
        cameraButton.disabled = !connected || busy;
        leaveButton.disabled = !connected || busy;

        // Django will perform the final permission check.
        const canEnd =
            isGroupOwner ||
            (
                meetingCreatorId !== null &&
                meetingCreatorId === currentUserId
            );

        endButton.disabled = !connected || busy || !canEnd;

        microphoneButton.textContent = microphoneEnabled
            ? "🎙 Mute Microphone"
            : "🎙 Enable Microphone";

        cameraButton.textContent = cameraEnabled
            ? "📹 Turn Camera Off"
            : "📹 Turn Camera On";

        videoButton.disabled = busy || connected;
        voiceButton.disabled = busy || connected;
    }

    function setBusy(value) {
        busy = value;
        updateControls();
    }

    // --------------------------------------------------
    // 6. Display participants and their media.
    // --------------------------------------------------

    function renderParticipants() {
        participants.replaceChildren();

        if (!room) {
            return;
        }

        const allParticipants = [
            room.localParticipant,
            ...room.remoteParticipants.values(),
        ];

        for (const participant of allParticipants) {
            const tile = document.createElement("div");
            tile.className = "livekit-participant";

            const name = document.createElement("strong");

            const isLocal =
                participant === room.localParticipant;

            name.textContent = isLocal
                ? "You"
                : (
                    participant.name ||
                    participant.identity ||
                    "Developer"
                );

            tile.appendChild(name);

            const mediaContainer = document.createElement("div");
            mediaContainer.className = "livekit-participant-media";

            let hasVideo = false;

            for (const publication of participant.trackPublications.values()) {
                const track = publication.track;

                if (!track || publication.isMuted) {
                    continue;
                }

                if (track.kind === Track.Kind.Video) {
                    const videoElement = track.attach();

                    videoElement.autoplay = true;
                    videoElement.playsInline = true;

                    if (isLocal) {
                        videoElement.muted = true;
                    }

                    mediaContainer.appendChild(videoElement);
                    hasVideo = true;
                }

                if (
                    track.kind === Track.Kind.Audio &&
                    !isLocal
                ) {
                    const audioElement = track.attach();

                    audioElement.autoplay = true;

                    mediaContainer.appendChild(audioElement);
                }
            }

            if (!hasVideo) {
                const placeholder = document.createElement("p");

                placeholder.textContent = "Camera off";

                mediaContainer.appendChild(placeholder);
            }

            tile.appendChild(mediaContainer);
            participants.appendChild(tile);
        }
    }

    // --------------------------------------------------
    // 7. Register LiveKit event listeners.
    // --------------------------------------------------

    function registerRoomEvents(activeRoom) {
        const refresh = () => {
            if (room === activeRoom) {
                renderParticipants();
                updateControls();
            }
        };

        activeRoom.on(RoomEvent.ParticipantConnected, refresh);
        activeRoom.on(RoomEvent.ParticipantDisconnected, refresh);

        activeRoom.on(RoomEvent.TrackSubscribed, refresh);
        activeRoom.on(RoomEvent.TrackUnsubscribed, refresh);

        activeRoom.on(RoomEvent.TrackPublished, refresh);
        activeRoom.on(RoomEvent.TrackUnpublished, refresh);
        activeRoom.on(RoomEvent.TrackMuted, refresh);
        activeRoom.on(RoomEvent.TrackUnmuted, refresh);

        activeRoom.on(RoomEvent.Disconnected, () => {
            if (room !== activeRoom) {
                return;
            }

            room = null;
            meetingMode = null;
            meetingCreatorId = null;

            participants.replaceChildren();

            setStatus("Disconnected from meeting.");
            updateControls();
        });
    }

    // --------------------------------------------------
    // 8. Connect to LiveKit.
    // --------------------------------------------------

    async function connectToLiveKit(credentials, mode) {
        const serverUrl = credentials.url;
        const accessToken = credentials.token;

        if (!serverUrl || !accessToken) {
            throw new Error(
                "Django did not return valid LiveKit credentials."
            );
        }

        const newRoom = new Room({
            adaptiveStream: true,
            dynacast: true,
        });

        room = newRoom;
        meetingMode = mode;

        registerRoomEvents(newRoom);

        try {
            setStatus("Connecting to LiveKit...");

            await newRoom.connect(serverUrl, accessToken);

            // Voice meetings start with the camera disabled.
            // Video meetings attempt to enable both devices.
            await newRoom.localParticipant.setMicrophoneEnabled(true);

            if (mode === "video") {
                await newRoom.localParticipant.setCameraEnabled(true);
            }

            title.textContent = mode === "video"
                ? "Video Meeting"
                : "Voice Meeting";

            setStatus("Connected to meeting.");

            renderParticipants();
        } catch (error) {
            await newRoom.disconnect();

            if (room === newRoom) {
                room = null;
                meetingMode = null;
            }

            throw error;
        }
    }

    // --------------------------------------------------
    // 9. Start or join a meeting.
    // --------------------------------------------------

    async function enterMeeting(mode) {
        if (busy || room) {
            return;
        }

        panel.hidden = false;
        setBusy(true);

        try {
            setStatus("Checking for an active meeting...");

            let startedMeeting = null;

            // First try joining an existing meeting.
            try {
                const joinResponse = await postMeetingRequest(joinUrl);

                await connectToLiveKit(
                    joinResponse.meeting,
                    mode
                );

                return;
            } catch (error) {
                // Only attempt to start a meeting when Django
                // reports that no meeting exists (404).
                // Do not bypass permission or validation errors.
                if (error.status !== 404) {
                    throw error;
                }
            }

            setStatus("Starting a new meeting...");

            const startResponse = await postMeetingRequest(startUrl);

            startedMeeting = startResponse.meeting;

            if (startedMeeting) {
                meetingCreatorId = Number(
                    startedMeeting.started_by
                );
            }

            // Starting creates the meeting; joining issues
            // the LiveKit URL and access token.
            const joinResponse = await postMeetingRequest(joinUrl);

            await connectToLiveKit(
                joinResponse.meeting,
                mode
            );
        } catch (error) {
            console.error("CodeView meeting error:", error);

            setStatus(error.message || "Unable to join meeting.");
        } finally {
            setBusy(false);
        }
    }

    // --------------------------------------------------
    // 10. Toggle the microphone.
    // --------------------------------------------------

    async function toggleMicrophone() {
        if (!room || busy) {
            return;
        }

        setBusy(true);

        try {
            const enabled =
                room.localParticipant.isMicrophoneEnabled;

            await room.localParticipant.setMicrophoneEnabled(
                !enabled
            );

            renderParticipants();
        } catch (error) {
            setStatus(error.message || "Microphone update failed.");
        } finally {
            setBusy(false);
        }
    }

    // --------------------------------------------------
    // 11. Toggle the camera.
    // --------------------------------------------------

    async function toggleCamera() {
        if (!room || busy) {
            return;
        }

        setBusy(true);

        try {
            const enabled =
                room.localParticipant.isCameraEnabled;

            await room.localParticipant.setCameraEnabled(
                !enabled
            );

            renderParticipants();
        } catch (error) {
            setStatus(error.message || "Camera update failed.");
        } finally {
            setBusy(false);
        }
    }

    // --------------------------------------------------
    // 12. Leave without ending the group meeting.
    // --------------------------------------------------

    async function leaveMeeting() {
        if (!room || busy) {
            return;
        }

        setBusy(true);

        try {
            const currentRoom = room;

            await currentRoom.disconnect();

            room = null;
            meetingMode = null;
            meetingCreatorId = null;

            participants.replaceChildren();

            setStatus("You left the meeting.");
        } finally {
            setBusy(false);
        }
    }

    // --------------------------------------------------
    // 13. End the meeting through Django.
    // --------------------------------------------------

    async function endMeeting() {
        if (!room || busy) {
            return;
        }

        const confirmed = window.confirm(
            "End this meeting for everyone?"
        );

        if (!confirmed) {
            return;
        }

        setBusy(true);

        try {
            setStatus("Ending meeting...");

            await postMeetingRequest(endUrl);

            const currentRoom = room;

            await currentRoom.disconnect();

            room = null;
            meetingMode = null;
            meetingCreatorId = null;

            participants.replaceChildren();

            setStatus("Meeting ended.");
        } catch (error) {
            setStatus(error.message || "Unable to end meeting.");
        } finally {
            setBusy(false);
        }
    }

    // --------------------------------------------------
    // 14. Connect the HTML buttons to their functions.
    // --------------------------------------------------

    videoButton.addEventListener("click", () => {
        enterMeeting("video");
    });

    voiceButton.addEventListener("click", () => {
        enterMeeting("voice");
    });

    microphoneButton.addEventListener(
        "click",
        toggleMicrophone
    );

    cameraButton.addEventListener(
        "click",
        toggleCamera
    );

    leaveButton.addEventListener(
        "click",
        leaveMeeting
    );

    endButton.addEventListener(
        "click",
        endMeeting
    );

    closeButton.addEventListener("click", () => {
        // Hiding the panel must not silently disconnect a call.
        panel.hidden = true;
    });

    // --------------------------------------------------
    // 15. Initialize the interface.
    // --------------------------------------------------

    updateControls();

    console.log("CodeView LiveKit meeting controls initialized.");
});