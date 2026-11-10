/**
 * CodeView — LiveKit Video and Voice Meetings
 *
 * Features:
 * 1. Start a private group meeting.
 * 2. Join an existing group meeting.
 * 3. Prevent duplicate meetings during simultaneous requests.
 * 4. Display local and remote participants.
 * 5. Enable and disable microphone and camera.
 * 6. Leave without ending the meeting for everyone.
 * 7. Allow authorized developers to end the meeting.
 * 8. Clean up audio and video elements.
 *
 * Security:
 * - Django verifies group membership.
 * - Django generates LiveKit access tokens.
 * - Django controls who can end meetings.
 * - All meeting requests use POST and CSRF protection.
 */

import {
    Room,
    RoomEvent,
    Track,
} from "livekit-client";


document.addEventListener("DOMContentLoaded", () => {
    "use strict";

    // --------------------------------------------------
    // 1. GET HTML ELEMENTS
    // --------------------------------------------------

    const videoButton = document.getElementById(
        "livekit-video-call"
    );

    const voiceButton = document.getElementById(
        "livekit-voice-call"
    );

    const panel = document.getElementById(
        "livekit-meeting-panel"
    );

    const title = document.getElementById(
        "livekit-meeting-title"
    );

    const status = document.getElementById(
        "livekit-meeting-status"
    );

    const participants = document.getElementById(
        "livekit-participants"
    );

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


    // Stop if the meeting interface is not on this page.
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


    // --------------------------------------------------
    // 2. DJANGO MEETING ENDPOINTS
    // --------------------------------------------------

    const startUrl = panel.dataset.startUrl;
    const joinUrl = panel.dataset.joinUrl;
    const endUrl = panel.dataset.endUrl;

    if (!startUrl || !joinUrl || !endUrl) {
        console.error(
            "CodeView: LiveKit meeting URLs are missing."
        );

        status.textContent =
            "Meeting configuration is incomplete.";

        return;
    }


    // --------------------------------------------------
    // 3. MEETING STATE
    // --------------------------------------------------

    // Current LiveKit room connection.
    let room = null;

    // Prevent overlapping meeting actions.
    let busy = false;

    // Current meeting type: video or voice.
    let meetingMode = null;

    // Developer who created the meeting.
    let meetingCreatorId = null;

    // Permission supplied by Django.
    let canEndMeeting = false;

    // Track media elements attached to the page.
    const attachedMedia = new Map();


    // --------------------------------------------------
    // 4. READ DJANGO CSRF TOKEN
    // --------------------------------------------------

    function getCsrfToken() {

        // First check Django's existing forms.
        const csrfInput = document.querySelector(
            'input[name="csrfmiddlewaretoken"]'
        );

        if (csrfInput && csrfInput.value) {
            return csrfInput.value;
        }

        // Otherwise read the CSRF cookie.
        const cookie = document.cookie
            .split(";")
            .map((item) => item.trim())
            .find((item) => {
                return item.startsWith("csrftoken=");
            });

        if (!cookie) {
            return "";
        }

        return decodeURIComponent(
            cookie.substring("csrftoken=".length)
        );
    }


    // --------------------------------------------------
    // 5. SEND POST REQUEST TO DJANGO
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
            const error = new Error(
                "The server returned an invalid meeting response."
            );

            error.status = response.status;

            throw error;
        }

        if (!response.ok || data.success !== true) {

            const error = new Error(
                data.error || "The meeting request failed."
            );

            error.status = response.status;

            // Preserve Django's machine-readable error code.
            error.code = data.code || null;

            throw error;
        }

        return data;
    }


    // --------------------------------------------------
    // 6. DISPLAY MEETING STATUS
    // --------------------------------------------------

    function setStatus(message) {
        status.textContent = message;
    }


    // --------------------------------------------------
    // 7. CHECK CONNECTION
    // --------------------------------------------------

    function isConnected() {
        return (
            room !== null &&
            room.state === "connected"
        );
    }


    // --------------------------------------------------
    // 8. RESET MEETING PERMISSIONS
    // --------------------------------------------------

    function resetMeetingPermissions() {

        meetingCreatorId = null;

        canEndMeeting = false;

        meetingMode = null;
    }


    // --------------------------------------------------
    // 9. UPDATE BUTTONS
    // --------------------------------------------------

    function updateControls() {

        const connected = isConnected();

        const microphoneEnabled = (
            connected &&
            room.localParticipant.isMicrophoneEnabled
        );

        const cameraEnabled = (
            connected &&
            room.localParticipant.isCameraEnabled
        );

        // Media controls require an active connection.
        microphoneButton.disabled = !connected || busy;

        cameraButton.disabled = !connected || busy;

        leaveButton.disabled = !connected || busy;

        // Django provides the permission.
        // The backend still checks authorization.
        endButton.disabled = (
            !connected ||
            busy ||
            !canEndMeeting
        );

        microphoneButton.textContent = microphoneEnabled
            ? "🎙 Mute Microphone"
            : "🎙 Enable Microphone";

        cameraButton.textContent = cameraEnabled
            ? "📹 Turn Camera Off"
            : "📹 Turn Camera On";

        // Developers cannot start another connection
        // while they are already connected.
        videoButton.disabled = busy || connected;

        voiceButton.disabled = busy || connected;
    }


    // --------------------------------------------------
    // 10. UPDATE BUSY STATE
    // --------------------------------------------------

    function setBusy(value) {

        busy = value;

        updateControls();
    }


    // --------------------------------------------------
    // 11. SAVE MEETING PERMISSIONS
    // --------------------------------------------------

    function saveMeetingPermissions(credentials) {

        // Identify the meeting creator.
        meetingCreatorId = Number(
            credentials.started_by
        );

        // Django determines whether this developer
        // may end the meeting for everyone.
        canEndMeeting = (
            credentials.can_end_meeting === true
        );

        updateControls();
    }


    // --------------------------------------------------
    // 12. CLEAN UP ATTACHED MEDIA
    // --------------------------------------------------

    function cleanupMedia() {

        // Detach audio and video elements from their tracks.
        for (const [track, elements] of attachedMedia) {

            for (const element of elements) {

                try {
                    track.detach(element);
                } catch (error) {
                    console.warn(
                        "CodeView: Media detach failed.",
                        error
                    );
                }

                element.remove();
            }
        }

        attachedMedia.clear();

        // Remove participant tiles.
        participants.replaceChildren();
    }


    // --------------------------------------------------
    // 13. REGISTER ATTACHED MEDIA
    // --------------------------------------------------

    function registerMedia(track, element) {

        if (!attachedMedia.has(track)) {
            attachedMedia.set(track, new Set());
        }

        attachedMedia.get(track).add(element);
    }


    // --------------------------------------------------
    // 14. DISPLAY PARTICIPANTS
    // --------------------------------------------------

    function renderParticipants() {

        // Remove old media attachments before rebuilding.
        cleanupMedia();

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

            const isLocal = (
                participant === room.localParticipant
            );

            name.textContent = isLocal
                ? "You"
                : (
                    participant.name ||
                    participant.identity ||
                    "Developer"
                );

            tile.appendChild(name);

            const mediaContainer = document.createElement(
                "div"
            );

            mediaContainer.className =
                "livekit-participant-media";

            let hasVideo = false;

            for (
                const publication
                of participant.trackPublications.values()
            ) {

                const track = publication.track;

                if (!track || publication.isMuted) {
                    continue;
                }

                // ------------------------------------------
                // VIDEO
                // ------------------------------------------

                if (track.kind === Track.Kind.Video) {

                    const videoElement = track.attach();

                    videoElement.autoplay = true;

                    videoElement.playsInline = true;

                    // Prevent hearing yourself through
                    // locally attached media.
                    if (isLocal) {
                        videoElement.muted = true;
                    }

                    registerMedia(
                        track,
                        videoElement
                    );

                    mediaContainer.appendChild(
                        videoElement
                    );

                    hasVideo = true;
                }

                // ------------------------------------------
                // AUDIO
                // ------------------------------------------

                if (
                    track.kind === Track.Kind.Audio &&
                    !isLocal
                ) {

                    const audioElement = track.attach();

                    audioElement.autoplay = true;

                    registerMedia(
                        track,
                        audioElement
                    );

                    mediaContainer.appendChild(
                        audioElement
                    );
                }
            }

            // Show a placeholder when the camera is off.
            if (!hasVideo) {

                const placeholder = document.createElement(
                    "p"
                );

                placeholder.textContent = "Camera off";

                mediaContainer.appendChild(
                    placeholder
                );
            }

            tile.appendChild(mediaContainer);

            participants.appendChild(tile);
        }
    }


    // --------------------------------------------------
    // 15. REGISTER LIVEKIT EVENTS
    // --------------------------------------------------

    function registerRoomEvents(activeRoom) {

        // Refresh only when this is the current room.
        const refresh = () => {

            if (room !== activeRoom) {
                return;
            }

            renderParticipants();

            updateControls();
        };


        // A developer joins the meeting.
        activeRoom.on(
            RoomEvent.ParticipantConnected,
            refresh
        );

        // A developer leaves the meeting.
        activeRoom.on(
            RoomEvent.ParticipantDisconnected,
            refresh
        );

        // A media track becomes available.
        activeRoom.on(
            RoomEvent.TrackSubscribed,
            refresh
        );

        // A media track becomes unavailable.
        activeRoom.on(
            RoomEvent.TrackUnsubscribed,
            refresh
        );

        // A participant publishes media.
        activeRoom.on(
            RoomEvent.TrackPublished,
            refresh
        );

        // A participant stops publishing media.
        activeRoom.on(
            RoomEvent.TrackUnpublished,
            refresh
        );

        // Microphone or camera muted.
        activeRoom.on(
            RoomEvent.TrackMuted,
            refresh
        );

        // Microphone or camera unmuted.
        activeRoom.on(
            RoomEvent.TrackUnmuted,
            refresh
        );


        // ----------------------------------------------
        // ROOM DISCONNECTED
        // ----------------------------------------------

        activeRoom.on(
            RoomEvent.Disconnected,
            () => {

                if (room !== activeRoom) {
                    return;
                }

                cleanupMedia();

                room = null;

                resetMeetingPermissions();

                setStatus(
                    "Disconnected from meeting."
                );

                updateControls();
            }
        );
    }


    // --------------------------------------------------
    // 16. CONNECT TO LIVEKIT
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

            setStatus(
                "Connecting to LiveKit..."
            );

            // Establish the secure LiveKit connection.
            await newRoom.connect(
                serverUrl,
                accessToken
            );

            // Save permissions only after connecting.
            saveMeetingPermissions(credentials);

            // ------------------------------------------
            // ENABLE MICROPHONE
            // ------------------------------------------

            try {

                await newRoom.localParticipant
                    .setMicrophoneEnabled(true);

            } catch (error) {

                console.warn(
                    "CodeView: Microphone unavailable.",
                    error
                );

                setStatus(
                    "Connected. Microphone access is unavailable."
                );
            }


            // ------------------------------------------
            // ENABLE CAMERA FOR VIDEO CALLS
            // ------------------------------------------

            if (mode === "video") {

                try {

                    await newRoom.localParticipant
                        .setCameraEnabled(true);

                } catch (error) {

                    console.warn(
                        "CodeView: Camera unavailable.",
                        error
                    );

                    setStatus(
                        "Connected. Camera access is unavailable."
                    );
                }
            }

            title.textContent = (
                mode === "video"
                    ? "Video Meeting"
                    : "Voice Meeting"
            );

            renderParticipants();

            // Do not overwrite a device error with
            // a generic connection message.
            if (
                newRoom.localParticipant.isMicrophoneEnabled &&
                (
                    mode === "voice" ||
                    newRoom.localParticipant.isCameraEnabled
                )
            ) {

                setStatus(
                    "Connected to meeting."
                );
            }

            updateControls();

        } catch (error) {

            // Disconnect a partially established room.
            try {

                await newRoom.disconnect();

            } catch (disconnectError) {

                console.warn(
                    "CodeView: Disconnect failed.",
                    disconnectError
                );
            }

            cleanupMedia();

            if (room === newRoom) {
                room = null;
            }

            resetMeetingPermissions();

            updateControls();

            throw error;
        }
    }


    // --------------------------------------------------
    // 17. START OR JOIN A MEETING
    // --------------------------------------------------

    async function enterMeeting(mode) {

        if (busy || room) {
            return;
        }

        panel.hidden = false;

        setBusy(true);

        try {

            setStatus(
                "Checking for an active meeting..."
            );

            let credentials = null;

            // ------------------------------------------
            // FIRST: TRY JOINING AN EXISTING MEETING
            // ------------------------------------------

            try {

                const joinResponse = await postMeetingRequest(
                    joinUrl
                );

                credentials = joinResponse.meeting;

            } catch (error) {

                // Only start a meeting when Django explicitly
                // reports that no active meeting exists.
                if (
                    error.status !== 404 ||
                    error.code !== "no_active_meeting"
                ) {
                    throw error;
                }


                // --------------------------------------
                // SECOND: START A NEW MEETING
                // --------------------------------------

                setStatus(
                    "Starting a new meeting..."
                );

                try {

                    await postMeetingRequest(
                        startUrl
                    );

                } catch (startError) {

                    // Another developer may have started
                    // the meeting at the same time.
                    //
                    // Retry joining only if Django reports
                    // that an active meeting already exists.
                    //
                    // Never retry on permission errors.
                    const alreadyActive = (
                        startError.status === 400 &&
                        startError.message.includes(
                            "already has an active meeting"
                        )
                    );

                    if (!alreadyActive) {
                        throw startError;
                    }

                    setStatus(
                        "Another developer started the meeting. Joining..."
                    );
                }


                // --------------------------------------
                // THIRD: REQUEST LIVEKIT CREDENTIALS
                // --------------------------------------

                const joinResponse = await postMeetingRequest(
                    joinUrl
                );

                credentials = joinResponse.meeting;
            }


            // ------------------------------------------
            // CONNECT TO LIVEKIT
            // ------------------------------------------

            await connectToLiveKit(
                credentials,
                mode
            );

        } catch (error) {

            console.error(
                "CodeView meeting error:",
                error
            );

            setStatus(
                error.message ||
                "Unable to join meeting."
            );

            // Ensure a failed attempt does not leave
            // stale permissions or media elements.
            if (!isConnected()) {

                cleanupMedia();

                resetMeetingPermissions();
            }

        } finally {

            setBusy(false);
        }
    }


    // --------------------------------------------------
    // 18. TOGGLE MICROPHONE
    // --------------------------------------------------

    async function toggleMicrophone() {

        if (!isConnected() || busy) {
            return;
        }

        setBusy(true);

        try {

            const enabled = (
                room.localParticipant.isMicrophoneEnabled
            );

            await room.localParticipant
                .setMicrophoneEnabled(!enabled);

            renderParticipants();

        } catch (error) {

            console.error(
                "CodeView microphone error:",
                error
            );

            setStatus(
                error.message ||
                "Unable to update microphone."
            );

        } finally {

            setBusy(false);
        }
    }


    // --------------------------------------------------
    // 19. TOGGLE CAMERA
    // --------------------------------------------------

    async function toggleCamera() {

        if (!isConnected() || busy) {
            return;
        }

        setBusy(true);

        try {

            const enabled = (
                room.localParticipant.isCameraEnabled
            );

            await room.localParticipant
                .setCameraEnabled(!enabled);

            renderParticipants();

        } catch (error) {

            console.error(
                "CodeView camera error:",
                error
            );

            setStatus(
                error.message ||
                "Unable to update camera."
            );

        } finally {

            setBusy(false);
        }
    }


    // --------------------------------------------------
    // 20. LEAVE MEETING
    // --------------------------------------------------

    async function leaveMeeting() {

        if (!room || busy) {
            return;
        }

        setBusy(true);

        try {

            const currentRoom = room;

            // Leaving does not end the meeting for others.
            await currentRoom.disconnect();

            cleanupMedia();

            if (room === currentRoom) {
                room = null;
            }

            resetMeetingPermissions();

            setStatus(
                "You left the meeting."
            );

        } catch (error) {

            console.error(
                "CodeView leave meeting error:",
                error
            );

            setStatus(
                error.message ||
                "Unable to leave meeting."
            );

        } finally {

            setBusy(false);
        }
    }


    // --------------------------------------------------
    // 21. END MEETING FOR EVERYONE
    // --------------------------------------------------

    async function endMeeting() {

        if (
            !isConnected() ||
            busy ||
            !canEndMeeting
        ) {
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

            setStatus(
                "Ending meeting..."
            );

            // Django checks whether this developer
            // is authorized to end the meeting.
            await postMeetingRequest(
                endUrl
            );

            const currentRoom = room;

            // Disconnect this developer.
            if (currentRoom) {

                await currentRoom.disconnect();
            }

            cleanupMedia();

            room = null;

            resetMeetingPermissions();

            setStatus(
                "Meeting ended."
            );

        } catch (error) {

            console.error(
                "CodeView end meeting error:",
                error
            );

            setStatus(
                error.message ||
                "Unable to end meeting."
            );

        } finally {

            setBusy(false);
        }
    }


    // --------------------------------------------------
    // 22. CLOSE MEETING PANEL
    // --------------------------------------------------

    function closeMeetingPanel() {

        // Do not hide controls during an active call.
        if (isConnected()) {

            setStatus(
                "Leave the meeting before closing this panel."
            );

            return;
        }

        // Also prevent hiding the panel while connecting.
        if (busy) {
            return;
        }

        panel.hidden = true;
    }


    // --------------------------------------------------
    // 23. BUTTON EVENT LISTENERS
    // --------------------------------------------------

    videoButton.addEventListener(
        "click",
        () => {
            enterMeeting("video");
        }
    );

    voiceButton.addEventListener(
        "click",
        () => {
            enterMeeting("voice");
        }
    );

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

    closeButton.addEventListener(
        "click",
        closeMeetingPanel
    );


    // --------------------------------------------------
    // 24. INITIALIZE MEETING CONTROLS
    // --------------------------------------------------

    updateControls();

    console.log(
        "CodeView LiveKit meeting controls initialized."
    );
});