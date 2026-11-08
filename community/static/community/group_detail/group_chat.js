/* ==========================================
   CODEVIEW — REAL-TIME GROUP CHAT

   Features:
   1. WebSocket connection
   2. Real-time new messages
   3. File attachments
   4. Message replies
   5. Send without refreshing
   6. Edit without refreshing
   7. Delete without refreshing
   8. Automatic scrolling
   9. Dynamic edit and delete forms
========================================== */

document.addEventListener("DOMContentLoaded", function () {

    // ========================================
    // 1. GET CHAT ELEMENTS
    // ========================================

    const chatForm = document.getElementById("chat-form");
    const chatMessages = document.getElementById("chat-messages");

    // Stop if Group Chat is not available.
    if (!chatForm || !chatMessages) {
        return;
    }

    const attachButton = document.getElementById("attach-file-button");

    // Normal message input container.
const composerNormal = document.getElementById("composer-normal");

// Voice recording container.
const composerVoice = document.getElementById("composer-voice");

// Stop and discard buttons.
const stopVoiceButton = document.getElementById("stop-voice-button");
const cancelVoiceButton = document.getElementById("cancel-voice-button");

// Recording timer and status.
const voiceRecordingTimer = document.getElementById("voice-recording-timer");
const voiceRecordingStatus = document.getElementById("voice-recording-status");

// Audio player for reviewing the recording.
const voicePreview = document.getElementById("voice-preview");


    // Button used to start and stop voice recording.
const recordVoiceButton = document.getElementById(
    "record-voice-button"
);


    const fileInput = chatForm.querySelector('input[type="file"]');

    const messageType = chatForm.querySelector(
        'input[name="message_type"]'
    );

    const messageInput = document.getElementById("id_content");

    const fileNameDisplay = document.getElementById(
        "selected-file-name"
    );

    const replyToInput = document.getElementById("reply-to-id");

    // Get the current group and logged-in developer IDs.
    const groupId = chatMessages.dataset.groupId;
    const currentUserId = Number(
        document.body.dataset.currentUserId
    );

    if (!groupId) {
        console.error("CodeView: Missing group ID.");
        return;
    }

    // ========================================
    // 2. WEBSOCKET CONNECTION
    // ========================================

    const protocol = window.location.protocol === "https:"
        ? "wss"
        : "ws";

    const socketUrl =
        `${protocol}://${window.location.host}/ws/groups/${groupId}/chat/`;

    let chatSocket = null;
    let reconnectTimer = null;
    let leavingPage = false;

    function connectWebSocket() {

        chatSocket = new WebSocket(socketUrl);

        chatSocket.onopen = function () {
            console.log("CodeView: WebSocket connected.");
        };

        chatSocket.onmessage = function (event) {

            let data;

            try {
                data = JSON.parse(event.data);
            } catch (error) {
                console.error("Invalid WebSocket message:", error);
                return;
            }

            switch (data.type) {

                case "message_created":
                    handleNewMessage(data);
                    break;

                case "message_edited":
                    handleEditedMessage(data);
                    break;

                case "message_deleted":
                    handleDeletedMessage(data);
                    break;

                    // Update reactions when another developer reacts.
                case "message_reaction":
                    handleMessageReaction(data);
                    break;

                default:
                    console.log("Unknown chat event:", data.type);
            }
        };

        chatSocket.onclose = function (event) {

            console.log("CodeView: WebSocket disconnected.");

            // Do not reconnect after authorization failure
            // or when leaving the page.
            if (
                leavingPage ||
                event.code === 4401 ||
                event.code === 4403
            ) {
                return;
            }

            reconnectTimer = setTimeout(
                connectWebSocket,
                3000
            );
        };

        chatSocket.onerror = function () {
            console.error("CodeView: WebSocket error.");
        };
    }

    connectWebSocket();

    // ========================================
    // 3. HELPER FUNCTIONS
    // ========================================

    function scrollToBottom() {
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    function findMessage(messageId) {
        return document.getElementById(
            `message-${messageId}`
        );
    }

    function getCSRFToken(form) {

        return form.querySelector(
            'input[name="csrfmiddlewaretoken"]'
        )?.value || "";
    }

// Submit a Django form without refreshing the page.
async function submitForm(form) {

    // Send the form data to Django.
    const response = await fetch(form.action, {

        method: "POST",

        // Include all form fields and attachments.
        body: new FormData(form),

        // Include Django session cookies.
        credentials: "same-origin",

        headers: {

            // Include Django's CSRF protection token.
            "X-CSRFToken": getCSRFToken(form),

            // Tell Django this is an AJAX request.
            "X-Requested-With": "XMLHttpRequest"
        }
    });

    // Reject unsuccessful HTTP responses.
    if (!response.ok) {

        throw new Error(
            `Request failed: ${response.status}`
        );
    }

    // Reject redirects instead of treating them as success.
    if (response.redirected) {

        throw new Error(
            "Django redirected the request instead of returning JSON."
        );
    }

    // Confirm Django returned JSON.
    const contentType = response.headers.get("content-type") || "";

    if (!contentType.includes("application/json")) {

        throw new Error(
            "Expected a JSON response from Django."
        );
    }

    // Read Django's response.
    const result = await response.json();

    // Confirm Django accepted the action.
    if (result.success !== true) {

        throw new Error(
            result.error || "The request was not successful."
        );
    }

    // Return the validated result.
    return result;
}

    // Create a CSRF input for dynamically generated forms.
    function addCSRFToken(form) {

        const csrfInput = document.createElement("input");

        csrfInput.type = "hidden";
        csrfInput.name = "csrfmiddlewaretoken";
        csrfInput.value = getCSRFToken(chatForm);

        form.appendChild(csrfInput);
    }

    // ========================================
    // 4. DISPLAY NEW WEBSOCKET MESSAGES
    // ========================================

    function handleNewMessage(data) {

        // Avoid adding duplicate messages.
        if (findMessage(data.message_id)) {
            return;
        }

        // Remove the empty-chat placeholder.
        const emptyMessage = chatMessages.querySelector(
            ".chat-empty"
        );

        if (emptyMessage) {
            emptyMessage.remove();
        }

        // Check whether this message belongs to the
        // currently logged-in developer.
        const isOwnMessage =
            currentUserId === Number(data.sender_id);

        // ====================================
        // CREATE MAIN MESSAGE CONTAINER
        // ====================================

        const article = document.createElement("article");

        article.className = "chat-message";
        article.id = `message-${data.message_id}`;
        article.dataset.messageId = data.message_id;

        // ====================================
        // SENDER AVATAR
        // ====================================

        const avatar = document.createElement("div");

        avatar.className = "message-avatar";
        avatar.textContent = (data.sender || "?")
            .charAt(0)
            .toUpperCase();

        article.appendChild(avatar);

        // ====================================
        // MESSAGE BODY
        // ====================================

        const body = document.createElement("div");

        body.className = "message-body";

        // ====================================
        // MESSAGE HEADER
        // ====================================

        const header = document.createElement("div");

        header.className = "message-header";

        const author = document.createElement("strong");

        author.className = "message-author";
        author.textContent = data.sender || "Unknown developer";

        const time = document.createElement("time");

        time.className = "message-time";

        if (data.created_at) {
            const createdAt = new Date(data.created_at);

            time.dateTime = data.created_at;

            time.textContent = createdAt.toLocaleString();
        }

        header.appendChild(author);
        header.appendChild(time);
        body.appendChild(header);

        // ====================================
        // REPLY PREVIEW
        // ====================================

        if (data.reply_to_id) {

            const replyPreview = document.createElement("div");

            replyPreview.className = "message-reply";

            const replyLabel = document.createElement("span");

            replyLabel.textContent = "↳ Replying to a message";

            replyPreview.appendChild(replyLabel);

            // Find the original message already in the chat.
            const originalMessage = findMessage(
                data.reply_to_id
            );

            if (originalMessage) {

                const originalAuthor = originalMessage.querySelector(
                    ".message-author"
                );

                const originalContent = originalMessage.querySelector(
                    ".chat-message-content"
                );

                if (originalAuthor) {

                    const authorName = document.createElement("strong");

                    authorName.textContent =
                        " " + originalAuthor.textContent;

                    replyPreview.appendChild(authorName);
                }

                if (originalContent) {

                    const previewText = document.createElement("p");

                    previewText.textContent =
                        originalContent.textContent.slice(0, 100);

                    replyPreview.appendChild(previewText);
                }
            }

            body.appendChild(replyPreview);
        }

        // ====================================
        // MESSAGE CONTENT
        // ====================================

        if (data.content) {

            let content;

            if (data.message_type === "code") {

                content = document.createElement("pre");
                content.className = "message-code";

                const code = document.createElement("code");
                code.textContent = data.content;

                content.appendChild(code);

            } else {

                content = document.createElement("div");

                content.className =
                    "message-content chat-message-content";

                content.style.whiteSpace = "pre-wrap";
                content.textContent = data.content;
            }

            body.appendChild(content);
        }

        // ====================================
        // FILE OR VOICE ATTACHMENT
        // ====================================

        if (data.attachment_url) {

            if (data.message_type === "voice") {

                const audio = document.createElement("audio");

                audio.className = "message-audio";
                audio.controls = true;
                audio.preload = "none";
                audio.src = data.attachment_url;

                body.appendChild(audio);

            } else {

                const attachment = document.createElement("a");

                attachment.className = "message-attachment";
                attachment.href = data.attachment_url;
                attachment.textContent = "📎 Download Attachment";

                attachment.setAttribute("download", "");

                body.appendChild(attachment);
            }
        }

        // ====================================
        // MESSAGE ACTION BUTTONS
        // ====================================

        const actions = document.createElement("div");

        actions.className = "message-actions";

        // Reply button — available to all group members.
        const replyButton = document.createElement("button");

        replyButton.type = "button";
        replyButton.className = "reply-button";
        replyButton.dataset.messageId = data.message_id;
        replyButton.dataset.sender = data.sender || "";
        replyButton.textContent = "↩ Reply";

        actions.appendChild(replyButton);

                // Allow developers to react to any message.
        const reactButton = document.createElement("button");

        reactButton.type = "button";
        reactButton.className = "react-button";
        reactButton.dataset.messageId = data.message_id;
        reactButton.textContent = "😊 React";

        actions.appendChild(reactButton);

        // Edit and Delete buttons — owner only.
        if (isOwnMessage) {

            if (data.message_type === "text") {

                const editButton = document.createElement("button");

                editButton.type = "button";
                editButton.className = "edit-button";
                editButton.dataset.messageId = data.message_id;
                editButton.textContent = "✏️ Edit";

                actions.appendChild(editButton);
            }

            const deleteButton = document.createElement("button");

            deleteButton.type = "button";
            deleteButton.className = "delete-button";
            deleteButton.dataset.messageId = data.message_id;
            deleteButton.textContent = "🗑 Delete";

            actions.appendChild(deleteButton);
        }

        body.appendChild(actions);


                // Container for the emoji picker.
        const reactionPicker = document.createElement("div");

        reactionPicker.className = "reaction-picker";
        reactionPicker.hidden = true;

        body.appendChild(reactionPicker);

        // Container for reaction counts.
        const reactionCounts = document.createElement("div");

        reactionCounts.className = "reaction-counts";

        body.appendChild(reactionCounts);
        // ====================================
        // DYNAMIC EDIT AND DELETE FORMS
        // ====================================

        if (isOwnMessage) {

            // Derive the correct URLs from the existing
            // Django message-sending form.
            // Get the group chat URL by removing "send/".
            const chatBaseUrl = chatForm.action.replace(/send\/?$/, "");

            // Create the correct Edit URL.
            const editUrl = `${chatBaseUrl}${data.message_id}/edit/`;

            // Create the correct Delete URL.
            const deleteUrl = `${chatBaseUrl}${data.message_id}/delete/`;

            // ====================================
            // EDIT FORM — TEXT MESSAGES ONLY
            // ====================================

            if (data.message_type === "text") {

                const editForm = document.createElement("form");

                editForm.method = "POST";
                editForm.action = editUrl;
                editForm.className = "message-edit-form";
                editForm.id = `edit-form-${data.message_id}`;
                editForm.hidden = true;

                addCSRFToken(editForm);

                const editInput = document.createElement("textarea");

                editInput.name = "content";
                editInput.className = "message-edit-input";
                editInput.rows = 3;
                editInput.required = true;
                editInput.value = data.content || "";

                editForm.appendChild(editInput);

                const editActions = document.createElement("div");

                editActions.className = "message-edit-actions";

                const saveButton = document.createElement("button");

                saveButton.type = "submit";
                saveButton.className = "edit-save-button";
                saveButton.textContent = "Save";

                const cancelEdit = document.createElement("button");

                cancelEdit.type = "button";
                cancelEdit.className = "edit-cancel-button";
                cancelEdit.textContent = "Cancel";

                editActions.appendChild(saveButton);
                editActions.appendChild(cancelEdit);

                editForm.appendChild(editActions);
                body.appendChild(editForm);
            }

            // ====================================
            // DELETE CONFIRMATION FORM
            // ====================================

            const deleteForm = document.createElement("form");

            deleteForm.method = "POST";
            deleteForm.action = deleteUrl;
            deleteForm.className = "message-delete-form";
            deleteForm.id = `delete-form-${data.message_id}`;
            deleteForm.hidden = true;

            addCSRFToken(deleteForm);

            const confirmation = document.createElement("p");

            confirmation.textContent =
                "Are you sure you want to delete this message?";

            deleteForm.appendChild(confirmation);

            const deleteActions = document.createElement("div");

            deleteActions.className = "message-edit-actions";

            const confirmDelete = document.createElement("button");

            confirmDelete.type = "submit";
            confirmDelete.className = "delete-confirm-button";
            confirmDelete.textContent = "Yes, Delete";

            const cancelDelete = document.createElement("button");

            cancelDelete.type = "button";
            cancelDelete.className = "delete-cancel-button";
            cancelDelete.textContent = "Cancel";

            deleteActions.appendChild(confirmDelete);
            deleteActions.appendChild(cancelDelete);

            deleteForm.appendChild(deleteActions);
            body.appendChild(deleteForm);
        }

        // ====================================
        // DISPLAY COMPLETED MESSAGE
        // ====================================

        article.appendChild(body);

        chatMessages.appendChild(article);

        scrollToBottom();
    }

    // ========================================
    // 5. UPDATE EDITED MESSAGES
    // ========================================
// ========================================
// UPDATE EDITED MESSAGES IN REAL TIME
// ========================================
// ========================================
// UPDATE EDITED MESSAGES WITHOUT REFRESHING
// ========================================

function handleEditedMessage(data) {

    // Find the message using its ID.
    const messageElement = document.getElementById(
        `message-${data.message_id}`
    );

    if (!messageElement) {
        console.error("Message not found:", data.message_id);
        return;
    }

    // Find the displayed message content.
    const contentElement = messageElement.querySelector(
        ".chat-message-content, .message-content"
    );

    if (!contentElement) {
        console.error("Message content not found:", data.message_id);
        return;
    }

    // Immediately display the edited message.
    contentElement.textContent = data.content;

    // Preserve line breaks.
    contentElement.style.whiteSpace = "pre-wrap";

    // Close the edit form.
    const editForm = document.getElementById(
        `edit-form-${data.message_id}`
    );

    if (editForm) {
        editForm.hidden = true;

        const textarea = editForm.querySelector(
            ".message-edit-input"
        );

        if (textarea) {
            textarea.value = data.content;
        }
    }

    console.log("Message edited successfully:", data.message_id);
}

    // ========================================
    // 6. REMOVE DELETED MESSAGES
    // ========================================

    function handleDeletedMessage(data) {

        const messageElement = findMessage(data.message_id);

        if (messageElement) {
            messageElement.remove();
        }

        // Show the empty-chat placeholder when appropriate.
        if (!chatMessages.querySelector(".chat-message")) {

            const emptyMessage = document.createElement("p");

            emptyMessage.className = "chat-empty";
            emptyMessage.textContent =
                "No messages yet. Start the conversation!";

            chatMessages.appendChild(emptyMessage);
        }
    }

    // ========================================
    // 7. FILE ATTACHMENTS
    // ========================================

    if (attachButton && fileInput) {

        attachButton.addEventListener("click", function () {
            fileInput.click();
        });

        fileInput.addEventListener("change", function () {

            const selectedFile = fileInput.files[0];

            if (messageType) {
                messageType.value = selectedFile ? "file" : "text";
            }

            if (fileNameDisplay) {

                fileNameDisplay.textContent = selectedFile
                    ? "📎 " + selectedFile.name
                    : "";

                fileNameDisplay.hidden = !selectedFile;
            }
        });
    }

   // ========================================
// 8. REPLY TO MESSAGES
// ========================================
// ========================================
// VOICE NOTE RECORDING
// ========================================

// Store the active microphone recorder.
let mediaRecorder = null;

// Store the microphone stream.
let microphoneStream = null;

// Store recorded audio pieces.
let audioChunks = [];

// Store the completed recording until it is sent.
let recordedVoiceFile = null;

// Track whether microphone permission is being requested.
let startingRecording = false;

// Maximum recording duration: 2 minutes.
const MAX_RECORDING_MS = 120000;

// Maximum recording size: 20 MB.
const MAX_VOICE_SIZE = 20 * 1024 * 1024;

// Automatically stop recordings after the maximum duration.
let recordingTimer = null;

// Update the visible recording timer.
let recordingDisplayTimer = null;

// Store when recording started.
let recordingStartedAt = 0;

// Store the temporary audio preview URL.
let voicePreviewUrl = null;

// Track whether the user discarded the recording.
let discardRecording = false;


// ========================================
// 1. FORMAT RECORDING TIME
// ========================================

function formatVoiceTime(totalSeconds) {

    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;

    return (
        String(minutes).padStart(2, "0") +
        ":" +
        String(seconds).padStart(2, "0")
    );
}


// ========================================
// 2. STOP RECORDING DISPLAY TIMER
// ========================================

function stopRecordingDisplayTimer() {

    if (recordingDisplayTimer !== null) {

        clearInterval(recordingDisplayTimer);

        recordingDisplayTimer = null;
    }
}


// ========================================
// 3. RELEASE MICROPHONE
// ========================================

function releaseMicrophone() {

    // Stop the automatic recording timeout.
    clearTimeout(recordingTimer);

    recordingTimer = null;

    // Release microphone access.
    if (microphoneStream) {

        microphoneStream.getTracks().forEach(function (track) {

            track.stop();

        });

        microphoneStream = null;
    }
}


// ========================================
// 4. RESET MICROPHONE BUTTON
// ========================================

function resetRecordButton() {

    if (!recordVoiceButton) {
        return;
    }

    recordVoiceButton.textContent = "🎤";

    recordVoiceButton.title = "Record voice note";

    recordVoiceButton.setAttribute(
        "aria-label",
        "Record voice note"
    );
}


// ========================================
// 5. RESTORE NORMAL MESSAGE COMPOSER
// ========================================

function showNormalComposer() {

    // Stop updating the recording timer.
    stopRecordingDisplayTimer();

    // Show the normal message input.
    if (composerNormal) {
        composerNormal.hidden = false;
    }

    // Hide the recording interface.
    if (composerVoice) {
        composerVoice.hidden = true;
    }

    // Stop and clear the audio preview.
    if (voicePreview) {

        voicePreview.pause();

        voicePreview.hidden = true;

        voicePreview.removeAttribute("src");

        voicePreview.load();
    }

    // Release the temporary audio URL.
    if (voicePreviewUrl) {

        URL.revokeObjectURL(voicePreviewUrl);

        voicePreviewUrl = null;
    }

    // Restore recording status.
    if (voiceRecordingStatus) {
        voiceRecordingStatus.hidden = false;
    }

    // Restore stop button.
    if (stopVoiceButton) {
        stopVoiceButton.hidden = false;
    }

    // Restore the microphone button.
    resetRecordButton();
}


// ========================================
// 6. SHOW RECORDING INTERFACE
// ========================================

function showRecordingComposer() {

    // Hide normal text input.
    if (composerNormal) {
        composerNormal.hidden = true;
    }

    // Show recording interface.
    if (composerVoice) {
        composerVoice.hidden = false;
    }

    // Hide audio preview while recording.
    if (voicePreview) {
        voicePreview.hidden = true;
    }

    // Show recording status.
    if (voiceRecordingStatus) {
        voiceRecordingStatus.hidden = false;
    }

    // Show stop recording button.
    if (stopVoiceButton) {
        stopVoiceButton.hidden = false;
    }

    // Record the starting time.
    recordingStartedAt = Date.now();

    // Start the timer from zero.
    if (voiceRecordingTimer) {
        voiceRecordingTimer.textContent = "00:00";
    }

    stopRecordingDisplayTimer();

    // Update the timer every second.
    recordingDisplayTimer = setInterval(function () {

        const elapsedSeconds = Math.floor(
            (Date.now() - recordingStartedAt) / 1000
        );

        if (voiceRecordingTimer) {

            voiceRecordingTimer.textContent =
                formatVoiceTime(elapsedSeconds);
        }

    }, 1000);
}


// ========================================
// 7. SHOW AUDIO PREVIEW
// ========================================

function showVoicePreviewComposer() {

    stopRecordingDisplayTimer();

    // A completed recording must exist.
    if (!recordedVoiceFile || !voicePreview) {

        showNormalComposer();

        return;
    }

    // Remove an older preview URL.
    if (voicePreviewUrl) {

        URL.revokeObjectURL(voicePreviewUrl);

        voicePreviewUrl = null;
    }

    // Create a temporary URL for playback.
    voicePreviewUrl = URL.createObjectURL(
        recordedVoiceFile
    );

    // Load the recorded audio.
    voicePreview.src = voicePreviewUrl;

    voicePreview.hidden = false;

    voicePreview.load();

    // Hide the recording timer.
    if (voiceRecordingStatus) {
        voiceRecordingStatus.hidden = true;
    }

    // Hide the stop button.
    if (stopVoiceButton) {
        stopVoiceButton.hidden = true;
    }

    // Keep the normal text input hidden.
    if (composerNormal) {
        composerNormal.hidden = true;
    }

    // Keep the voice composer visible.
    if (composerVoice) {
        composerVoice.hidden = false;
    }
}


// ========================================
// 8. DISPLAY RECORDED VOICE
// ========================================

function showRecordedVoice() {

    if (!recordedVoiceFile) {
        return;
    }

    // Show the audio player inside the composer.
    showVoicePreviewComposer();

    // Hide the old recording notification.
    if (fileNameDisplay) {

        fileNameDisplay.textContent = "";

        fileNameDisplay.hidden = true;
    }
}


// ========================================
// 9. START VOICE RECORDING
// ========================================

async function startVoiceRecording() {

    // Prevent multiple recording sessions.
    if (
        startingRecording ||
        mediaRecorder ||
        sendingMessage
    ) {
        return;
    }

    // Check browser microphone support.
    if (
        !navigator.mediaDevices ||
        !navigator.mediaDevices.getUserMedia ||
        typeof MediaRecorder === "undefined"
    ) {

        alert(
            "Your browser does not support microphone recording."
        );

        return;
    }

    // Ensure the recording interface exists.
    if (
        !composerNormal ||
        !composerVoice ||
        !voicePreview
    ) {

        alert("Voice recording interface is unavailable.");

        return;
    }

    startingRecording = true;

    try {

        // Request microphone permission.
        microphoneStream =
            await navigator.mediaDevices.getUserMedia({
                audio: true
            });

        // Choose a supported recording format.
        let mimeType = "";

        if (
            MediaRecorder.isTypeSupported(
                "audio/webm;codecs=opus"
            )
        ) {

            mimeType = "audio/webm;codecs=opus";

        } else if (
            MediaRecorder.isTypeSupported("audio/webm")
        ) {

            mimeType = "audio/webm";

        } else if (
            MediaRecorder.isTypeSupported("audio/mp4")
        ) {

            mimeType = "audio/mp4";
        }

        // Create the microphone recorder.
        mediaRecorder = mimeType
            ? new MediaRecorder(
                microphoneStream,
                { mimeType }
            )
            : new MediaRecorder(microphoneStream);

        // Clear old recording data.
        audioChunks = [];

        recordedVoiceFile = null;

        discardRecording = false;

        // Collect audio data.
        mediaRecorder.addEventListener(
            "dataavailable",
            function (event) {

                if (event.data.size > 0) {

                    audioChunks.push(event.data);
                }
            }
        );

        // Process the recording after it stops.
        mediaRecorder.addEventListener(
            "stop",
            function () {

                // Stop the visible recording timer.
                stopRecordingDisplayTimer();

                // Get the recorded audio format.
                const recorderType =
                    mediaRecorder.mimeType ||
                    mimeType ||
                    "audio/webm";

                // Combine the recorded audio pieces.
                const audioBlob = new Blob(
                    audioChunks,
                    {
                        type: recorderType
                    }
                );

                // Determine the file extension.
                const extension =
                    recorderType.includes("mp4")
                        ? "m4a"
                        : "webm";

                // Release the recorder and microphone.
                mediaRecorder = null;

                releaseMicrophone();

                // Check whether the recording was discarded.
                if (discardRecording) {

                    recordedVoiceFile = null;

                    discardRecording = false;

                    showNormalComposer();

                } else if (audioBlob.size === 0) {

                    alert("No audio was recorded.");

                    showNormalComposer();

                } else if (
                    audioBlob.size > MAX_VOICE_SIZE
                ) {

                    alert(
                        "Voice note exceeds the 20 MB limit."
                    );

                    showNormalComposer();

                } else {

                    // Create the file Django will receive.
                    recordedVoiceFile = new File(
                        [audioBlob],
                        `voice-note-${Date.now()}.${extension}`,
                        {
                            type: recorderType
                        }
                    );

                    // Show playback before sending.
                    showRecordedVoice();
                }

                // Clear temporary audio pieces.
                audioChunks = [];

                // Restore microphone button.
                resetRecordButton();
            }
        );

        // Handle recorder errors.
        mediaRecorder.addEventListener(
            "error",
            function (event) {

                console.error(
                    "Voice recorder error:",
                    event
                );

                discardRecording = true;

                stopRecordingDisplayTimer();

                releaseMicrophone();

                showNormalComposer();
            }
        );

        // Start recording.
        mediaRecorder.start();

        // Switch to the recording interface.
        showRecordingComposer();

        // Automatically stop after two minutes.
        recordingTimer = setTimeout(function () {

            if (
                mediaRecorder &&
                mediaRecorder.state === "recording"
            ) {

                mediaRecorder.stop();
            }

        }, MAX_RECORDING_MS);

    } catch (error) {

        console.error(
            "Microphone recording failed:",
            error
        );

        // Clean up a recorder that failed to start.
        if (
            mediaRecorder &&
            mediaRecorder.state === "recording"
        ) {

            discardRecording = true;

            mediaRecorder.stop();

        } else {

            mediaRecorder = null;

            releaseMicrophone();

            showNormalComposer();
        }

        alert(
            "Unable to access your microphone. Check browser permissions."
        );

    } finally {

        startingRecording = false;
    }
}


// ========================================
// 10. MICROPHONE BUTTON
// ========================================

if (recordVoiceButton) {

    recordVoiceButton.addEventListener(
        "click",
        async function () {

            // Start a new recording.
            await startVoiceRecording();
        }
    );
}


// ========================================
// 11. STOP RECORDING BUTTON
// ========================================

if (stopVoiceButton) {

    stopVoiceButton.addEventListener(
        "click",
        function () {

            if (
                mediaRecorder &&
                mediaRecorder.state === "recording"
            ) {

                // Stop recording and prepare preview.
                mediaRecorder.stop();
            }
        }
    );
}


// ========================================
// 12. DELETE RECORDING BUTTON
// ========================================

if (cancelVoiceButton) {

    cancelVoiceButton.addEventListener(
        "click",
        function () {

            // If recording is active, discard it.
            if (
                mediaRecorder &&
                mediaRecorder.state === "recording"
            ) {

                discardRecording = true;

                mediaRecorder.stop();

                return;
            }

            // If already recorded, delete the voice file.
            recordedVoiceFile = null;

            audioChunks = [];

            discardRecording = false;

            // Restore normal text input.
            showNormalComposer();
        }
    );
}


// ========================================
// 13. CLEAN UP MICROPHONE WHEN LEAVING
// ========================================

window.addEventListener(
    "beforeunload",
    function () {

        // Stop the visible recording timer.
        stopRecordingDisplayTimer();

        // Release microphone access.
        releaseMicrophone();

        // Remove the temporary audio URL.
        if (voicePreviewUrl) {

            URL.revokeObjectURL(voicePreviewUrl);

            voicePreviewUrl = null;
        }
    }
);

// Find the existing reply preview elements in the HTML.
const replyPreview = document.getElementById("chat-reply-preview");
const replyPreviewSender = document.getElementById("reply-preview-sender");
const replyPreviewContent = document.getElementById("reply-preview-content");

// Find the Cancel Reply button.
const cancelReplyButton = document.querySelector(
    "#chat-reply-preview button"
);

// Reset the reply form to its normal state.
function clearReply() {

    // Remove the ID of the message being replied to.
    if (replyToInput) {
        replyToInput.value = "";
    }

    // Hide the reply preview.
    if (replyPreview) {
        replyPreview.hidden = true;
    }

    // Clear the previous reply details.
    if (replyPreviewSender) {
        replyPreviewSender.textContent = "";
    }

    if (replyPreviewContent) {
        replyPreviewContent.textContent = "";
    }

    // Restore the normal message placeholder.
    if (messageInput) {
        messageInput.placeholder = "Type a message...";
    }
}

// Allow the user to cancel a reply.
if (cancelReplyButton) {
    cancelReplyButton.addEventListener("click", function (event) {

        // Prevent accidental form submission.
        event.preventDefault();

        // Cancel the reply.
        clearReply();

        // Return focus to the message input.
        if (messageInput) {
            messageInput.focus();
        }
    });
}
// Listen for clicks on Reply buttons.
chatMessages.addEventListener("click", function (event) {

    // Identify the Reply button that was clicked.
    const button = event.target.closest(".reply-button");

    if (!button) {
        return;
    }

    // Store the ID of the message being replied to.
    if (replyToInput) {
        replyToInput.value = button.dataset.messageId;
    }

    // Find the original message in the chat.
    const originalMessage = findMessage(button.dataset.messageId);

    // Get the original message's text.
    const originalContent = originalMessage
        ? originalMessage.querySelector(".chat-message-content, .message-content")
        : null;

    // Display the original sender and message.
    if (replyPreview && replyPreviewSender && replyPreviewContent) {

        replyPreviewSender.textContent =
            "Replying to " + (button.dataset.sender || "Developer");

        replyPreviewContent.textContent = originalContent
            ? originalContent.textContent.trim()
            : "Original message";

        // Make the preview visible.
        replyPreview.hidden = false;
    }

    // Focus the message input.
    if (messageInput) {
        messageInput.placeholder =
            "Replying to " + (button.dataset.sender || "Developer") + "...";

        messageInput.focus();
    }
});

    // ========================================
    // 9. SEND MESSAGES WITHOUT REFRESHING
    // ========================================

    let sendingMessage = false;

    chatForm.addEventListener("submit", async function (event) {

        event.preventDefault();

        if (sendingMessage) {
            return;
        }
// Prevent sending while microphone permission is being requested.
if (startingRecording) {
    alert("Please wait for the microphone to start.");
    return;
}

// If the user presses Send while recording,
// stop recording and wait until the audio file is ready.
if (
    mediaRecorder &&
    mediaRecorder.state === "recording"
) {

    // Wait for the recorder to finish creating the audio file.
    const recorder = mediaRecorder;

    const recordingFinished = new Promise(function (resolve, reject) {

        recorder.addEventListener(
            "stop",
            function () {
                resolve();
            },
            { once: true }
        );

        recorder.addEventListener(
            "error",
            function () {
                reject(new Error("Voice recording failed."));
            },
            { once: true }
        );
    });

    // Stop the recording automatically.
    recorder.stop();

    try {
        await recordingFinished;
    } catch (error) {
        console.error("Voice recording failed:", error);
        alert("Unable to finish the voice recording.");
        return;
    }

    // Confirm that a valid audio file was created.
    if (!recordedVoiceFile) {
        alert("No valid voice recording is available to send.");
        return;
    }
}

        const message = messageInput
            ? messageInput.value.trim()
            : "";

        const hasFile = Boolean(
            fileInput && fileInput.files.length > 0
        );

        if (!message && !hasFile && !recordedVoiceFile) {
            alert("Please enter a message or attach a file.");
            return;
        }
// Preserve the voice message type for recorded audio.
if (messageType) {

    if (recordedVoiceFile) {
        messageType.value = "voice";
    } else {
        messageType.value = hasFile ? "file" : "text";
    }
}

        sendingMessage = true;

        try {

           // Send the message and wait for the server to confirm success.
         // Send a voice note if one has been recorded.
if (recordedVoiceFile) {

    const formData = new FormData(chatForm);

    // Attach the recorded audio.
    formData.set(
        "attachment",
        recordedVoiceFile,
        recordedVoiceFile.name
    );

    // Tell Django this is a voice message.
    formData.set("message_type", "voice");

    const response = await fetch(chatForm.action, {
        method: "POST",
        body: formData,
        credentials: "same-origin",
        headers: {
            "X-CSRFToken": getCSRFToken(chatForm),
            "X-Requested-With": "XMLHttpRequest"
        }
    });

    if (!response.ok) {
        throw new Error(
            `Voice upload failed: ${response.status}`
        );
    }

    const result = await response.json();

    if (result.success !== true) {
        throw new Error(
            result.error || "Voice message was not accepted."
        );
    }

} else {

    // Send normal text messages and attachments.
    await submitForm(chatForm);
}

            // Reset the message form.
            chatForm.reset();


            // Clear the recording only after Django confirms success.
            recordedVoiceFile = null;
            audioChunks = [];

            showNormalComposer();
            // Clear the reply ID and hide the reply preview.
            clearReply();

            // Restore the normal message placeholder.
            if (messageInput) {
            messageInput.placeholder = `Message #${groupId}`;
}

            if (fileNameDisplay) {
                fileNameDisplay.textContent = "";
                fileNameDisplay.hidden = true;
            }

        } catch (error) {

            console.error("Could not send message:", error);

            alert("Unable to send message. Please try again.");

        } finally {
            sendingMessage = false;
        }
    });

    // ========================================
    // 10. OPEN AND CLOSE EDIT / DELETE FORMS
    // ========================================

    chatMessages.addEventListener("click", function (event) {

        const editButton = event.target.closest(".edit-button");

        const deleteButton = event.target.closest(".delete-button");

        const editCancelButton = event.target.closest(
            ".edit-cancel-button"
        );

        const deleteCancelButton = event.target.closest(
            ".delete-cancel-button"
        );

        // Cancel editing.
        if (editCancelButton) {

            const form = editCancelButton.closest(
                ".message-edit-form"
            );

            if (form) {
                form.reset();
                form.hidden = true;
            }

            return;
        }

        // Cancel deletion.
        if (deleteCancelButton) {

            const form = deleteCancelButton.closest(
                ".message-delete-form"
            );

            if (form) {
                form.hidden = true;
            }

            return;
        }

        // Open edit form.
        if (editButton) {

            const form = document.getElementById(
                `edit-form-${editButton.dataset.messageId}`
            );

            if (!form) {
                return;
            }

            // Close other open forms.
            chatMessages.querySelectorAll(
                ".message-edit-form, .message-delete-form"
            ).forEach(function (otherForm) {

                if (otherForm !== form) {
                    otherForm.hidden = true;
                }
            });

            form.hidden = false;

            const input = form.querySelector(
                ".message-edit-input"
            );

            if (input) {
                input.focus();
            }

            return;
        }

        // Open delete confirmation.
        if (deleteButton) {

            const form = document.getElementById(
                `delete-form-${deleteButton.dataset.messageId}`
            );

            if (!form) {
                return;
            }

            chatMessages.querySelectorAll(
                ".message-edit-form, .message-delete-form"
            ).forEach(function (otherForm) {
                otherForm.hidden = true;
            });

            form.hidden = false;

            const cancelButton = form.querySelector(
                ".delete-cancel-button"
            );

            if (cancelButton) {
                cancelButton.focus();
            }
        }
    });

    // ========================================
    // 11. EDIT / DELETE WITHOUT REFRESHING
    // ========================================

    let processingAction = false;

    chatMessages.addEventListener("submit", async function (event) {

        const form = event.target;

        const isEdit = form.matches(".message-edit-form");
        const isDelete = form.matches(".message-delete-form");

        if (!isEdit && !isDelete) {
            return;
        }

        event.preventDefault();

        if (processingAction) {
            return;
        }

        if (isEdit) {

            const input = form.querySelector(
                ".message-edit-input"
            );

            if (!input || !input.value.trim()) {
                alert("Your message cannot be empty.");
                return;
            }

            input.value = input.value.trim();
        }

        processingAction = true;

        try {

// Send the edit or delete request to Django.
// submitForm() already returns validated JSON data.
const result = await submitForm(form);

// Immediately update the edited message.
if (isEdit) {

    handleEditedMessage({
        message_id: result.message_id,
        content: result.content
    });
}

// Immediately remove the deleted message.
if (isDelete) {

    handleDeletedMessage({
        message_id: result.message_id
    });
}

// Hide the form after success.
form.hidden = true;

        } catch (error) {

            console.error("Chat action failed:", error);

            alert(
                "Unable to complete this action. Please try again."
            );

        } finally {
            processingAction = false;
        }
    });

        // ========================================
    // GROUP CHAT EMOJI REACTIONS
    // ========================================

    // Emojis supported by the Django backend.
    const reactionEmojis = [
        "👍",
        "❤️",
        "😂",
        "🔥",
        "😮",
        "😢"
    ];

    // Track the logged-in developer's reactions.
    const myReactions = new Map();

    // Track messages currently submitting reactions.
    const pendingReactions = new Set();

    // Build the reaction endpoint.
    function getReactionUrl(messageId) {

        const chatBaseUrl = chatForm.action.replace(
            /send\/?$/,
            ""
        );

        return `${chatBaseUrl}${messageId}/react/`;
    }

    // Ensure every message has reaction containers.
    function ensureReactionElements(messageElement) {

        const actions = messageElement.querySelector(
            ".message-actions"
        );

        if (!actions) {
            return null;
        }

        let button = actions.querySelector(".react-button");

        if (!button) {

            button = document.createElement("button");

            button.type = "button";
            button.className = "react-button";
            button.textContent = "😊 React";

            actions.appendChild(button);
        }

        button.dataset.messageId =
            messageElement.dataset.messageId;

        const body = messageElement.querySelector(".message-body");

        if (!body) {
            return null;
        }

        let picker = body.querySelector(".reaction-picker");

        if (!picker) {

            picker = document.createElement("div");

            picker.className = "reaction-picker";
            picker.hidden = true;

            body.appendChild(picker);
        }

        let counts = body.querySelector(".reaction-counts");

        if (!counts) {

            counts = document.createElement("div");

            counts.className = "reaction-counts";

            body.appendChild(counts);
        }

        return {
            button,
            picker,
            counts
        };
    }

    // Display the emoji selection buttons.
    function showReactionPicker(messageElement) {

        const elements = ensureReactionElements(messageElement);

        if (!elements) {
            return;
        }

        const picker = elements.picker;

        // Clicking React again closes the picker.
        if (!picker.hidden) {

            picker.hidden = true;
            return;
        }

        // Close other open reaction pickers.
        chatMessages.querySelectorAll(
            ".reaction-picker"
        ).forEach(function (otherPicker) {

            otherPicker.hidden = true;
        });

        picker.replaceChildren();

        reactionEmojis.forEach(function (emoji) {

            const button = document.createElement("button");

            button.type = "button";
            button.className = "reaction-option";
            button.textContent = emoji;
            button.dataset.emoji = emoji;

            picker.appendChild(button);
        });

        picker.hidden = false;
    }

    // Display updated emoji counts.
    function renderMessageReactions(messageId, reactions) {

        const messageElement = findMessage(messageId);

        if (!messageElement) {
            return;
        }

        const elements = ensureReactionElements(messageElement);

        if (!elements) {
            return;
        }

        const container = elements.counts;

        container.replaceChildren();

        // Django returns an object such as:
        // {"❤️": 3, "😂": 2}
        Object.entries(reactions || {}).forEach(
            function ([emoji, count]) {

                if (!reactionEmojis.includes(emoji)) {
                    return;
                }

                if (!Number.isInteger(count) || count <= 0) {
                    return;
                }

                const button = document.createElement("button");

                button.type = "button";
                button.className = "reaction-count-button";

                button.dataset.emoji = emoji;
                button.dataset.messageId = messageId;

                button.textContent = `${emoji} ${count}`;

                // Highlight the developer's selected emoji.
                if (myReactions.get(String(messageId)) === emoji) {

                    button.classList.add("my-reaction");
                }

                container.appendChild(button);
            }
        );
    }

    // Send a reaction to Django.
    async function sendMessageReaction(messageId, emoji) {

        const key = String(messageId);

        // Prevent duplicate requests.
        if (pendingReactions.has(key)) {
            return;
        }

        pendingReactions.add(key);

        try {

            const response = await fetch(
                getReactionUrl(messageId),
                {
                    method: "POST",

                    credentials: "same-origin",

                    headers: {
                        "Content-Type": "application/json",

                        "X-CSRFToken": getCSRFToken(chatForm),

                        "X-Requested-With": "XMLHttpRequest"
                    },

                    body: JSON.stringify({
                        emoji: emoji
                    })
                }
            );

            if (!response.ok) {

                throw new Error(
                    `Reaction failed: ${response.status}`
                );
            }

            const result = await response.json();

            if (result.success !== true) {

                throw new Error(
                    result.error || "Unable to save reaction."
                );
            }

            // Store this developer's latest reaction.
            if (result.current_reaction) {

                myReactions.set(
                    key,
                    result.current_reaction
                );

            } else {

                myReactions.delete(key);
            }

            // Update immediately without waiting for WebSocket.
            renderMessageReactions(
                messageId,
                result.reactions
            );

        } catch (error) {

            console.error("Reaction error:", error);

            alert("Unable to react to this message.");

        } finally {

            pendingReactions.delete(key);
        }
    }

    // Handle reaction updates received through WebSockets.
    function handleMessageReaction(data) {

        const messageId = String(data.message_id);

        // Update the current developer's selected emoji
        // when their own reaction event arrives.
        if (Number(data.user_id) === currentUserId) {

            if (data.action === "removed") {

                myReactions.delete(messageId);

            } else if (data.emoji) {

                myReactions.set(messageId, data.emoji);
            }
        }

        renderMessageReactions(
            messageId,
            data.reactions
        );
    }

    // Handle reaction button clicks for existing
    // and newly created messages.
    chatMessages.addEventListener("click", function (event) {

        const reactButton = event.target.closest(
            ".react-button"
        );

        const emojiButton = event.target.closest(
            ".reaction-option, .reaction-count-button"
        );

        // Open or close the emoji picker.
        if (reactButton) {

            const messageElement = reactButton.closest(
                ".chat-message"
            );

            if (messageElement) {

                showReactionPicker(messageElement);
            }

            return;
        }

        // Submit a selected emoji.
        if (emojiButton) {

            const messageElement = emojiButton.closest(
                ".chat-message"
            );

            if (!messageElement) {
                return;
            }

            const messageId = messageElement.dataset.messageId;

            const emoji = emojiButton.dataset.emoji;

            const picker = messageElement.querySelector(
                ".reaction-picker"
            );

            if (picker) {
                picker.hidden = true;
            }

            sendMessageReaction(messageId, emoji);
        }
    });

    // Prepare reaction buttons on messages already
    // displayed when the page loads.
    chatMessages.querySelectorAll(
        ".chat-message"
    ).forEach(function (messageElement) {

        ensureReactionElements(messageElement);
    });

    // ========================================
    // 12. INITIAL SCROLL
    // ========================================

    scrollToBottom();

    // ========================================
    // 13. CLEAN UP WEBSOCKET
    // ========================================

    window.addEventListener("beforeunload", function () {

        leavingPage = true;

        clearTimeout(reconnectTimer);

        if (chatSocket) {
            chatSocket.close();
        }
    });

});