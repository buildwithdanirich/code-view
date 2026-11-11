/**
 * CodeView — LiveKit Meeting Controller
 *
 * Features:
 * - Start or join private group meetings.
 * - Microphone and camera controls.
 * - Creator-only screen sharing.
 * - Separate screen presentation and participant videos.
 * - Automatic cleanup when browser screen sharing stops.
 * - Leave without ending the meeting.
 * - End meetings with Django authorization.
 *
 * Security:
 * Django issues permission-restricted LiveKit tokens.
 * Frontend permissions improve the UI but do not replace
 * LiveKit's server-side publishing restrictions.
 */

import { Room, RoomEvent, Track } from "livekit-client";

document.addEventListener("DOMContentLoaded", () => {
    "use strict";

    // =====================================================
    // 1. HTML ELEMENTS
    // =====================================================

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
            "CodeView: Required LiveKit HTML elements are missing."
        );

        return;
    }

    // =====================================================
    // 2. DJANGO ENDPOINTS
    // =====================================================

    const startUrl = panel.dataset.startUrl;
    const joinUrl = panel.dataset.joinUrl;
    const endUrl = panel.dataset.endUrl;

    if (!startUrl || !joinUrl || !endUrl) {
        status.textContent = "Meeting configuration is incomplete.";
        return;
    }

    // =====================================================
    // 3. MEETING STATE
    // =====================================================

    let room = null;
    let busy = false;
    let meetingMode = null;

    // Permissions returned by Django.
    let canEndMeeting = false;
    let canShareScreen = false;

    // Track media elements without repeatedly recreating them.
    const attachedMedia = new Map();

    // Participant identity -> participant tile.
    const participantTiles = new Map();

    // =====================================================
    // 4. CREATE SCREEN PRESENTATION AREA
    // =====================================================

    /*
     * The HTML already contains #livekit-participants.
     *
     * We create a separate presentation element using JS.
     * This avoids placing the shared screen inside a
     * participant's camera tile.
     *
     * CSS styling will be handled in its own file next.
     */

    const meetingLayout = document.createElement("div");
    meetingLayout.className = "livekit-meeting-layout";

    const presentation = document.createElement("section");
    presentation.className = "livekit-presentation";
    presentation.hidden = true;

    const presentationHeader = document.createElement("div");
    presentationHeader.className = "livekit-presentation-header";

    const presentationTitle = document.createElement("strong");
    presentationTitle.textContent = "Screen Sharing";

    const presentationMedia = document.createElement("div");
    presentationMedia.className = "livekit-presentation-media";

    presentationHeader.appendChild(presentationTitle);

    presentation.appendChild(presentationHeader);
    presentation.appendChild(presentationMedia);

    // Preserve the original participant container.
    participants.parentNode.insertBefore(
        meetingLayout,
        participants
    );

    meetingLayout.appendChild(presentation);
    meetingLayout.appendChild(participants);

    // =====================================================
    // 5. CSRF PROTECTION
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
    // 6. DJANGO REQUESTS
    // =====================================================

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

    // =====================================================
    // 7. CONNECTION HELPERS
    // =====================================================

    function setStatus(message) {
        status.textContent = message;
    }

    function isConnected() {
        return Boolean(room && room.state === "connected");
    }

    function resetMeetingPermissions() {
        canEndMeeting = false;
        canShareScreen = false;
        meetingMode = null;
    }

    function setBusy(value) {
        busy = value;
        updateControls();
    }

    // =====================================================
    // 8. UPDATE MEETING BUTTONS
    // =====================================================

    function updateControls() {
        const connected = isConnected();

        const local = connected
            ? room.localParticipant
            : null;

        const microphoneEnabled = Boolean(
            local && local.isMicrophoneEnabled
        );

        const cameraEnabled = Boolean(
            local && local.isCameraEnabled
        );

        const screenSharing = Boolean(
            local && local.isScreenShareEnabled
        );

        videoButton.disabled = busy || connected;
        voiceButton.disabled = busy || connected;

        microphoneButton.disabled = !connected || busy;
        cameraButton.disabled = !connected || busy;

        // Only the meeting creator can share.
        screenShareButton.disabled = (
            !connected ||
            busy ||
            !canShareScreen
        );

        leaveButton.disabled = !connected || busy;

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

        screenShareButton.textContent = screenSharing
            ? "🛑 Stop Sharing"
            : "🖥 Share Screen";

        screenShareButton.setAttribute(
            "aria-pressed",
            String(screenSharing)
        );

        if (!canShareScreen) {
            screenShareButton.title =
                "Only the meeting creator can share their screen.";
        } else {
            screenShareButton.title = "";
        }
    }

    // =====================================================
    // 9. PARTICIPANT TILE MANAGEMENT
    // =====================================================

    function getParticipantTile(participant) {
        const identity = participant.identity;

        if (participantTiles.has(identity)) {
            return participantTiles.get(identity);
        }

        const tile = document.createElement("div");
        tile.className = "livekit-participant";
        tile.dataset.identity = identity;

        const name = document.createElement("strong");
        name.className = "livekit-participant-name";

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

    // =====================================================
    // 10. TRACK ATTACHMENT
    // =====================================================

    function attachParticipantTrack(
        participant,
        track,
        publication
    ) {
        if (!room || !track || publication.isMuted) {
            return;
        }

        // Prevent duplicate attachment.
        if (attachedMedia.has(track)) {
            return;
        }

        const isLocal = (
            participant === room.localParticipant
        );

        // Never play our own audio back to ourselves.
        if (
            isLocal &&
            track.kind === Track.Kind.Audio
        ) {
            return;
        }

        const isScreenShare = (
            publication.source === Track.Source.ScreenShare
        );

        const tileData = getParticipantTile(participant);

        const element = track.attach();
        element.autoplay = true;

        if (track.kind === Track.Kind.Video) {
            element.playsInline = true;

            if (isLocal) {
                element.muted = true;
            }
        }

        if (
            isScreenShare &&
            track.kind === Track.Kind.Video
        ) {
            // Screen-sharing video goes into the main
            // presentation area, not the camera tile.
            element.classList.add(
                "livekit-screen-share-video"
            );

            presentationMedia.appendChild(element);

            const name = isLocal
                ? "You"
                : (
                    participant.name ||
                    participant.identity ||
                    "Developer"
                );

            presentationTitle.textContent =
                `${name} is sharing a screen`;

        } else {
            // Camera video and remote audio remain associated
            // with the participant's tile.
            if (track.kind === Track.Kind.Video) {
                element.classList.add(
                    "livekit-camera-video"
                );
            }

            tileData.mediaContainer.appendChild(element);
        }

        attachedMedia.set(track, {
            element,
            participantIdentity: participant.identity,
            isScreenShare,
        });

        updatePresentation();
    }

    // =====================================================
    // 11. DETACH TRACKS
    // =====================================================

    function detachTrack(track) {
        const entry = attachedMedia.get(track);

        if (!entry) {
            return;
        }

        try {
            track.detach(entry.element);
        } catch (error) {
            console.warn(
                "CodeView: Unable to detach media.",
                error
            );
        }

        entry.element.remove();
        attachedMedia.delete(track);

        updatePresentation();
    }

    // =====================================================
    // 12. PRESENTATION LAYOUT
    // =====================================================

    function updatePresentation() {
        const screenVideos = presentationMedia.querySelectorAll(
            ".livekit-screen-share-video"
        );

        const hasScreenShare = screenVideos.length > 0;

        presentation.hidden = !hasScreenShare;

        meetingLayout.classList.toggle(
            "livekit-is-presenting",
            hasScreenShare
        );

        participants.classList.toggle(
            "livekit-participants-sidebar",
            hasScreenShare
        );

        if (!hasScreenShare) {
            presentationTitle.textContent = "Screen Sharing";
        }
    }

    // =====================================================
    // 13. SYNCHRONIZE PARTICIPANT TRACKS
    // =====================================================

    function syncParticipant(participant) {
        if (!room || !participant) {
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

        // Remove tracks no longer active for this participant.
        for (const [track, entry] of attachedMedia) {
            if (
                entry.participantIdentity === participant.identity &&
                !activeTracks.has(track)
            ) {
                detachTrack(track);
            }
        }

        const hasCamera = Boolean(
            tileData.mediaContainer.querySelector(
                ".livekit-camera-video"
            )
        );

        let placeholder = tileData.mediaContainer.querySelector(
            ".livekit-camera-placeholder"
        );

        if (!hasCamera && !placeholder) {
            placeholder = document.createElement("p");

            placeholder.className =
                "livekit-camera-placeholder";

            placeholder.textContent = "Camera off";

            tileData.mediaContainer.appendChild(placeholder);
        }

        if (hasCamera && placeholder) {
            placeholder.remove();
        }

        updatePresentation();
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

    // =====================================================
    // 14. REMOVE PARTICIPANTS
    // =====================================================

    function removeParticipant(participant) {
        const identity = participant.identity;

        for (const [track, entry] of attachedMedia) {
            if (entry.participantIdentity === identity) {
                detachTrack(track);
            }
        }

        const tileData = participantTiles.get(identity);

        if (tileData) {
            tileData.tile.remove();
            participantTiles.delete(identity);
        }

        updatePresentation();
    }

    // =====================================================
    // 15. CLEAN UP MEDIA
    // =====================================================

    function cleanupMedia() {
        for (const track of [...attachedMedia.keys()]) {
            detachTrack(track);
        }

        participantTiles.clear();
        participants.replaceChildren();
        presentationMedia.replaceChildren();

        updatePresentation();
    }

    // =====================================================
    // 16. LIVEKIT EVENTS
    // =====================================================

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

        activeRoom.on(
            RoomEvent.ParticipantConnected,
            (participant) => {
                refresh(participant);
            }
        );

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

        activeRoom.on(
            RoomEvent.TrackPublished,
            (publication, participant) => {
                refresh(participant);
            }
        );

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

        activeRoom.on(
            RoomEvent.TrackUnmuted,
            (publication, participant) => {
                refresh(participant);
            }
        );

        // These events also handle the browser's native
        // "Stop Sharing" button.
        activeRoom.on(
            RoomEvent.LocalTrackPublished,
            () => {
                refresh(activeRoom.localParticipant);
            }
        );

        activeRoom.on(
            RoomEvent.LocalTrackUnpublished,
            (publication) => {
                if (room !== activeRoom) {
                    return;
                }

                if (publication.track) {
                    detachTrack(publication.track);
                }

                refresh(activeRoom.localParticipant);
            }
        );

        activeRoom.on(
            RoomEvent.Disconnected,
            () => {
                if (room !== activeRoom) {
                    return;
                }

                cleanupMedia();
                room = null;

                resetMeetingPermissions();

                setStatus("Disconnected from meeting.");
                updateControls();
            }
        );
    }

    // =====================================================
    // 17. CONNECT TO LIVEKIT
    // =====================================================

    async function connectToLiveKit(credentials, mode) {
        if (!credentials.url || !credentials.token) {
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
                credentials.url,
                credentials.token
            );

            // Permissions come from Django.
            canEndMeeting = (
                credentials.can_end_meeting === true
            );

            canShareScreen = (
                credentials.can_share_screen === true
            );

            let deviceError = false;

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

            title.textContent = mode === "video"
                ? "Video Meeting"
                : "Voice Meeting";

            syncAllParticipants();

            setStatus(
                deviceError
                    ? "Connected. Some devices are unavailable."
                    : "Connected to meeting."
            );

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

    // =====================================================
    // 18. START OR JOIN A MEETING
    // =====================================================

    async function enterMeeting(mode) {
        if (busy || room) {
            return;
        }

        panel.hidden = false;
        setBusy(true);

        try {
            setStatus("Checking for an active meeting...");

            let credentials;

            try {
                const response = await postMeetingRequest(
                    joinUrl
                );

                credentials = response.meeting;

            } catch (error) {
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
                error.message || "Unable to join meeting."
            );

            if (!isConnected()) {
                cleanupMedia();
                resetMeetingPermissions();
            }

        } finally {
            setBusy(false);
        }
    }

    // =====================================================
    // 19. MICROPHONE
    // =====================================================

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
                error.message || "Unable to update microphone."
            );

        } finally {
            setBusy(false);
        }
    }

    // =====================================================
    // 20. CAMERA
    // =====================================================

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
                error.message || "Unable to update camera."
            );

        } finally {
            setBusy(false);
        }
    }

    // =====================================================
    // 21. CREATOR-ONLY SCREEN SHARING
    // =====================================================

    async function toggleScreenSharing() {
        if (
            !isConnected() ||
            busy ||
            !canShareScreen
        ) {
            return;
        }

        setBusy(true);

        try {
            const local = room.localParticipant;

            const currentlySharing = (
                local.isScreenShareEnabled
            );

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
                    error.message || "Unable to share screen."
                );
            }

        } finally {
            setBusy(false);
        }
    }

    // =====================================================
    // 22. LEAVE MEETING
    // =====================================================

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
                error.message || "Unable to leave meeting."
            );

        } finally {
            setBusy(false);
        }
    }

    // =====================================================
    // 23. END MEETING
    // =====================================================

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

            // Django independently verifies authorization.
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
                error.message || "Unable to end meeting."
            );

        } finally {
            setBusy(false);
        }
    }

    // =====================================================
    // 24. CLOSE PANEL
    // =====================================================

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

    // =====================================================
    // 25. BUTTON EVENTS
    // =====================================================

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

    // =====================================================
    // 26. INITIALIZE
    // =====================================================

    updatePresentation();
    updateControls();

    console.log(
        "CodeView LiveKit meeting controller initialized."
    );
});