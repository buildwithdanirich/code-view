/**
 * CodeView — LiveKit Meeting Controller
 *
 * Features:
 * - Start or join private group meetings.
 * - Full-screen meeting interface.
 * - Microphone and camera controls.
 * - Creator-only screen sharing.
 * - Large screen presentation with participant sidebar.
 * - Automatic cleanup when screen sharing stops.
 * - Leave without ending the meeting.
 * - End meetings with Django authorization.
 * - Return to CodeView after leaving or disconnecting.
 *
 * Security:
 * Django issues permission-restricted LiveKit tokens.
 * Frontend permissions do not replace server-side checks.
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
        status.textContent =
            "Meeting configuration is incomplete.";

        return;
    }

    // =====================================================
    // 3. MEETING STATE
    // =====================================================

    let room = null;
    let busy = false;
    let meetingMode = null;

    let canEndMeeting = false;
    let canShareScreen = false;
    let isMeetingCreator = false;

        // Remember the current meeting ID.
    let currentMeetingId = null;

    // Prevent multiple screen-sharing release requests.
    let screenShareReleaseInProgress = false;

    // Remember the original page scrolling behavior.
    let previousBodyOverflow = null;

    // Track attached audio and video elements.
    const attachedMedia = new Map();

    // Store participant tiles by LiveKit identity.
    const participantTiles = new Map();

    // =====================================================
    // 4. CREATE PRESENTATION LAYOUT
    // =====================================================

    // The original HTML already contains #livekit-participants.
    // Create a wrapper for the presentation and cameras.

    const meetingLayout = document.createElement("div");

    meetingLayout.className = "livekit-meeting-layout";

    const presentation = document.createElement("section");

    presentation.className = "livekit-presentation";
    presentation.hidden = true;

    const presentationHeader = document.createElement("div");

    presentationHeader.className =
        "livekit-presentation-header";

    const presentationTitle = document.createElement("strong");

    presentationTitle.textContent = "Screen Sharing";

    const presentationMedia = document.createElement("div");

    presentationMedia.className =
        "livekit-presentation-media";

    presentationHeader.appendChild(presentationTitle);

    presentation.appendChild(presentationHeader);
    presentation.appendChild(presentationMedia);

    // Move the existing participant container into the layout.
    participants.parentNode.insertBefore(
        meetingLayout,
        participants
    );

    meetingLayout.appendChild(presentation);
    meetingLayout.appendChild(participants);

    // =====================================================
    // 5. FULL-SCREEN PANEL MANAGEMENT
    // =====================================================

    function openMeetingPanel() {
        // Display the full-screen meeting interface.
        panel.hidden = false;

        // Prevent the workspace from scrolling behind it.
        if (previousBodyOverflow === null) {
            previousBodyOverflow = document.body.style.overflow;
        }

        document.body.style.overflow = "hidden";
    }

    function hideMeetingPanel() {
        // Hide the full-screen meeting interface.
        panel.hidden = true;

        // Restore the original workspace scrolling behavior.
        if (previousBodyOverflow !== null) {
            document.body.style.overflow = previousBodyOverflow;

            previousBodyOverflow = null;
        }
    }

    // =====================================================
    // 6. CSRF PROTECTION
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
    // 7. DJANGO REQUESTS
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
    // 8. CONNECTION HELPERS
    // =====================================================

    function setStatus(message) {
        status.textContent = message;
    }

    function isConnected() {
        return Boolean(
            room && room.state === "connected"
        );
    }

    function resetMeetingPermissions() {
        canEndMeeting = false;
        canShareScreen = false;
        isMeetingCreator = false;
        meetingMode = null;
    }

    function setBusy(value) {
        busy = value;

        updateControls();
    }

    // =====================================================
    // 9. UPDATE MEETING CONTROLS
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

        // Only the creator can share their screen.
        screenShareButton.disabled = (
            !connected ||
            busy ||
            !canShareScreen
        );

        // The creator must end the meeting instead of leaving.
        leaveButton.hidden = isMeetingCreator;
        leaveButton.disabled = (
            !connected ||
            busy ||
            isMeetingCreator
        );

        // Creator or group owner can end the meeting.
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

        screenShareButton.title = canShareScreen
            ? ""
            : "Only the meeting creator can share their screen.";
    }

    // =====================================================
    // 10. PARTICIPANT TILE MANAGEMENT
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
    // 11. ATTACH AUDIO AND VIDEO TRACKS
    // =====================================================

    function attachParticipantTrack(
        participant,
        track,
        publication
    ) {
        if (!room || !track || publication.isMuted) {
            return;
        }

        // Avoid attaching the same track twice.
        if (attachedMedia.has(track)) {
            return;
        }

        const isLocal = (
            participant === room.localParticipant
        );

        // Never play our own microphone audio.
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
            // Put screen sharing into the large presentation.
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
            // Camera and remote audio stay in participant tiles.
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
    // 12. DETACH MEDIA TRACKS
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
    // 13. UPDATE SCREEN-SHARING LAYOUT
    // =====================================================

    /**
     * Remove local screen-sharing media after sharing stops.
     *
     * This restores the normal camera layout without
     * disconnecting the developer from LiveKit.
     */
    function removeStoppedLocalScreenShare() {
        if (
            !room ||
            room.localParticipant.isScreenShareEnabled
        ) {
            return;
        }

        const localIdentity = room.localParticipant.identity;

        for (const [track, entry] of [...attachedMedia]) {
            if (
                entry.participantIdentity === localIdentity &&
                entry.isScreenShare
            ) {
                detachTrack(track);
            }
        }
    }

    function updatePresentation() {
        const screenVideos = presentationMedia.querySelectorAll(
            ".livekit-screen-share-video"
        );

        const hasScreenShare = screenVideos.length > 0;

        // Hide presentation when nobody is sharing.
        presentation.hidden = !hasScreenShare;

        // Switch between camera grid and presentation layout.
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
    // 14. SYNCHRONIZE PARTICIPANT TRACKS
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

        // Remove tracks that are no longer active.
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
    // 15. REMOVE PARTICIPANTS
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
    // 16. CLEAN UP MEDIA
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
    // 17. HANDLE MEETING DISCONNECTION
    // =====================================================

    
    function handleDisconnected(activeRoom) {
        console.trace("CodeView: Meeting disconnected");
        // Ignore events from an older room.
        if (room !== activeRoom) {
            return;
        }

        cleanupMedia();

        room = null;

        resetMeetingPermissions();

        setStatus("Disconnected from meeting.");
        // Return to the normal CodeView workspace.
        hideMeetingPanel();

        updateControls();

        // Notify other controllers that this meeting connection ended.
        // They must hide controls and stop polling permissions.
        document.dispatchEvent(
            new CustomEvent("codeview:meeting-disconnected")
        );
    }

    // =====================================================
    // 18. LIVEKIT EVENTS
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

        // Handles publishing and browser screen-share stopping.
        activeRoom.on(
            RoomEvent.LocalTrackPublished,
            () => {
                refresh(activeRoom.localParticipant);
            }
        );

        // Detect when a local track stops publishing.
        // This includes the browser's Stop Sharing button.
        activeRoom.on(
            RoomEvent.LocalTrackUnpublished,
            (publication) => {
                // Ignore events from an old meeting connection.
                if (room !== activeRoom) {
                    return;
                }

                // Remove the unpublished track from the layout.
                if (publication.track) {
                    detachTrack(publication.track);
                }

                // Update the participant's media.
                refresh(activeRoom.localParticipant);

                // Only screen-sharing tracks trigger release.
                // Camera and microphone changes must not.
                const wasScreenSharing = (
                    publication.source === Track.Source.ScreenShare
                );

                if (!wasScreenSharing) {
                    return;
                }

                // Restore the normal camera layout.
                removeStoppedLocalScreenShare();

                // Update the screen-sharing button.
                updateControls();

                // The creator does not release approved
                // participant permissions.
                if (isMeetingCreator) {
                    return;
                }

                // Return the approved participant's
                // screen-sharing permission to Django.
                void releaseScreenSharingPermission();
            }
        );

        // Handles normal and unexpected disconnections.
        activeRoom.on(
            RoomEvent.Disconnected,
            () => {
                handleDisconnected(activeRoom);
            }
        );
    }

    // =====================================================
    // 19. CONNECT TO LIVEKIT
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

            // Store the meeting ID for permission verification.
            currentMeetingId = credentials.meeting_id;

            // Django supplies these permissions.
            canEndMeeting = (
                credentials.can_end_meeting === true
            );

            canShareScreen = (
                credentials.can_share_screen === true
            );

            // Prefer Django's explicit creator permission.
            //
            // Temporary fallback:
            // Currently only the meeting creator can share.
            // Remove this fallback when participant screen
            // sharing permissions are introduced.
            isMeetingCreator = (
                typeof credentials.is_meeting_creator === "boolean"
                    ? credentials.is_meeting_creator
                    : canShareScreen
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

            // Notify other controllers that the meeting is connected.
            // No LiveKit credentials or tokens are exposed.
            document.dispatchEvent(
                new CustomEvent("codeview:meeting-connected", {
                    detail: {
                        meetingId: credentials.meeting_id,
                        isMeetingCreator: isMeetingCreator,
                    },
                })
            );

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
    // 20. START OR JOIN MEETING
    // =====================================================

    async function enterMeeting(mode) {
        if (busy || room) {
            return;
        }

        // Open the full-screen meeting interface.
        openMeetingPanel();

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

                // Return to the workspace if joining failed.
                hideMeetingPanel();
            }

        } finally {
            setBusy(false);
        }
    }

    // =====================================================
    // 21. MICROPHONE CONTROL
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
    // 22. CAMERA CONTROL
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
    // RELEASE APPROVED SCREEN-SHARING PERMISSION
    // =====================================================

    async function releaseScreenSharingPermission() {
        // The meeting creator does not need to release
        // an approved participant's permission.
        if (isMeetingCreator) {
            return;
        }

        // Prevent duplicate release requests.
        if (screenShareReleaseInProgress) {
            return;
        }

        // Django endpoint configured in meeting_room.html.
        const releaseUrl = panel.dataset.screenShareReleaseUrl;

        if (!releaseUrl || !currentMeetingId) {
            console.warn(
                "CodeView: Screen-sharing release URL or meeting ID is missing."
            );

            return;
        }

        // Only release after the local screen track has stopped.
        if (
            isConnected() &&
            room.localParticipant.isScreenShareEnabled
        ) {
            return;
        }

        screenShareReleaseInProgress = true;

        try {
            // Reuse the existing Django POST helper.
            await postMeetingRequest(releaseUrl);

            // Django has successfully released the reservation.
            canShareScreen = false;

            updateControls();

            setStatus(
                "Screen-sharing permission returned to the meeting creator."
            );

            // Ask the request controller to refresh permissions.
            document.dispatchEvent(
                new CustomEvent(
                    "codeview:screen-share-release-completed",
                    {
                        detail: {
                            meetingId: currentMeetingId,
                        },
                    }
                )
            );

        } catch (error) {
            console.error(
                "CodeView: Unable to release screen-sharing permission.",
                error
            );

            setStatus(
                "Screen sharing stopped, but permission release could not be confirmed."
            );

        } finally {
            screenShareReleaseInProgress = false;
        }
    }
    // =====================================================
    // 23. SCREEN SHARING
    // =====================================================

    async function toggleScreenSharing() {
        if (
            !isConnected() ||
            busy
        ) {
            return;
        }

        const local = room.localParticipant;

        const currentlySharing = (
            local.isScreenShareEnabled
        );

        // A developer must have permission to START sharing.
        // However, someone already sharing must always
        // be allowed to STOP sharing.
        if (
            !currentlySharing &&
            !canShareScreen
        ) {
            setStatus(
                "You do not have permission to share your screen."
            );

            return;
        }

        setBusy(true);

        try {
            // Enable or disable the local screen-sharing track.
            await local.setScreenShareEnabled(
                !currentlySharing
            );

            // If screen sharing has stopped, remove
            // the presentation from the meeting layout.
            if (!local.isScreenShareEnabled) {
                removeStoppedLocalScreenShare();
            }

            // Update participant tiles and presentation.
            syncParticipant(local);
            updatePresentation();

            if (local.isScreenShareEnabled) {
                setStatus(
                    "You are sharing your screen."
                );

            } else {
                setStatus(
                    "Screen sharing stopped."
                );

                // Approved participants must return
                // their screen-sharing permission to Django.
                if (!isMeetingCreator) {
                    await releaseScreenSharingPermission();
                }
            }

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
    // 24. LEAVE MEETING
    // =====================================================

    async function leaveMeeting() {
        console.trace("CodeView: Leave Meeting called");
        if (!room || busy || isMeetingCreator) {
            if (isMeetingCreator) {
                setStatus(
                    "Meeting creators must use End Meeting."
                );
            }

            return;
        }

        setBusy(true);

        try {
            const currentRoom = room;

            await currentRoom.disconnect();

            // The Disconnected event normally performs cleanup.
            // Also clean up here if the event has not done so.
            if (room === currentRoom) {
                handleDisconnected(currentRoom);
            }

            // Return to CodeView.
            hideMeetingPanel();

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
    // 25. END MEETING
    // =====================================================

    async function endMeeting() {
        console.trace("CodeView: End Meeting called");
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

            // Django verifies creator/group-owner permission.
            await postMeetingRequest(endUrl);

            const currentRoom = room;

            if (currentRoom) {
                await currentRoom.disconnect();

                if (room === currentRoom) {
                    handleDisconnected(currentRoom);
                }
            }

            setStatus("Meeting ended.");

            // Return to the normal CodeView workspace.
            hideMeetingPanel();

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
    // 26. CLOSE PANEL
    // =====================================================

    function closeMeetingPanel() {
        if (isConnected()) {
            setStatus(
                isMeetingCreator
                    ? "End the meeting before closing this panel."
                    : "Leave the meeting before closing this panel."
            );

            return;
        }

        if (busy) {
            return;
        }

        hideMeetingPanel();
    }

    // =====================================================
    // 27. BUTTON EVENTS
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
    // 28. INITIALIZE
    // =====================================================

    // Ensure the original workspace starts normally.
    hideMeetingPanel();

    updatePresentation();
    updateControls();

    console.log(
        "CodeView LiveKit meeting controller initialized."
    );

        // =====================================================
    // SCREEN-SHARING PERMISSION UPDATES
    // =====================================================

    document.addEventListener(
        "codeview:screen-share-permission-changed",
        (event) => {

            // Ignore permission updates when disconnected.
            if (!isConnected()) {
                return;
            }

            const details = event.detail;

            if (!details) {
                return;
            }

            // Ignore updates belonging to another meeting.
            if (
                currentMeetingId === null ||
                String(details.meetingId) !== String(currentMeetingId)
            ) {
                return;
            }

            // Update the permission received from Django.
            canShareScreen = details.canShareScreen === true;

            // Refresh the Share Screen button.
            updateControls();
        }
    );
});