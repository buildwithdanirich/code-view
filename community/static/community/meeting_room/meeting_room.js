// ============================================================
// CODEVIEW DEVELOPMENT ROOM — GITHUB FILE EXPLORER
// ============================================================

document.addEventListener("DOMContentLoaded", async () => {

    // Find the file explorer on the page.
    const fileTree = document.getElementById("github-file-tree");

    // Stop if the current page has no file explorer.
    if (!fileTree) {
        return;
    }

    // Get the Django endpoint that returns repository files.
    const filesUrl = fileTree.dataset.filesUrl;

    // Find the editor's active filename label.
    const activeFileName = document.getElementById("active-file-name");

    // Create a nested folder structure from flat GitHub paths.
    function buildTree(files) {

        const root = {
            folders: {},
            files: [],
        };

        for (const file of files) {

            // Separate the file path into folder/file names.
            const parts = file.path.split("/");

            let current = root;

            for (let index = 0; index < parts.length; index++) {

                const part = parts[index];
                const isLast = index === parts.length - 1;

                // Add folders to the tree.
                if (!isLast || file.type === "folder") {

                    if (!current.folders[part]) {
                        current.folders[part] = {
                            folders: {},
                            files: [],
                        };
                    }

                    current = current.folders[part];

                } else {

                    // Add a file to its containing folder.
                    current.files.push(file);
                }
            }
        }

        return root;
    }

    // Convert a folder structure into visible HTML elements.
    function renderTree(node, container) {

        // Sort folder names alphabetically.
        const folderNames = Object.keys(node.folders).sort();

        for (const folderName of folderNames) {

            // A details element creates an expandable folder.
            const folder = document.createElement("details");

            const summary = document.createElement("summary");
            summary.className = "explorer-item";

            // textContent prevents filenames from becoming HTML.
            summary.textContent = `📁 ${folderName}`;

            folder.appendChild(summary);

            const children = document.createElement("div");
            children.className = "explorer-children";

            // Display files and folders inside this folder.
            renderTree(node.folders[folderName], children);

            folder.appendChild(children);
            container.appendChild(folder);
        }

        // Sort files alphabetically.
        const sortedFiles = [...node.files].sort(
            (a, b) => a.name.localeCompare(b.name)
        );

        for (const file of sortedFiles) {

            const button = document.createElement("button");

            button.type = "button";
            button.className = "explorer-item";
            button.textContent = `📄 ${file.name}`;

            // For now, selecting a file displays its name.
            // Open the selected GitHub file in the editor.
            button.addEventListener("click", async () => {

                const editorContent = document.getElementById(
                    "editor-content"
                );

                const sourceCode = document.getElementById(
                    "source-code"
                );

                const sourceCodeText = document.getElementById(
                    "source-code-text"
                );

                const placeholder = document.getElementById(
                    "editor-placeholder"
                );

                // Show the selected filename.
                if (activeFileName) {
                    activeFileName.textContent = file.path;
                }

                // Check that all editor elements exist.
                if (
                    !editorContent ||
                    !sourceCode ||
                    !sourceCodeText ||
                    !placeholder
                ) {
                    return;
                }

                // Show a loading message.
                placeholder.textContent = "Loading source code...";
                placeholder.hidden = false;
                sourceCode.hidden = true;

                // Build the Django endpoint URL safely.
                const url = new URL(
                    editorContent.dataset.fileUrl,
                    window.location.origin
                );

                url.searchParams.set("path", file.path);

                try {

                    // Request the selected file from Django.
                    const response = await fetch(url, {
                        credentials: "same-origin",
                    });

                    const data = await response.json();

                    if (!response.ok) {
                        throw new Error(
                            data.error || "Unable to open this file."
                        );
                    }

                    // Display the GitHub source code safely.
                    sourceCodeText.textContent = data.content;

                    // ========================================
                    // SYNTAX HIGHLIGHTING
                    // ========================================

                    // Get the selected file's extension.
                    const extension = file.name.split(".").pop().toLowerCase();

                    // Match file extensions to programming languages.
                    const languages = {
                        py: "python",
                        go: "go",
                        js: "javascript",
                        css: "css",
                        html: "markup",
                        json: "json",
                    };

                    // Identify the programming language.
                    const language = languages[extension] || "none";

                    // Remove the previous file's language class.
                    sourceCodeText.className = "";

                    // Apply the selected programming language.
                    sourceCodeText.classList.add(`language-${language}`);

                    // Highlight the code using Prism.js.
                    if (window.Prism) {
                        Prism.highlightElement(sourceCodeText);
                    }

                    // ========================================
                    // LINE NUMBERS
                    // ========================================

                    // Find the line-number container.
                    const lineNumbers = document.getElementById("line-numbers");

                    // Split the source code into individual lines.
                    const lines = data.content.split("\n");

                    // Avoid adding an extra line number for a final newline.
                    if (lines.length > 1 && lines[lines.length - 1] === "") {
                        lines.pop();
                    }

                    // Generate line numbers starting from 1.
                    if (lineNumbers) {
                        lineNumbers.textContent = lines
                            .map((_, index) => index + 1)
                            .join("\n");
                    }
                    // Hide the placeholder and show the code.
                    placeholder.hidden = true;
                    sourceCode.hidden = false;

                } catch (error) {

                    placeholder.textContent = error.message;
                    placeholder.hidden = false;
                    sourceCode.hidden = true;
                }
            });

            container.appendChild(button);
        }
    }

    // Retrieve repository files from our Django backend.
    try {

        const response = await fetch(filesUrl, {
            credentials: "same-origin",
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(
                data.error || "Unable to load repository files."
            );
        }

        // Convert GitHub's flat list into a folder tree.
        const tree = buildTree(data.files);

        // Remove the loading message.
        fileTree.replaceChildren();

        // Display the repository folders and files.
        renderTree(tree, fileTree);

        if (data.files.length === 0) {
            fileTree.textContent = "This repository has no files.";
        }

    } catch (error) {

        // Show a useful message if the request fails.
        fileTree.textContent = error.message;
    }
});
// ============================================================
// CODEVIEW — TEAM CHAT INTERFACE
// ============================================================

// This controls the chat interface only.
// Real messaging will be connected using Django Channels later.

document.addEventListener("DOMContentLoaded", () => {

    // Find the chat panel.
    const chatPanel = document.getElementById("team-chat-panel");

    // Find the workspace containing the editor and chat.
    const workspace = document.getElementById("workspace-with-chat");

    // Find the button in the page header.
    const headerChatButton = document.getElementById(
        "header-chat-toggle"
    );

    // Find the button in the sidebar.
    const sidebarChatButton = document.getElementById(
        "sidebar-chat-toggle"
    );

    // Find the button that closes the chat.
    const closeChatButton = document.getElementById("close-chat");

    // Stop if the current page does not contain the chat interface.
    if (!chatPanel || !workspace) {
        return;
    }

    // Remember whether the developer previously closed the chat
    // in this browser tab.
    let chatIsOpen = sessionStorage.getItem(
        "codeview-chat-open"
    ) !== "false";


    // ========================================================
    // FUNCTION 1 — UPDATE CHAT VISIBILITY
    // ========================================================

    function updateChatVisibility() {

        // Hide or display the chat panel.
        chatPanel.hidden = !chatIsOpen;

        // Expand the development workspace when chat is hidden.
        workspace.classList.toggle(
            "chat-collapsed",
            !chatIsOpen
        );

        // Update accessibility information.
        if (headerChatButton) {
            headerChatButton.setAttribute(
                "aria-expanded",
                String(chatIsOpen)
            );
        }

        if (sidebarChatButton) {
            sidebarChatButton.setAttribute(
                "aria-expanded",
                String(chatIsOpen)
            );
        }

        // Save the developer's preference for this browser tab.
        sessionStorage.setItem(
            "codeview-chat-open",
            String(chatIsOpen)
        );
    }


    // ========================================================
    // FUNCTION 2 — OPEN CHAT
    // ========================================================

    function openChat() {

        chatIsOpen = true;

        updateChatVisibility();
    }


    // ========================================================
    // FUNCTION 3 — CLOSE CHAT
    // ========================================================

    function closeChat() {

        chatIsOpen = false;

        updateChatVisibility();
    }


    // ========================================================
    // FUNCTION 4 — TOGGLE CHAT
    // ========================================================

    function toggleChat() {

        chatIsOpen = !chatIsOpen;

        updateChatVisibility();
    }


    // ========================================================
    // CHAT BUTTON EVENTS
    // ========================================================

    // The header button opens or closes chat.
    if (headerChatButton) {

        headerChatButton.addEventListener(
            "click",
            toggleChat
        );
    }

    // The sidebar button opens chat.
    if (sidebarChatButton) {

        sidebarChatButton.addEventListener(
            "click",
            openChat
        );
    }

    // The close button hides chat.
    if (closeChatButton) {

        closeChatButton.addEventListener(
            "click",
            closeChat
        );
    }


    // ========================================================
    // FUNCTION 5 — UPDATE UNREAD MESSAGE COUNTER
    // ========================================================

    function updateUnreadCount(count) {

        // Convert the received count into a number.
        const unreadCount = Number(count);

        // Reject invalid unread counts.
        if (
            !Number.isSafeInteger(unreadCount) ||
            unreadCount < 0
        ) {
            return;
        }

        // Find all unread message badges.
        const badges = document.querySelectorAll(
            "[data-unread-count]"
        );

        badges.forEach((badge) => {

            // Display the number of unread messages.
            badge.textContent = String(unreadCount);

            // Hide the badge when there are no unread messages.
            badge.hidden = unreadCount === 0;

        });
    }


    // ========================================================
    // FUNCTION 6 — PREPARE A MESSAGE REPLY
    // ========================================================

    function replyToMessage(message) {

        // A real message must have an ID and author.
        if (!message || !message.id || !message.author) {
            return;
        }

        // Find the reply preview.
        const replyPreview = document.getElementById(
            "chat-reply-preview"
        );

        const replyDescription = document.getElementById(
            "chat-reply-description"
        );

        if (!replyPreview || !replyDescription) {
            return;
        }

        // Display which message the developer is replying to.
        replyDescription.textContent =
            `Replying to ${message.author}: ${message.text || ""}`;

        // Store the ID of the original message.
        replyPreview.dataset.replyToId = String(message.id);

        // Display the reply preview.
        replyPreview.hidden = false;

        // Open the chat panel.
        openChat();
    }


    // ========================================================
    // CANCEL REPLY BUTTON
    // ========================================================

    const cancelReplyButton = document.getElementById(
        "cancel-chat-reply"
    );

    if (cancelReplyButton) {

        cancelReplyButton.addEventListener("click", () => {

            const replyPreview = document.getElementById(
                "chat-reply-preview"
            );

            if (!replyPreview) {
                return;
            }

            // Hide the reply preview.
            replyPreview.hidden = true;

            // Remove the selected message ID.
            delete replyPreview.dataset.replyToId;

        });
    }


    // ========================================================
    // PREPARE FOR FUTURE DJANGO CHANNELS INTEGRATION
    // ========================================================

    // These functions will be used when real-time messaging
    // is implemented. They do not fetch or create messages yet.
    window.codeviewChatUI = {

        open: openChat,

        close: closeChat,

        notifyNewMessages: updateUnreadCount,

        replyTo: replyToMessage,

    };


    // Apply the saved chat visibility when the page loads.
    updateChatVisibility();

});

// ============================================================
// CODEVIEW — MEETING ROOM REAL-TIME CHAT
// ============================================================

// Connect the Meeting Room to the existing Group Chat WebSocket.
document.addEventListener("DOMContentLoaded", () => {

    // Get the WebSocket URL from the HTML body.
    const socketPath = document.body.dataset.chatSocketUrl;

    // Find the Meeting Room message container.
    const chatMessages = document.getElementById("chat-messages");

    // Stop if the required elements are missing.
    if (!socketPath || !chatMessages) {
        return;
    }

    // Use secure WebSockets when the website uses HTTPS.
    const protocol = window.location.protocol === "https:"
        ? "wss:"
        : "ws:";

    // Build the complete WebSocket URL.
    const socketUrl = `${protocol}//${window.location.host}${socketPath}`;

    // Connect to the existing GroupChatConsumer.
    const chatSocket = new WebSocket(socketUrl);

    // ========================================================
    // FUNCTION 1 — RECEIVE NEW MESSAGES
    // ========================================================

    chatSocket.addEventListener("message", (event) => {

        // Convert the received JSON into a JavaScript object.
        let data;

        try {
            data = JSON.parse(event.data);
        } catch (error) {
            console.error("Invalid chat message received.");
            return;
        }

// ====================================================
// HANDLE EDITED MESSAGES
// ====================================================

// Developer A edits a message.
// Django broadcasts the update to all connected members.
if (data.type === "message_edited") {

    // Find the existing message.
    const messageElement = document.getElementById(
        `message-${data.message_id}`
    );

    // Stop if the message isn't displayed.
    if (!messageElement) {
        return;
    }

    // Find its content.
    const contentElement = messageElement.querySelector(
        ".cv-chat-message-content"
    );

    // Update the content without refreshing the page.
    if (contentElement) {
        contentElement.textContent = data.content ?? "";
    }

    return;
}

// ====================================================
// HANDLE DELETED MESSAGES
// ====================================================

// Developer A deletes a message.
// Django broadcasts the deletion to all connected members.
if (data.type === "message_deleted") {

    // Find and remove the deleted message.
    const messageElement = document.getElementById(
        `message-${data.message_id}`
    );

    if (messageElement) {
        messageElement.remove();
    }

    return;
}

// ====================================================
// HANDLE NEW MESSAGES
// ====================================================

// Continue to the existing message-creation code only
// when the event represents a newly created message.
if (data.type !== "message_created") {
    return;
}

        // Avoid displaying the same message twice.
        if (document.getElementById(`message-${data.message_id}`)) {
            return;
        }

        // Remove the empty-chat placeholder.
        const emptyMessage = chatMessages.querySelector(".cv-chat-empty");

        if (emptyMessage) {
            emptyMessage.remove();
        }

        // ====================================================
        // CREATE THE MESSAGE ELEMENT
        // ====================================================

        // Create the main message container.
        const article = document.createElement("article");

        article.className = "cv-chat-message";
        article.id = `message-${data.message_id}`;
        article.dataset.messageId = data.message_id;

        // Create the message header.
        const header = document.createElement("div");

        header.className = "cv-chat-message-header";

        // Display the sender's username.
        const author = document.createElement("strong");

        author.className = "cv-chat-message-author";
        author.textContent = data.sender || "Deleted user";

        // Display the message time.
        const time = document.createElement("small");

        time.className = "cv-chat-message-time";

        const createdAt = new Date(data.created_at);

        time.textContent = Number.isNaN(createdAt.getTime())
            ? ""
            : createdAt.toLocaleTimeString([], {
                hour: "2-digit",
                minute: "2-digit",
            });

        // Add the sender and time to the header.
        header.appendChild(author);
        header.appendChild(time);

        // Create the message content.
        const content = document.createElement("p");

        content.className = "cv-chat-message-content";

        // Use textContent to display messages safely.
        content.textContent = data.content || "";

        // Create the reply button.
        const replyButton = document.createElement("button");

        replyButton.type = "button";
        replyButton.className = "cv-chat-reply-button";
        replyButton.dataset.messageId = data.message_id;
        replyButton.dataset.author = data.sender || "Deleted user";
        replyButton.textContent = "Reply";

        // Add everything to the message container.
        article.appendChild(header);

        // Show the reply relationship when present.
        if (data.reply_to_id) {

            const replyInfo = document.createElement("div");

            replyInfo.className = "cv-chat-message-reply";
            replyInfo.textContent = "↳ Replying to a message";

            article.appendChild(replyInfo);
        }

        // Display text, code, voice notes, or attachments.
        if (data.message_type === "voice" && data.attachment_url) {

            const audio = document.createElement("audio");

            audio.controls = true;
            audio.src = data.attachment_url;

            article.appendChild(audio);

        } else if (
            data.message_type === "file" &&
            data.attachment_url
        ) {

            const attachment = document.createElement("a");

            attachment.href = data.attachment_url;
            attachment.textContent = "View attachment";
            attachment.target = "_blank";
            attachment.rel = "noopener noreferrer";

            article.appendChild(attachment);

        } else {

            article.appendChild(content);
        }

// ====================================================
// CREATE MESSAGE ACTION BUTTONS
// ====================================================

// Get the logged-in developer's ID from Django.
const currentUserId = Number(
    document.body.dataset.currentUserId
);

// Get the sender's ID from the WebSocket message.
const senderId = Number(data.sender_id);

// Create the action button container.
const actions = document.createElement("div");

actions.className = "cv-chat-message-actions";

// Every group member can reply.
actions.appendChild(replyButton);

// ====================================================
// CHECK MESSAGE OWNERSHIP
// ====================================================

// Only the sender can edit or delete their message.
if (
    Number.isInteger(currentUserId) &&
    currentUserId > 0 &&
    senderId === currentUserId
) {

    // Get Django's URL templates.
    const editUrlTemplate = document.body.dataset.editUrlTemplate;
    const deleteUrlTemplate = document.body.dataset.deleteUrlTemplate;

    // Build URLs using the real message ID.
    const editUrl = editUrlTemplate.replace(
        /\/0\/$/,
        `/${data.message_id}/`
    );

    const deleteUrl = deleteUrlTemplate.replace(
        /\/0\/$/,
        `/${data.message_id}/`
    );

    // Store the URLs on the message.
    article.dataset.editUrl = editUrl;
    article.dataset.deleteUrl = deleteUrl;

    // ====================================================
    // CREATE EDIT BUTTON
    // ====================================================

    // Only text messages can be edited.
    if (data.message_type === "text") {

        const editButton = document.createElement("button");

        editButton.type = "button";
        editButton.className = "cv-chat-edit-button";
        editButton.dataset.messageId = data.message_id;
        editButton.textContent = "Edit";

        actions.appendChild(editButton);
    }

    // ====================================================
    // CREATE DELETE BUTTON
    // ====================================================

    const deleteButton = document.createElement("button");

    deleteButton.type = "button";
    deleteButton.className = "cv-chat-delete-button";
    deleteButton.dataset.messageId = data.message_id;
    deleteButton.textContent = "Delete";

    actions.appendChild(deleteButton);
}

// Add the action buttons to the message.
article.appendChild(actions);

        // Display the new message at the bottom.
        chatMessages.appendChild(article);

        // Scroll to the newest message.
        chatMessages.scrollTop = chatMessages.scrollHeight;

    });

    // ========================================================
    // WEBSOCKET CONNECTION EVENTS
    // ========================================================

    chatSocket.addEventListener("open", () => {
        console.log("Meeting Room chat connected.");
    });

    chatSocket.addEventListener("close", () => {
        console.log("Meeting Room chat disconnected.");
    });

    chatSocket.addEventListener("error", () => {
        console.error("Meeting Room chat connection error.");
    });

});
// ============================================================
// CODEVIEW — SEND MEETING ROOM CHAT MESSAGES
// ============================================================

document.addEventListener("DOMContentLoaded", () => {

    // Find the Meeting Room message form.
    const chatForm = document.getElementById("meeting-chat-form");

    // Find the message input.
    const messageInput = document.getElementById("chat-message-input");

    // Find the Send Message button.
    const sendButton = document.getElementById("send-chat-message");

    // Stop if the required elements are missing.
    if (!chatForm || !messageInput || !sendButton) {
        return;
    }

    // Prevent duplicate submissions.
    let sendingMessage = false;

    // ========================================================
    // SEND MESSAGE WITHOUT REFRESHING
    // ========================================================

    chatForm.addEventListener("submit", async (event) => {

        // Stop the browser from refreshing the page.
        event.preventDefault();

        // Prevent sending the same message twice.
        if (sendingMessage) {
            return;
        }

        // Remove unnecessary spaces.
        const message = messageInput.value.trim();

        // Reject empty messages.
        if (!message) {
            alert("Please enter a message.");
            return;
        }

        // Prepare the form data for Django.
        const formData = new FormData(chatForm);

        // Send the trimmed message.
        formData.set("content", message);

        // Mark the message as being sent.
        sendingMessage = true;
        sendButton.disabled = true;

        try {

            // Send the message to the existing Django view.
            const response = await fetch(chatForm.action, {
                method: "POST",
                body: formData,
                credentials: "same-origin",
                headers: {
                    "X-Requested-With": "XMLHttpRequest",
                },
            });

            // Read Django's response.
            const data = await response.json();

            // Handle failed requests.
            if (!response.ok || !data.success) {
                throw new Error(
                    data.error || "Unable to send message."
                );
            }

            // Clear the input after successful submission.
            messageInput.value = "";

            // Clear the reply ID.
            const replyInput = document.getElementById(
                "meeting-chat-reply-id"
            );

            if (replyInput) {
                replyInput.value = "";
            }

            // Hide the reply preview.
            const replyPreview = document.getElementById(
                "chat-reply-preview"
            );

            if (replyPreview) {
                replyPreview.hidden = true;
                delete replyPreview.dataset.replyToId;
            }

            // Return focus to the message input.
            messageInput.focus();

            // The existing WebSocket listener displays
            // the saved message automatically.

        } catch (error) {

            // Display an error without deleting the message.
            alert(error.message);

        } finally {

            // Allow the developer to send another message.
            sendingMessage = false;
            sendButton.disabled = false;

        }

    });

});
// ============================================================
// CODEVIEW — MEETING ROOM MESSAGE REPLIES
// ============================================================

document.addEventListener("DOMContentLoaded", () => {

    // Find the container holding chat messages.
    const chatMessages = document.getElementById("chat-messages");

    // Find the hidden input that stores the original message ID.
    const replyInput = document.getElementById(
        "meeting-chat-reply-id"
    );

    // Find the reply preview.
    const replyPreview = document.getElementById(
        "chat-reply-preview"
    );

    // Find the text showing who we are replying to.
    const replyDescription = document.getElementById(
        "chat-reply-description"
    );

    // Find the button for cancelling a reply.
    const cancelReplyButton = document.getElementById(
        "cancel-chat-reply"
    );

    // Find the message input.
    const messageInput = document.getElementById(
        "chat-message-input"
    );

    // Stop if any required element is missing.
    if (
        !chatMessages ||
        !replyInput ||
        !replyPreview ||
        !replyDescription ||
        !cancelReplyButton ||
        !messageInput
    ) {
        return;
    }

    // ========================================================
    // FUNCTION 1 — SELECT A MESSAGE TO REPLY TO
    // ========================================================

    function selectReply(messageId, author, content) {

        // Store the original message ID for Django.
        replyInput.value = messageId;

        // Display the original sender and message.
        replyDescription.textContent =
            `Replying to ${author}: ${content}`;

        // Show the reply preview.
        replyPreview.hidden = false;

        // Focus the message input.
        messageInput.focus();
    }

    // ========================================================
    // FUNCTION 2 — CANCEL A REPLY
    // ========================================================

    function cancelReply() {

        // Remove the selected message ID.
        replyInput.value = "";

        // Hide the reply preview.
        replyPreview.hidden = true;

        // Remove the previous reply description.
        replyDescription.textContent = "";

        // Clear the stored reply information.
        delete replyPreview.dataset.replyToId;
    }

    // ========================================================
    // FUNCTION 3 — HANDLE REPLY BUTTON CLICKS
    // ========================================================

    chatMessages.addEventListener("click", (event) => {

        // Find the Reply button that was clicked.
        const replyButton = event.target.closest(
            ".cv-chat-reply-button"
        );

        // Ignore clicks outside Reply buttons.
        if (!replyButton) {
            return;
        }

        // Get the original message ID.
        const messageId = replyButton.dataset.messageId;

        // Get the original sender's name.
        const author = replyButton.dataset.author || "Developer";

        // Find the message containing the Reply button.
        const messageElement = replyButton.closest(
            ".cv-chat-message"
        );

        // Get the original message's content.
        const contentElement = messageElement?.querySelector(
            ".cv-chat-message-content"
        );

        const content = contentElement
            ? contentElement.textContent.trim()
            : "Attachment";

        // Prepare the reply.
        selectReply(messageId, author, content);

    });

    // ========================================================
    // FUNCTION 4 — HANDLE CANCEL REPLY
    // ========================================================

    cancelReplyButton.addEventListener("click", cancelReply);

});

// ============================================================
// MEETING ROOM — EDIT CHAT MESSAGES (INLINE EDITING)
// ============================================================

document.addEventListener("DOMContentLoaded", () => {

    // Get the container holding all chat messages.
    const chatMessages = document.getElementById("chat-messages");

    if (!chatMessages) {
        return;
    }

    // Listen for clicks on Edit, Save, and Cancel.
    chatMessages.addEventListener("click", async (event) => {

        const editButton = event.target.closest(".cv-chat-edit-button");
        const saveButton = event.target.closest(".cv-chat-save-button");
        const cancelButton = event.target.closest(".cv-chat-cancel-edit-button");

        // Ignore clicks unrelated to editing.
        if (!editButton && !saveButton && !cancelButton) {
            return;
        }

        // Find the message containing the clicked button.
        const messageElement = event.target.closest(".cv-chat-message");

        if (!messageElement) {
            return;
        }

        // Find the message's content.
        const contentElement = messageElement.querySelector(
            ".cv-chat-message-content"
        );

        if (!contentElement) {
            return;
        }

        // ====================================================
        // FUNCTION 1 — START EDITING
        // ====================================================

        if (editButton) {

            // Prevent opening multiple editors for one message.
            if (messageElement.querySelector(".cv-chat-edit-textarea")) {
                return;
            }

            // Remember the original message.
            const originalContent = contentElement.textContent.trim();

            // Create an editable textarea.
            const textarea = document.createElement("textarea");

            textarea.className = "cv-chat-edit-textarea";
            textarea.value = originalContent;
            textarea.rows = 3;

            // Create Save button.
            const save = document.createElement("button");

            save.type = "button";
            save.className = "cv-chat-save-button";
            save.textContent = "Save";

            // Create Cancel button.
            const cancel = document.createElement("button");

            cancel.type = "button";
            cancel.className = "cv-chat-cancel-edit-button";
            cancel.textContent = "Cancel";

            // Create a container for the buttons.
            const controls = document.createElement("div");

            controls.className = "cv-chat-edit-controls";

            controls.appendChild(save);
            controls.appendChild(cancel);

            // Create a container for the editor.
            const editor = document.createElement("div");

            editor.className = "cv-chat-inline-editor";

            editor.appendChild(textarea);
            editor.appendChild(controls);

            // Hide the original content while editing.
            contentElement.hidden = true;

            // Insert the editor after the message content.
            contentElement.after(editor);

            // Hide the Edit button while editing.
            editButton.hidden = true;

            // Focus the textarea.
            textarea.focus();

            return;
        }

        // ====================================================
        // FUNCTION 2 — CANCEL EDITING
        // ====================================================

        if (cancelButton) {

            // Remove the inline editor.
            messageElement.querySelector(
                ".cv-chat-inline-editor"
            )?.remove();

            // Show the original message.
            contentElement.hidden = false;

            // Show the Edit button again.
            const originalEditButton = messageElement.querySelector(
                ".cv-chat-edit-button"
            );

            if (originalEditButton) {
                originalEditButton.hidden = false;
            }

            return;
        }

        // ====================================================
        // FUNCTION 3 — SAVE EDITED MESSAGE
        // ====================================================

        if (saveButton) {

            // Find the textarea.
            const textarea = messageElement.querySelector(
                ".cv-chat-edit-textarea"
            );

            if (!textarea) {
                return;
            }

            // Get the updated message.
            const newContent = textarea.value.trim();

            if (!newContent) {
                alert("Message cannot be empty.");
                return;
            }

            // Get the Django edit endpoint.
            const editUrl = messageElement.dataset.editUrl;

            if (!editUrl) {
                alert("Edit URL is missing.");
                return;
            }

            // Get the CSRF token.
            const csrfToken = document.querySelector(
                "#meeting-chat-form input[name='csrfmiddlewaretoken']"
            )?.value;

            if (!csrfToken) {
                alert("CSRF token is missing.");
                return;
            }

            // Prepare the message.
            const formData = new FormData();

            formData.append("content", newContent);

            // Prevent multiple Save clicks.
            saveButton.disabled = true;

            try {

                // Send the updated message to Django.
                const response = await fetch(editUrl, {
                    method: "POST",
                    credentials: "same-origin",
                    headers: {
                        "X-CSRFToken": csrfToken,
                        "X-Requested-With": "XMLHttpRequest",
                    },
                    body: formData,
                });

                // Read the server response.
                const data = await response.json();

                if (!response.ok || !data.success) {
                    throw new Error(
                        data.error || "Unable to edit message."
                    );
                }

                // Update the visible message.
                contentElement.textContent = data.content ?? newContent;

                // Remove the editor.
                messageElement.querySelector(
                    ".cv-chat-inline-editor"
                )?.remove();

                // Show the updated message.
                contentElement.hidden = false;

                // Restore the Edit button.
                const originalEditButton = messageElement.querySelector(
                    ".cv-chat-edit-button"
                );

                if (originalEditButton) {
                    originalEditButton.hidden = false;
                }

            } catch (error) {

                alert(error.message);

                // Allow the developer to try saving again.
                saveButton.disabled = false;
            }
        }

    });

});
// ============================================================
// MEETING ROOM — DELETE CHAT MESSAGES
// ============================================================

document.addEventListener("DOMContentLoaded", () => {

    // Get the container holding all chat messages.
    const chatMessages = document.getElementById("chat-messages");

    if (!chatMessages) {
        return;
    }

    // Listen for Delete, Cancel, and Confirm button clicks.
    chatMessages.addEventListener("click", async (event) => {

        // Find the button that was clicked.
        const deleteButton = event.target.closest(".cv-chat-delete-button");
        const cancelButton = event.target.closest(".cv-chat-delete-cancel");
        const confirmButton = event.target.closest(".cv-chat-delete-confirm");

        // Ignore clicks unrelated to deletion.
        if (!deleteButton && !cancelButton && !confirmButton) {
            return;
        }

        // Find the message containing the clicked button.
        const messageElement = event.target.closest(".cv-chat-message");

        if (!messageElement) {
            return;
        }

        // ====================================================
        // FUNCTION 1 — CANCEL DELETION
        // ====================================================

        if (cancelButton) {

            // Remove the confirmation box.
            messageElement.querySelector(
                ".cv-chat-delete-confirmation"
            )?.remove();

            // Stop here. Do not delete anything.
            return;
        }

        // ====================================================
        // FUNCTION 2 — SHOW DELETE CONFIRMATION
        // ====================================================

        if (deleteButton) {

            // Prevent multiple confirmation boxes.
            if (messageElement.querySelector(".cv-chat-delete-confirmation")) {
                return;
            }

            // Create the confirmation box.
            const confirmation = document.createElement("div");

            confirmation.className = "cv-chat-delete-confirmation";

            // Create the question.
            const question = document.createElement("p");

            question.textContent = "Are you sure you want to delete this message?";

            // Create the Cancel button.
            const cancel = document.createElement("button");

            cancel.type = "button";
            cancel.className = "cv-chat-delete-cancel";
            cancel.textContent = "Cancel";

            // Create the Confirm button.
            const confirm = document.createElement("button");

            confirm.type = "button";
            confirm.className = "cv-chat-delete-confirm";
            confirm.textContent = "Yes, Delete";

            // Add the elements to the confirmation box.
            confirmation.appendChild(question);
            confirmation.appendChild(cancel);
            confirmation.appendChild(confirm);

            // Display the confirmation inside the message.
            messageElement.appendChild(confirmation);

            // IMPORTANT:
            // Stop here. Wait for the developer to click
            // Cancel or Yes, Delete before continuing.
            return;
        }

        // ====================================================
        // FUNCTION 3 — CONFIRM AND DELETE MESSAGE
        // ====================================================

        if (confirmButton) {

            // Get the Django delete URL.
            const deleteUrl = messageElement.dataset.deleteUrl;

            if (!deleteUrl) {
                alert("Delete URL is missing.");
                return;
            }

            // Get Django's CSRF token.
            const csrfToken = document.querySelector(
                "#meeting-chat-form input[name='csrfmiddlewaretoken']"
            )?.value;

            if (!csrfToken) {
                alert("CSRF token is missing.");
                return;
            }

            // Prevent duplicate requests.
            confirmButton.disabled = true;
            confirmButton.textContent = "Deleting...";

            try {

                // Send the delete request to Django.
                const response = await fetch(deleteUrl, {
                    method: "POST",
                    credentials: "same-origin",
                    headers: {
                        "X-CSRFToken": csrfToken,
                        "X-Requested-With": "XMLHttpRequest",
                    },
                });

                // Read Django's response.
                const data = await response.json();

                // Check whether deletion succeeded.
                if (!response.ok || !data.success) {
                    throw new Error(
                        data.error || "Unable to delete message."
                    );
                }

                // Remove the deleted message from the chat.
                messageElement.remove();

            } catch (error) {

                alert(error.message);

                // Allow the developer to try again.
                confirmButton.disabled = false;
                confirmButton.textContent = "Yes, Delete";
            }
        }

    });

});