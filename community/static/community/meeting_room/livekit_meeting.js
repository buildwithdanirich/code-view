/**
 * CodeView — LiveKit Voice, Video and Screen Sharing
 *
 * Features:
 * - Start or join a private development group meeting.
 * - Voice and video calls.
 * - Microphone and camera controls.
 * - Screen sharing.
 * - Display local and remote participants.
 * - Leave without ending the meeting for everyone.
 * - End meetings with Django authorization.
 * - Handle participant connections and disconnections.
 * - Clean up media tracks and HTML elements.
 *
 * Security:
 * - Django verifies group membership.
 * - Django generates LiveKit access tokens.
 * - Django controls meeting termination permissions.
 * - POST requests use CSRF protection.
 */

import {
    Room,
    RoomEvent,
    Track,
} from "livekit-client";


document.addEventListener("DOMContentLoaded", () => {
    "use strict";

    // ==================================================
    // 1. HTML ELEMENTS
    // ==================================================

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

    const screenShareButton = document.getElementById(
        "livekit-toggle-screen-share"
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

    // Stop initialization if the interface is incomplete.
    if (
        !videoButton ||
        !voiceButton ||
        !panel ||
        !title ||
        !status ||
        !participants ||
        !microphoneButton ||
        !cameraButton ||
        !screenShareButton ||
        !leaveButton ||
        !endButton ||
        !closeButton
    ) {
        console.error(
            "CodeView: LiveKit interface elements are missing."
        );

        return;
    }


    // ==================================================
    // 2. DJANGO ENDPOINTS
    // ==================================================

    const startUrl = panel.dataset.startUrl;
    const joinUrl = panel.dataset.joinUrl;
    const endUrl = panel.dataset.endUrl;

    if (!startUrl || !joinUrl || !endUrl) {
        status.textContent =
            "Meeting configuration is incomplete.";

        return;
    }


    // ==================================================
    // 3. MEETING STATE
    // ==================================================

    let room = null;

    // Prevent simultaneous button actions.
    let busy = false;

    // Current meeting mode.
    let meetingMode = null;

    // Django supplies this permission.
    let canEndMeeting = false;

    // Store HTML elements associated with media tracks.
    const attachedMedia = new Map();

    // Store participant tiles without repeatedly rebuilding them.
    const participantTiles = new Map();


    // ==================================================
    // 4. CSRF TOKEN
    // ==================================================

    function getCsrfToken() {

        const csrfInput = document.querySelector(
            'input[name="csrfmiddlewaretoken"]'
        );

        if (csrfInput && csrfInput.value) {
            return csrfInput.value;
        }

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


    // ==================================================
    // 5. SEND REQUEST TO DJANGO
    // ==================================================

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
                data.error || "Meeting request failed."
            );

            error.status = response.status;
            error.code = data.code || null;

            throw error;
        }

        return data;
    }


    // ==================================================
    // 6. STATUS AND CONNECTION
    // ==================================================

    function setStatus(message) {
        status.textContent = message;
    }

    function isConnected() {
        return (
            room !== null &&
            room.state === "connected"
        );
    }

    function resetMeetingPermissions() {
        canEndMeeting = false;
        meetingMode = null;
    }


    // ==================================================
    // 7. UPDATE BUTTONS
    // ==================================================

    function updateControls() {

        const connected = isConnected();

        const localParticipant = connected
            ? room.localParticipant
            : null;

        const microphoneEnabled = Boolean(
            localParticipant &&
            localParticipant.isMicrophoneEnabled
        );

        const cameraEnabled = Boolean(
            localParticipant &&
            localParticipant.isCameraEnabled
        );

        const screenSharing = Boolean(
            localParticipant &&
            localParticipant.isScreenShareEnabled
        );

        microphoneButton.disabled = !connected || busy;
        cameraButton.disabled = !connected || busy;

        screenShareButton.disabled = !connected || busy;

        leaveButton.disabled = !connected || busy;

        endButton.disabled = (
            !connected ||
            busy ||
            !canEndMeeting
        );

        videoButton.disabled = busy || connected;
        voiceButton.disabled = busy || connected;

        microphoneButton.textContent = microphoneEnabled
            ? "🎙 Mute Microphone"
            : "🎙 Enable Microphone";

        cameraButton.textContent = cameraEnabled
            ? "📹 Turn Camera Off"
            : "📹 Turn Camera On";

        screenShareButton.textContent = screenSharing
            ? "🛑 Stop Sharing"
            : "🖥 Share Screen";

        screenShareButton.setAttribute(
            "aria-pressed",
            String(screenSharing)
        );
    }


    function setBusy(value) {
        busy = value;
        updateControls();
    }


    // ==================================================
    // 8. MEDIA MANAGEMENT
    // ==================================================

    function detachTrack(track) {

        const elements = attachedMedia.get(track);

        if (!elements) {
            return;
        }

        for (const element of elements) {

            try {
                track.detach(element);
            } catch (error) {
                console.warn(
                    "CodeView: Unable to detach media.",
                    error
                );
            }

            element.remove();
        }

        attachedMedia.delete(track);
    }


    function cleanupMedia() {

        for (const track of [...attachedMedia.keys()]) {
            detachTrack(track);
        }

        participantTiles.clear();
        participants.replaceChildren();
    }


    // ==================================================
    // 9. PARTICIPANT TILES
    // ==================================================

    function getParticipantTile(participant) {

        const identity = participant.identity;

        if (participantTiles.has(identity)) {
            return participantTiles.get(identity);
        }

        const tile = document.createElement("div");

        tile.className = "livekit-participant";

        tile.dataset.identity = identity;

        const name = document.createElement("strong");

        const isLocal = (
            room &&
            participant === room.localParticipant
        );

        name.textContent = isLocal
            ? "You"
            : (
                participant.name ||
                participant.identity ||
                "Developer"
            );

        const mediaContainer = document.createElement("div");

        mediaContainer.className =
            "livekit-participant-media";

        tile.appendChild(name);
        tile.appendChild(mediaContainer);

        participants.appendChild(tile);

        const tileData = {
            tile,
            mediaContainer,
        };

        participantTiles.set(identity, tileData);

        return tileData;
    }


    // ==================================================
    // 10. ATTACH MEDIA TRACK
    // ==================================================

    function attachParticipantTrack(
        participant,
        track,
        publication
    ) {

        if (!room || !track || publication.isMuted) {
            return;
        }

        // Do not attach the same track twice.
        if (attachedMedia.has(track)) {
            return;
        }

        const tileData = getParticipantTile(participant);

        const isLocal = (
            participant === room.localParticipant
        );

        // Do not play our own microphone audio.
        if (
            track.kind === Track.Kind.Audio &&
            isLocal
        ) {
            return;
        }

        const element = track.attach();

        element.autoplay = true;

        if (track.kind === Track.Kind.Video) {

            element.playsInline = true;

            if (isLocal) {
                element.muted = true;
            }

            // Distinguish screen sharing from camera video.
            if (
                publication.source === Track.Source.ScreenShare
            ) {

                element.classList.add(
                    "livekit-screen-share-video"
                );

                tileData.tile.classList.add(
                    "livekit-has-screen-share"
                );

            } else {

                element.classList.add(
                    "livekit-camera-video"
                );
            }
        }

        tileData.mediaContainer.appendChild(element);

        attachedMedia.set(track, new Set([element]));
    }


    // ==================================================
    // 11. SYNCHRONIZE PARTICIPANT MEDIA
    // ==================================================

    function syncParticipant(participant) {

        if (!room) {
            return;
        }

        const tileData = getParticipantTile(participant);

        const activeTracks = new Set();

        for (
            const publication
            of participant.trackPublications.values()
        ) {

            const track = publication.track;

            if (!track || publication.isMuted) {
                continue;
            }

            activeTracks.add(track);

            attachParticipantTrack(
                participant,
                track,
                publication
            );
        }

        // Remove media that is no longer published or active.
        for (
            const publication
            of participant.trackPublications.values()
        ) {

            const track = publication.track;

            if (
                track &&
                publication.isMuted &&
                attachedMedia.has(track)
            ) {
                detachTrack(track);
            }
        }

        // Show a placeholder when no video is available.
        const hasVideo = [...tileData.mediaContainer.children]
            .some((element) => {
                return element.tagName === "VIDEO";
            });

        let placeholder = tileData.mediaContainer.querySelector(
            ".livekit-camera-placeholder"
        );

        if (!hasVideo && !placeholder) {

            placeholder = document.createElement("p");

            placeholder.className =
                "livekit-camera-placeholder";

            placeholder.textContent = "Camera off";

            tileData.mediaContainer.appendChild(placeholder);

        } else if (hasVideo && placeholder) {

            placeholder.remove();
        }

        // Update screen-sharing presentation.
        const hasScreenShare = Boolean(
            tileData.mediaContainer.querySelector(
                ".livekit-screen-share-video"
            )
        );

        tileData.tile.classList.toggle(
            "livekit-has-screen-share",
            hasScreenShare
        );
    }


    function removeParticipant(participant) {

        const identity = participant.identity;

        const tileData = participantTiles.get(identity);

        if (!tileData) {
            return;
        }

        for (
            const publication
            of participant.trackPublications.values()
        ) {

            if (publication.track) {
                detachTrack(publication.track);
            }
        }

        tileData.tile.remove();

        participantTiles.delete(identity);
    }


    function syncAllParticipants() {

        if (!room) {
            return;
        }

        syncParticipant(room.localParticipant);

        for (
            const participant
            of room.remoteParticipants.values()
        ) {
            syncParticipant(participant);
        }
    }


    // ==================================================
    // 12. REGISTER LIVEKIT EVENTS
    // ==================================================

    function registerRoomEvents(activeRoom) {

        const refresh = (participant) => {

            if (room !== activeRoom) {
                return;
            }

            if (participant) {
                syncParticipant(participant);
            } else {
                syncAllParticipants();
            }

            updateControls();
        };


        // A developer joins.
        activeRoom.on(
            RoomEvent.ParticipantConnected,
            (participant) => {
                refresh(participant);
            }
        );


        // A developer leaves.
        activeRoom.on(
            RoomEvent.ParticipantDisconnected,
            (participant) => {

                if (room !== activeRoom) {
                    return;
                }

                removeParticipant(participant);
                updateControls();
            }
        );


        // A remote track becomes available.
        activeRoom.on(
            RoomEvent.TrackSubscribed,
            (track, publication, participant) => {

                if (room !== activeRoom) {
                    return;
                }

                attachParticipantTrack(
                    participant,
                    track,
                    publication
                );

                refresh(participant);
            }
        );


        // A remote track becomes unavailable.
        activeRoom.on(
            RoomEvent.TrackUnsubscribed,
            (track, publication, participant) => {

                if (room !== activeRoom) {
                    return;
                }

                detachTrack(track);
                refresh(participant);
            }
        );


        // A track is published.
        activeRoom.on(
            RoomEvent.TrackPublished,
            (publication, participant) => {
                refresh(participant);
            }
        );


        // A track is unpublished.
        activeRoom.on(
            RoomEvent.TrackUnpublished,
            (publication, participant) => {

                if (room !== activeRoom) {
                    return;
                }

                if (publication.track) {
                    detachTrack(publication.track);
                }

                refresh(participant);
            }
        );


        // Microphone, camera, or screen share is muted.
        activeRoom.on(
            RoomEvent.TrackMuted,
            (publication, participant) => {

                if (room !== activeRoom) {
                    return;
                }

                if (publication.track) {
                    detachTrack(publication.track);
                }

                refresh(participant);
            }
        );


        // Microphone, camera, or screen share is unmuted.
        activeRoom.on(
            RoomEvent.TrackUnmuted,
            (publication, participant) => {
                refresh(participant);
            }
        );


        // Local media publication changes.
        activeRoom.on(
            RoomEvent.LocalTrackPublished,
            () => {
                refresh(activeRoom.localParticipant);
            }
        );

        activeRoom.on(
            RoomEvent.LocalTrackUnpublished,
            () => {
                refresh(activeRoom.localParticipant);
            }
        );


        // Browser or LiveKit disconnects.
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


    // ==================================================
    // 13. CONNECT TO LIVEKIT
    // ==================================================

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

            await newRoom.connect(
                serverUrl,
                accessToken
            );

            // Django decides who can end the meeting.
            canEndMeeting = (
                credentials.can_end_meeting === true
            );

            let deviceError = false;

            // Enable microphone.
            try {

                await newRoom.localParticipant
                    .setMicrophoneEnabled(true);

            } catch (error) {

                deviceError = true;

                console.warn(
                    "CodeView: Microphone unavailable.",
                    error
                );
            }

            // Enable camera only for video meetings.
            if (mode === "video") {

                try {

                    await newRoom.localParticipant
                        .setCameraEnabled(true);

                } catch (error) {

                    deviceError = true;

                    console.warn(
                        "CodeView: Camera unavailable.",
                        error
                    );
                }
            }

            title.textContent = (
                mode === "video"
                    ? "Video Meeting"
                    : "Voice Meeting"
            );

            syncAllParticipants();

            if (deviceError) {

                setStatus(
                    "Connected. Some devices are unavailable."
                );

            } else {

                setStatus("Connected to meeting.");
            }

            updateControls();

        } catch (error) {

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


    // ==================================================
    // 14. START OR JOIN MEETING
    // ==================================================

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

            try {

                // Join an existing meeting first.
                const response = await postMeetingRequest(
                    joinUrl
                );

                credentials = response.meeting;

            } catch (error) {

                // Only create a meeting if none exists.
                if (
                    error.status !== 404 ||
                    error.code !== "no_active_meeting"
                ) {
                    throw error;
                }

                setStatus("Starting a new meeting...");

                try {

                    await postMeetingRequest(startUrl);

                } catch (startError) {

                    // Handle two developers starting together.
                    const alreadyActive = (
                        startError.status === 400 &&
                        startError.message.includes(
                            "already has an active meeting"
                        )
                    );

                    if (!alreadyActive) {
                        throw startError;
                    }
                }

                const response = await postMeetingRequest(
                    joinUrl
                );

                credentials = response.meeting;
            }

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

            if (!isConnected()) {
                cleanupMedia();
                resetMeetingPermissions();
            }

        } finally {

            setBusy(false);
        }
    }


    // ==================================================
    // 15. TOGGLE MICROPHONE
    // ==================================================

    async function toggleMicrophone() {

        if (!isConnected() || busy) {
            return;
        }

        setBusy(true);

        try {

            const local = room.localParticipant;

            await local.setMicrophoneEnabled(
                !local.isMicrophoneEnabled
            );

            syncParticipant(local);

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


    // ==================================================
    // 16. TOGGLE CAMERA
    // ==================================================

    async function toggleCamera() {

        if (!isConnected() || busy) {
            return;
        }

        setBusy(true);

        try {

            const local = room.localParticipant;

            await local.setCameraEnabled(
                !local.isCameraEnabled
            );

            syncParticipant(local);

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


    // ==================================================
    // 17. TOGGLE SCREEN SHARING
    // ==================================================

    async function toggleScreenSharing() {

        if (!isConnected() || busy) {
            return;
        }

        setBusy(true);

        try {

            const local = room.localParticipant;

            const currentlySharing = (
                local.isScreenShareEnabled
            );

            // LiveKit asks the browser to select a screen.
            await local.setScreenShareEnabled(
                !currentlySharing
            );

            syncParticipant(local);

            setStatus(
                local.isScreenShareEnabled
                    ? "You are sharing your screen."
                    : "Screen sharing stopped."
            );

        } catch (error) {

            console.error(
                "CodeView screen sharing error:",
                error
            );

            if (error.name === "NotAllowedError") {

                setStatus(
                    "Screen sharing was cancelled or denied."
                );

            } else {

                setStatus(
                    error.message ||
                    "Unable to share screen."
                );
            }

        } finally {

            setBusy(false);
        }
    }


    // ==================================================
    // 18. LEAVE MEETING
    // ==================================================

    async function leaveMeeting() {

        if (!room || busy) {
            return;
        }

        setBusy(true);

        try {

            const currentRoom = room;

            await currentRoom.disconnect();

            cleanupMedia();

            if (room === currentRoom) {
                room = null;
            }

            resetMeetingPermissions();

            setStatus("You left the meeting.");

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


    // ==================================================
    // 19. END MEETING FOR EVERYONE
    // ==================================================

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

            setStatus("Ending meeting...");

            // Django verifies permission before ending.
            await postMeetingRequest(endUrl);

            const currentRoom = room;

            if (currentRoom) {
                await currentRoom.disconnect();
            }

            cleanupMedia();

            room = null;

            resetMeetingPermissions();

            setStatus("Meeting ended.");

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


    // ==================================================
    // 20. CLOSE MEETING PANEL
    // ==================================================

    function closeMeetingPanel() {

        if (isConnected()) {

            setStatus(
                "Leave the meeting before closing this panel."
            );

            return;
        }

        if (busy) {
            return;
        }

        panel.hidden = true;
    }


    // ==================================================
    // 21. EVENT LISTENERS
    // ==================================================

    videoButton.addEventListener(
        "click",
        () => enterMeeting("video")
    );

    voiceButton.addEventListener(
        "click",
        () => enterMeeting("voice")
    );

    microphoneButton.addEventListener(
        "click",
        toggleMicrophone
    );

    cameraButton.addEventListener(
        "click",
        toggleCamera
    );

    screenShareButton.addEventListener(
        "click",
        toggleScreenSharing
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


    // ==================================================
    // 22. INITIALIZE
    // ==================================================

    updateControls();

    console.log(
        "CodeView LiveKit voice, video and screen sharing initialized."
    );
});