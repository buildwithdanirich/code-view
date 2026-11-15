// ============================================================
// COLABVERSE — PRIVATE GROUP WORKSPACE
// File: group_workspace.js
//
// Responsibilities:
// 1. Open Group Chat by default.
// 2. Switch between Group Chat and Members.
// 3. Keep group information visible.
// 4. Support browser Back/Forward navigation.
// 5. Confirm member removal.
// 6. Confirm leaving a group.
//
// All functionality uses external JavaScript.
// ============================================================

document.addEventListener("DOMContentLoaded", function () {

    // ========================================================
    // 1. WORKSPACE NAVIGATION
    // ========================================================

    // Find navigation links for sections on this page.
    const tabs = document.querySelectorAll("[data-workspace-tab]");

    // Find the existing workspace panels.
    const chatSection = document.getElementById("group-chat");
    const membersSection = document.getElementById("group-members");

    // Find the scrollable workspace container.
    const workspaceMain = document.querySelector(".workspace-main");

    // Only these sections are supported.
    const supportedTabs = ["chat", "members"];


    // ========================================================
    // FUNCTION: GET THE ACTIVE TAB FROM THE URL
    // ========================================================

    function getTabFromURL() {

        // Members is selected when the URL ends in #group-members.
        if (window.location.hash === "#group-members") {
            return "members";
        }

        // Group Chat is the default for all other URLs.
        return "chat";
    }


    // ========================================================
    // FUNCTION: SWITCH WORKSPACE TAB
    // ========================================================

    function switchTab(tabName) {

        // Reject unsupported navigation values.
        if (!supportedTabs.includes(tabName)) {
            return;
        }

        // Do not switch to a section that does not exist.
        if (tabName === "chat" && !chatSection) {
            return;
        }

        if (tabName === "members" && !membersSection) {
            return;
        }

        // Hide both workspace panels.
        if (chatSection) {
            chatSection.hidden = true;
        }

        if (membersSection) {
            membersSection.hidden = true;
        }

        // Show the requested panel.
        if (tabName === "chat") {
            chatSection.hidden = false;
        }

        if (tabName === "members") {
            membersSection.hidden = false;
        }

        // Update the selected navigation link.
        tabs.forEach(function (tab) {

            const isActive = tab.dataset.workspaceTab === tabName;

            tab.classList.toggle("active", isActive);

            if (isActive) {
                tab.setAttribute("aria-current", "page");
            } else {
                tab.removeAttribute("aria-current");
            }
        });

        // Keep group information visible above the panels.
        // Only the chat and members panels are switched.

        // Return the main workspace to the top.
        if (workspaceMain) {
            workspaceMain.scrollTop = 0;
        }
    }


    // ========================================================
    // 2. HANDLE NAVIGATION CLICKS
    // ========================================================

    tabs.forEach(function (tab) {

        tab.addEventListener("click", function (event) {

            const tabName = tab.dataset.workspaceTab;

            // Ignore links without a supported workspace tab.
            if (!supportedTabs.includes(tabName)) {
                return;
            }

            // Prevent normal anchor scrolling.
            event.preventDefault();

            // Update the browser URL.
            const targetHash = tabName === "members"
                ? "#group-members"
                : "#group-chat";

            window.history.pushState(
                null,
                "",
                targetHash
            );

            // Display the selected workspace panel.
            switchTab(tabName);
        });
    });


    // ========================================================
    // 3. HANDLE BROWSER NAVIGATION
    // ========================================================

    // Handle browser Back and Forward buttons.
    window.addEventListener("popstate", function () {
        switchTab(getTabFromURL());
    });

    // Handle URL hash changes.
    window.addEventListener("hashchange", function () {
        switchTab(getTabFromURL());
    });


    // ========================================================
    // 4. DISPLAY THE INITIAL WORKSPACE
    // ========================================================

    // Members open Group Chat automatically unless
    // the URL explicitly selects the Members section.
    switchTab(getTabFromURL());


    // ========================================================
    // 5. REMOVE MEMBER CONFIRMATION MODAL
    // ========================================================

    const removeModal = document.getElementById(
        "remove-member-modal"
    );

    const cancelRemoveButton = document.getElementById(
        "cancel-remove-member"
    );

    const confirmRemoveButton = document.getElementById(
        "confirm-remove-member"
    );

    // Remember which membership form should be submitted.
    let selectedRemoveForm = null;

    // Remember which button opened the modal.
    let removeTriggerButton = null;

    if (
        removeModal &&
        cancelRemoveButton &&
        confirmRemoveButton
    ) {

        const removeForms = document.querySelectorAll(
            ".remove-member-form"
        );

        // Open confirmation before submitting a removal form.
        removeForms.forEach(function (form) {

            form.addEventListener("submit", function (event) {

                event.preventDefault();

                selectedRemoveForm = form;

                removeTriggerButton =
                    event.submitter ||
                    form.querySelector('button[type="submit"]');

                removeModal.hidden = false;

                // Move keyboard focus into the dialog.
                cancelRemoveButton.focus();
            });
        });


        // Close the dialog without removing anyone.
        function closeRemoveModal() {

            removeModal.hidden = true;

            // Return focus to the original button.
            if (removeTriggerButton) {
                removeTriggerButton.focus();
            }

            selectedRemoveForm = null;
            removeTriggerButton = null;
        }


        // Cancel removal.
        cancelRemoveButton.addEventListener(
            "click",
            closeRemoveModal
        );


        // Confirm removal.
        confirmRemoveButton.addEventListener("click", function () {

            if (!selectedRemoveForm) {
                return;
            }

            // Submit the original Django form.
            // Its CSRF token is preserved.
            selectedRemoveForm.submit();
        });


        // Close when clicking the modal overlay.
        const removeOverlay = removeModal.querySelector(
            ".codeview-modal-overlay"
        );

        if (removeOverlay) {

            removeOverlay.addEventListener(
                "click",
                closeRemoveModal
            );
        }


        // Close with Escape.
        document.addEventListener("keydown", function (event) {

            if (
                event.key === "Escape" &&
                !removeModal.hidden
            ) {
                closeRemoveModal();
            }
        });
    }


    // ========================================================
    // 6. LEAVE GROUP CONFIRMATION MODAL
    // ========================================================

    const leaveForm = document.querySelector(
        ".leave-group-form"
    );

    const leaveModal = document.getElementById(
        "leave-group-modal"
    );

    const cancelLeaveButton = document.getElementById(
        "cancel-leave-group"
    );

    const confirmLeaveButton = document.getElementById(
        "confirm-leave-group"
    );

    if (
        leaveForm &&
        leaveModal &&
        cancelLeaveButton &&
        confirmLeaveButton
    ) {

        // Remember the button used to open the dialog.
        const leaveTriggerButton = leaveForm.querySelector(
            'button[type="submit"]'
        );


        // Open confirmation instead of immediately leaving.
        leaveForm.addEventListener("submit", function (event) {

            event.preventDefault();

            leaveModal.hidden = false;

            cancelLeaveButton.focus();
        });


        // Close the confirmation dialog.
        function closeLeaveModal() {

            leaveModal.hidden = true;

            // Restore keyboard focus.
            if (leaveTriggerButton) {
                leaveTriggerButton.focus();
            }
        }


        // Cancel leaving the group.
        cancelLeaveButton.addEventListener(
            "click",
            closeLeaveModal
        );


        // Confirm leaving the group.
        confirmLeaveButton.addEventListener("click", function () {

            // Submit the original Django form with its CSRF token.
            leaveForm.submit();
        });


        // Close when clicking outside the dialog.
        const leaveOverlay = leaveModal.querySelector(
            ".codeview-modal-overlay"
        );

        if (leaveOverlay) {

            leaveOverlay.addEventListener(
                "click",
                closeLeaveModal
            );
        }


        // Close with Escape.
        document.addEventListener("keydown", function (event) {

            if (
                event.key === "Escape" &&
                !leaveModal.hidden
            ) {
                closeLeaveModal();
            }
        });
    }

});