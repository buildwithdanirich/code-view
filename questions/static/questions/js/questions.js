document.addEventListener("DOMContentLoaded", function () {

    // =====================================================
    // 1. MOBILE SIDEBAR NAVIGATION
    // =====================================================
    //
    // Desktop:
    // - Sidebar remains visible.
    //
    // Mobile (700px and below):
    // - Sidebar is hidden initially.
    // - Menu button opens and closes the sidebar.
    // - Escape closes the menu.
    // - Clicking a navigation link closes the menu.
    // - Resizing to desktop resets the mobile menu.
    // =====================================================

    const mobileMenuButton = document.querySelector(
        "[data-mobile-menu-toggle]"
    );

    const mobileSidebar = document.getElementById(
        "site-sidebar"
    );

    const mobileBreakpoint = window.matchMedia(
        "(max-width: 700px)"
    );

    if (mobileMenuButton && mobileSidebar) {

        // Update the menu's visible and accessible state.
        function setMobileMenuOpen(isOpen) {

            mobileSidebar.classList.toggle(
                "is-open",
                isOpen
            );

            mobileMenuButton.setAttribute(
                "aria-expanded",
                String(isOpen)
            );

            mobileMenuButton.setAttribute(
                "aria-label",
                isOpen
                    ? "Close navigation menu"
                    : "Open navigation menu"
            );

        }


        // =================================================
        // HANDLE MENU BUTTON
        // =================================================

        mobileMenuButton.addEventListener(
            "click",
            function () {

                // Only toggle the sidebar on mobile screens.
                if (!mobileBreakpoint.matches) {
                    return;
                }

                const isCurrentlyOpen =
                    mobileSidebar.classList.contains(
                        "is-open"
                    );

                setMobileMenuOpen(!isCurrentlyOpen);

            }
        );


        // =================================================
        // CLOSE MENU WITH ESCAPE
        // =================================================

        document.addEventListener(
            "keydown",
            function (event) {

                if (
                    event.key === "Escape" &&
                    mobileBreakpoint.matches &&
                    mobileSidebar.classList.contains("is-open")
                ) {

                    setMobileMenuOpen(false);

                    // Return keyboard focus to the menu button.
                    mobileMenuButton.focus();

                }

            }
        );


        // =================================================
        // CLOSE MENU AFTER SELECTING A LINK
        // =================================================

        mobileSidebar.querySelectorAll("a").forEach(
            function (link) {

                link.addEventListener(
                    "click",
                    function () {

                        if (mobileBreakpoint.matches) {
                            setMobileMenuOpen(false);
                        }

                    }
                );

            }
        );


        // =================================================
        // RESET MENU WHEN SCREEN SIZE CHANGES
        // =================================================

        mobileBreakpoint.addEventListener(
            "change",
            function () {

                // Prevent stale mobile state when switching
                // between mobile and desktop layouts.
                setMobileMenuOpen(false);

            }
        );


        // Start with the mobile menu closed.
        setMobileMenuOpen(false);

    }


    // =====================================================
    // 2. SHOW / HIDE REPLY FORMS
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
    // 3. CONFIRM DESTRUCTIVE ACTIONS
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
    // 4. SHARED AJAX LIKE HANDLER
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
    // 5. QUESTION LIKES (COMMUNITY FEED)
    // =====================================================

    setupLikeForms({
        formSelector: "[data-question-like-form]",
        buttonSelector: "[data-question-like-button]",
        iconSelector: "[data-question-like-icon]",
        labelSelector: "[data-question-like-label]",
        countSelector: "[data-question-like-count]"
    });


    // =====================================================
    // 6. COMMENT AND REPLY LIKES
    // =====================================================

    setupLikeForms({
        formSelector: "[data-comment-like-form]",
        buttonSelector: "[data-comment-like-button]",
        iconSelector: "[data-comment-like-icon]",
        countSelector: "[data-comment-like-count]"
    });

});