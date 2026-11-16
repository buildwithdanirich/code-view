document.addEventListener("DOMContentLoaded", function () {

    // =====================================================
    // 1. SHOW / HIDE REPLY FORMS
    // =====================================================

    document.querySelectorAll(".reply-toggle").forEach(function (button) {

        button.addEventListener("click", function () {

            const form = document.getElementById(
                button.dataset.target
            );

            if (form) {
                form.hidden = !form.hidden;
            }

        });

    });


    // =====================================================
    // 2. CONFIRM DESTRUCTIVE ACTIONS
    // =====================================================

    document.querySelectorAll("form[data-confirm]").forEach(function (form) {

        form.addEventListener("submit", function (event) {

            const message = form.dataset.confirm;

            if (message && !window.confirm(message)) {
                event.preventDefault();
            }

        });

    });


    // =====================================================
    // 3. SHARED AJAX LIKE HANDLER
    // =====================================================
    //
    // Used by:
    // - Community feed question likes
    // - Discussion comment likes
    // - Nested reply likes
    //
    // Sends a POST request without refreshing the page.
    // =====================================================

    function setupLikeForms(options) {

        document.querySelectorAll(
            options.formSelector
        ).forEach(function (form) {

            const button = form.querySelector(
                options.buttonSelector
            );

            const icon = form.querySelector(
                options.iconSelector
            );

            const count = form.querySelector(
                options.countSelector
            );

            const label = options.labelSelector
                ? form.querySelector(options.labelSelector)
                : null;

            const csrfInput = form.querySelector(
                'input[name="csrfmiddlewaretoken"]'
            );

            // If the HTML is incomplete, leave the normal
            // Django form behavior available.
            if (
                !button ||
                !icon ||
                !count ||
                !csrfInput ||
                (options.labelSelector && !label)
            ) {
                return;
            }

            // =================================================
            // HANDLE LIKE / UNLIKE
            // =================================================

            form.addEventListener("submit", async function (event) {

                // Stop the browser from refreshing or navigating.
                event.preventDefault();

                // Ignore duplicate submissions.
                if (button.disabled) {
                    return;
                }

                // Disable temporarily while Django processes it.
                button.disabled = true;

                button.setAttribute(
                    "aria-busy",
                    "true"
                );

                try {

                    // Send the Like/Unlike request to Django.
                    const response = await fetch(
                        form.action,
                        {
                            method: "POST",

                            credentials: "same-origin",

                            headers: {
                                "X-CSRFToken": csrfInput.value,
                                "X-Requested-With": "XMLHttpRequest",
                                "Accept": "application/json"
                            }
                        }
                    );

                    // If the login session expired,
                    // Django may redirect to the login page.
                    if (response.redirected) {
                        window.location.href = response.url;
                        return;
                    }

                    // Read Django's JSON response.
                    const data = await response.json();

                    // Handle errors from Django.
                    if (!response.ok) {
                        throw new Error(
                            data.error ||
                            "Unable to update this like."
                        );
                    }

                    // Ensure Django returned valid information.
                    if (
                        typeof data.liked !== "boolean" ||
                        !Number.isSafeInteger(data.like_count) ||
                        data.like_count < 0
                    ) {
                        throw new Error(
                            "Invalid response from the server."
                        );
                    }

                    // =========================================
                    // UPDATE THE HEART
                    // =========================================

                    if (data.liked) {

                        icon.textContent = "♥";

                        button.classList.add("is-liked");

                        button.setAttribute(
                            "aria-pressed",
                            "true"
                        );

                        if (label) {
                            label.textContent = "Unlike";
                        }

                    } else {

                        icon.textContent = "♡";

                        button.classList.remove("is-liked");

                        button.setAttribute(
                            "aria-pressed",
                            "false"
                        );

                        if (label) {
                            label.textContent = "Like";
                        }

                    }

                    // =========================================
                    // UPDATE THE LIKE COUNT
                    // =========================================

                    count.textContent = data.like_count;

                } catch (error) {

                    console.error(
                        "Like request failed:",
                        error
                    );

                    window.alert(
                        error.message ||
                        "Something went wrong. Please try again."
                    );

                } finally {

                    // Re-enable the button only if it was
                    // allowed to be clicked initially.
                    button.disabled = false;

                    button.removeAttribute("aria-busy");

                }

            });

        });

    }


    // =====================================================
    // 4. QUESTION LIKES (COMMUNITY FEED)
    // =====================================================

    setupLikeForms({
        formSelector: "[data-question-like-form]",
        buttonSelector: "[data-question-like-button]",
        iconSelector: "[data-question-like-icon]",
        labelSelector: "[data-question-like-label]",
        countSelector: "[data-question-like-count]"
    });


    // =====================================================
    // 5. COMMENT AND REPLY LIKES
    // =====================================================

    setupLikeForms({
        formSelector: "[data-comment-like-form]",
        buttonSelector: "[data-comment-like-button]",
        iconSelector: "[data-comment-like-icon]",
        countSelector: "[data-comment-like-count]"
    });

});