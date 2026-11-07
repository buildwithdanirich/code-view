"use strict";

/*
========================================================
CODEVIEW - DISCUSSION INTERACTIONS
========================================================

Responsibilities:

1. Handle the Back button.
2. Send Like/Unlike requests to Django.
3. Update the Like button without refreshing.
4. Update the number of likes.
5. Display errors when requests fail.

This JavaScript can be reused on multiple pages.
*/

document.addEventListener("DOMContentLoaded", () => {

    // ====================================================
    // 1. BACK BUTTON
    // ====================================================

    // Find all Back buttons on the page.
    const backButtons = document.querySelectorAll(
        ".page-back-button"
    );

    // Attach a click event to each Back button.
    backButtons.forEach(function(button) {

        button.addEventListener("click", function() {

            // Read the fallback URL stored in the HTML.
            const fallbackURL = button.dataset.fallbackUrl || "/";

            // Get the page the developer came from.
            const previousPage = document.referrer;

            if (previousPage) {

                try {

                    // Convert the previous address into a URL object.
                    const previousURL = new URL(previousPage);

                  // Go back only when browser history exists
// and the previous page belongs to CodeView.
                    if (
                        window.history.length > 1 &&
                        previousURL.origin === window.location.origin &&
                        previousURL.pathname !== window.location.pathname
                    ) {

                        window.history.back();

                        return;
                    }

                } catch (error) {

                    // If the previous URL is invalid,
                    // continue to the fallback below.
                }
            }

            // Open the groups dashboard if going back is unsafe.
            window.location.href = fallbackURL;

        });

    });


    // ====================================================
    // 2. FIND DISCUSSION LIKE FORMS
    // ====================================================

    // Find Like forms on the group and discussion pages.
    const likeForms = document.querySelectorAll(
        ".like-form, #like-form"
    );

    // Give each Like form its own submit event.
    likeForms.forEach(function(form) {

        form.addEventListener("submit", async function(event) {

            // Stop the browser from reloading the page.
            event.preventDefault();


            // ====================================================
            // 3. FIND THE DISCUSSION ELEMENTS
            // ====================================================

            // Get the discussion ID stored in the form.
            const discussionId = form.dataset.discussionId;

            // Find the Like button.
            const button = form.querySelector(".like-button");

            // Stop if the button does not exist
            // or a request is already processing.
            if (!button || button.disabled) {
                return;
            }

            // Find the text inside the Like button.
            const label = button.querySelector(".like-label");

            // Find the Like count for this discussion.
            const countElement = discussionId
                ? document.getElementById(
                    "like-count-" + discussionId
                )
                : document.querySelector("#like-count");

            // Find the container for displaying errors.
            const errorElement = discussionId
                ? document.getElementById(
                    "like-error-" + discussionId
                )
                : document.querySelector("#like-error");


            // ====================================================
            // 4. PREPARE THE REQUEST
            // ====================================================

            // Clear any previous error message.
            if (errorElement) {

                errorElement.hidden = true;

                errorElement.textContent = "";
            }

            // Prevent repeated clicks while Django saves the Like.
            button.disabled = true;


            // ====================================================
            // 5. SEND REQUEST TO DJANGO
            // ====================================================

            try {

                // Send a POST request to the form's Django URL.
                const response = await fetch(form.action, {

                    method: "POST",

                    // Include form values and Django's CSRF token.
                    body: new FormData(form),

                    // Tell Django this is an AJAX request.
                    headers: {
                        "X-Requested-With": "XMLHttpRequest"
                    },

                    // Include cookies for this website.
                    credentials: "same-origin"

                });


                // Stop if Django returns an error.
                if (!response.ok) {

                    throw new Error(
                        "Unable to update your like. Please try again."
                    );
                }


                // ====================================================
                // 6. READ DJANGO'S RESPONSE
                // ====================================================

                // Convert Django's JSON response into a JS object.
                const data = await response.json();
                // Confirm Django returned the expected Like information.
        if (
        typeof data.liked !== "boolean" ||
        !Number.isInteger(data.like_count) ||
        data.like_count < 0
     ) {
        throw new Error("Invalid response from the server.");
    }


                // ====================================================
                // 7. UPDATE THE LIKE BUTTON
                // ====================================================

                if (data.liked) {

                    // Make the button green.
                    button.classList.add("liked");

                    // Mark the button as pressed for accessibility.
                    button.setAttribute("aria-pressed", "true");

                    // Change the button text.
                    if (label) {
                        label.textContent = "💚 Liked";
                    }

                } else {

                    // Remove the green appearance.
                    button.classList.remove("liked");

                    // Mark the button as not pressed.
                    button.setAttribute("aria-pressed", "false");

                    // Change the button text.
                    if (label) {
                        label.textContent = "♡ Like";
                    }
                }


                // ====================================================
                // 8. UPDATE THE LIKE COUNT
                // ====================================================

                // Use the number returned by Django.
                if (countElement) {

                    countElement.textContent = data.like_count;
                }


            } catch (error) {

                // ====================================================
                // 9. HANDLE REQUEST ERRORS
                // ====================================================

                if (errorElement) {

                    // Show the error to the developer.
                    errorElement.textContent = error.message;

                    errorElement.hidden = false;

                } else {

                    // Log errors when no error container exists.
                    console.error(
                        "CodeView Like request failed:",
                        error
                    );
                }

            } finally {

                // ====================================================
                // 10. ENABLE THE BUTTON AGAIN
                // ====================================================

                // Allow another Like/Unlike request.
                button.disabled = false;
            }

        });

    });
        // ====================================================
    // 11. SUBMIT COMMENTS AND REPLIES WITHOUT REFRESHING
    // ====================================================

    // Listen for submissions from comment and reply forms.
    document.addEventListener("submit", async function(event) {

        // Find the comment or reply form being submitted.
        const form = event.target.closest(
            "#comments-section form, #discussion-comments form"
        );

        // Ignore unrelated forms.
        if (!form) {
            return;
        }

        // Stop the browser from refreshing.
        event.preventDefault();

        // Find the submit button.
        const button = form.querySelector('button[type="submit"]');

        // Prevent duplicate submissions.
        if (button && button.disabled) {
            return;
        }

        if (button) {
            button.disabled = true;
        }

        try {

            // Collect comment content, CSRF token, and parent ID.
            const formData = new FormData(form);

            // Send the comment to Django.
            const response = await fetch(form.action, {
                method: "POST",
                body: formData,
                headers: {
                    "X-Requested-With": "XMLHttpRequest"
                }
            });

// Read Django's JSON response.
const data = await response.json();

// Check whether Django rejected the comment.
if (!response.ok || !data.success) {

    // Get the error message returned by Django.
    const errorMessage =
        data.error || "Unable to post comment.";

    // Display the error using the existing catch block.
    throw new Error(errorMessage);
}

            // Clear the comment box after successful submission.
            form.reset();

            // The WebSocket will display the saved comment.

        } catch (error) {

            console.error("CodeView comment error:", error);

            alert(error.message);

        } finally {

            // Allow another comment submission.
            if (button) {
                button.disabled = false;
            }
        }
    });

    // ====================================================
    // 12. REAL-TIME DISCUSSION LIKE UPDATES
    // ====================================================
// Get the WebSocket URL provided by Django.
const discussionSocketUrl = document.body.dataset.discussionSocketUrl;

// Store the timer used for reconnecting.
let reconnectTimer = null;

// Create a function responsible for connecting to Django Channels.
function connectDiscussionSocket() {

    // Do nothing if the page has no WebSocket URL.
    if (!discussionSocketUrl) {
        return;
    }

    // Establish a new WebSocket connection.
    const socket = new WebSocket(discussionSocketUrl);

    // Run when the WebSocket successfully connects.
    socket.addEventListener("open", function() {

        console.log("CodeView WebSocket connected.");
    });

    // Run when the WebSocket connection closes.
    socket.addEventListener("close", function() {

        console.log("CodeView WebSocket disconnected.");

        // Cancel any existing reconnection timer.
        if (reconnectTimer !== null) {
            clearTimeout(reconnectTimer);
        }

        // Wait three seconds before reconnecting.
        reconnectTimer = setTimeout(function() {

            reconnectTimer = null;

            // Try connecting again.
            connectDiscussionSocket();

        }, 3000);
    });

    // Listen for updates from Django Channels.
    socket.addEventListener("message", function(event) {

            // Convert the received JSON into a JavaScript object.
            const data = JSON.parse(event.data);

            // Check what Django Channels sends to the browser.
        console.log("CodeView WebSocket received:", data);

            // ====================================================
// 13. RECEIVE REAL-TIME DISCUSSION COMMENTS
// ====================================================

// Check whether Django Channels sent a new comment.
if (data.event === "discussion_comment") {
        // ====================================================
    // UPDATE THE DISCUSSION COMMENT COUNT
    // ====================================================

// Get the discussion ID stored in the current page.
const currentDiscussionId = document.body.dataset.discussionId;

// Only filter comments when viewing a specific discussion.
if (
    currentDiscussionId &&
    Number(currentDiscussionId) !== Number(data.discussion_id)
) {
    // Ignore comments belonging to another discussion.
    return;
}
    
    // Find the comment count for this discussion.
    const commentCountElement = document.getElementById(
        "comment-count-" + data.discussion_id
    );

    // Check that Django sent a valid comment count.
    if (
        commentCountElement &&
        Number.isInteger(data.comment_count) &&
        data.comment_count >= 0
    ) {

        // Update the count without refreshing.
        commentCountElement.textContent = data.comment_count;
    }

    // Find the comments section on the discussion page.
    const commentsSection = document.getElementById(
        "discussion-comments"
    );

    // The group workspace does not display full comments.
    if (!commentsSection) {
        return;
    }

    // ====================================================
// REMOVE THE EMPTY COMMENTS MESSAGE
// ====================================================

// Find the paragraphs inside the comments section.
const paragraphs = commentsSection.querySelectorAll(
    "p.group-description"
);

// Check each paragraph.
paragraphs.forEach(function(paragraph) {

    // Get the paragraph text without extra spaces.
    const text = paragraph.textContent.trim();

    // Remove the empty-state messages.
    if (
        text === "No comments yet." ||
        text === "Be the first to comment!"
    ) {
        paragraph.remove();
    }
});

    // Avoid displaying the same comment twice.
    if (document.getElementById("comment-" + data.comment_id)) {
        return;
    }

    // Create a new comment card.
    const commentCard = document.createElement("article");

    commentCard.className = "group-card discussion-comment";
    commentCard.id = "comment-" + data.comment_id;

    // Show the parent author when this is a reply.
    if (data.parent_id && data.parent_author) {

        const replyIndicator = document.createElement("p");
        replyIndicator.className = "reply-indicator";

        replyIndicator.textContent =
            "↳ Replying to " + data.parent_author;

        commentCard.appendChild(replyIndicator);
    }

    // Display the comment author and date.
    const authorElement = document.createElement("p");
    authorElement.className = "group-owner";

    authorElement.textContent =
        data.author + " · " + data.created_at;

    commentCard.appendChild(authorElement);

    // Display the comment content safely.
    const contentElement = document.createElement("p");
    contentElement.className = "group-description";

    contentElement.textContent = data.content;
    contentElement.style.whiteSpace = "pre-wrap";

    commentCard.appendChild(contentElement);


    // ====================================================
// CREATE A REPLY FORM FOR THE NEW COMMENT
// ====================================================

// Find the existing comment form to reuse its URL and CSRF token.
const originalForm = document.querySelector(
    "#comments-section form"
);

// Only group members have permission to reply.
if (originalForm) {

    // Create a new reply form.
    const replyForm = document.createElement("form");

    replyForm.method = "POST";
    replyForm.action = originalForm.action;

    // Copy the CSRF token from the existing form.
    const csrfToken = originalForm.querySelector(
        'input[name="csrfmiddlewaretoken"]'
    );

    if (csrfToken) {
        replyForm.appendChild(csrfToken.cloneNode(true));
    }

    // Identify which comment the developer is replying to.
    const parentInput = document.createElement("input");

    parentInput.type = "hidden";
    parentInput.name = "parent_id";
    parentInput.value = data.comment_id;

    replyForm.appendChild(parentInput);

    // Create a label for the reply box.
    const replyLabel = document.createElement("label");

    replyLabel.htmlFor = "reply-" + data.comment_id;
    replyLabel.textContent = "Reply to " + data.author;

    replyForm.appendChild(replyLabel);

    // Create the reply text box.
    const replyTextarea = document.createElement("textarea");

    replyTextarea.id = "reply-" + data.comment_id;
    replyTextarea.name = "content";
    replyTextarea.className = "group-textarea";
    replyTextarea.rows = 2;
    replyTextarea.maxLength = 2000;
    replyTextarea.placeholder = "Write a reply...";
    replyTextarea.required = true;

    replyForm.appendChild(replyTextarea);

    // Create the Reply button.
    const replyButton = document.createElement("button");

    replyButton.type = "submit";
    replyButton.className = "group-action";
    replyButton.textContent = "Reply";

    replyForm.appendChild(replyButton);

    // Display the reply form inside the new comment card.
    commentCard.appendChild(replyForm);
}

// Find the first existing comment.
const firstComment = commentsSection.querySelector(
    ".discussion-comment"
);

// Insert the new comment before existing comments.
if (firstComment) {

    commentsSection.insertBefore(
        commentCard,
        firstComment
    );

} else {

    // If there are no comments, add the first comment.
    commentsSection.appendChild(commentCard);
}

    return;
}

            // Ignore events that are not discussion Like updates.
            if (data.event !== "discussion_like") {
                return;
            }

            // Find the discussion whose Like count changed.
            const countElement = document.getElementById(
                "like-count-" + data.discussion_id
            ) || document.getElementById("like-count");

            // Validate the received count.
            if (
                !Number.isInteger(data.like_count) ||
                data.like_count < 0
            ) {
                return;
            }

            // Update the total number of likes.
            if (countElement) {
                countElement.textContent = data.like_count;
            }
        });

} // End connectDiscussionSocket().

// Start the first WebSocket connection.
connectDiscussionSocket();

}); // End DOMContentLoaded.