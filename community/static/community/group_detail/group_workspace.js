// ========================================
// CODEVIEW GROUP WORKSPACE
// Switch between Discussions, Chat,
// and Members without reloading the page.
// ========================================

document.addEventListener("DOMContentLoaded", function () {

    // Find all sidebar links that switch workspace sections.
    const tabs = document.querySelectorAll("[data-workspace-tab]");

    // Find the main workspace content.
    const workspaceContent = document.querySelector(".workspace-content");

    // Find the discussions, chat, and members sections.
    const discussionSections = [
        document.getElementById("create-discussion"),
        document.getElementById("group-discussions")
    ];

    const chatSection = document.getElementById("group-chat");

    const membersSection = document.getElementById("group-members");

    // Find the heading and group information.
    const workspaceHeading = document.querySelector(".workspace-heading");
    const groupInformation = document.querySelector(".workspace-group-info");

    // Find the membership notice for nonmembers.
    const membershipNotice = document.querySelector(".membership-notice");


    // ========================================
    // FUNCTION: SWITCH WORKSPACE TAB
    // ========================================

    function switchTab(tabName) {
        // Only allow the three supported workspace tabs.
        if (!["discussions", "chat", "members"].includes(tabName)) {
        return;
    } 

        // Check whether the selected section exists.
        if (tabName === "chat" && !chatSection) {
            return;
        }

        if (tabName === "members" && !membersSection) {
            return;
        }

        // ====================================
        // 1. HIDE ALL WORKSPACE SECTIONS
        // ====================================

        discussionSections.forEach(function (section) {

            if (section) {
                section.hidden = true;
            }

        });

        if (chatSection) {
            chatSection.hidden = true;
        }

        if (membersSection) {
            membersSection.hidden = true;
        }

        if (workspaceHeading) {
            workspaceHeading.hidden = true;
        }

        if (groupInformation) {
            groupInformation.hidden = true;
        }

        if (membershipNotice) {
            membershipNotice.hidden = true;
        }


        // ====================================
        // 2. SHOW THE SELECTED SECTION
        // ====================================

        if (tabName === "discussions") {

            discussionSections.forEach(function (section) {

                if (section) {
                    section.hidden = false;
                }

            });

            if (workspaceHeading) {
                workspaceHeading.hidden = false;
            }

            if (groupInformation) {
                groupInformation.hidden = false;
            }

            if (membershipNotice) {
                membershipNotice.hidden = false;
            }

        } else if (tabName === "chat") {

            chatSection.hidden = false;

        } else if (tabName === "members") {

            membersSection.hidden = false;

        }


        // ====================================
        // 3. UPDATE ACTIVE SIDEBAR LINK
        // ====================================

        tabs.forEach(function (tab) {

            const isActive = tab.dataset.workspaceTab === tabName;

            tab.classList.toggle("active", isActive);

            if (isActive) {
                tab.setAttribute("aria-current", "page");
            } else {
                tab.removeAttribute("aria-current");
            }

        });


        // ====================================
        // 4. SCROLL MAIN CONTENT TO TOP
        // ====================================

        if (workspaceContent) {
            workspaceContent.scrollTop = 0;
        }

    }


    // ========================================
    // FUNCTION: READ TAB FROM URL
    // ========================================

    function getTabFromURL() {

        const hash = window.location.hash;

        if (hash === "#group-chat") {
            return "chat";
        }

        if (hash === "#group-members") {
            return "members";
        }

        return "discussions";
    }


    // ========================================
    // HANDLE SIDEBAR CLICKS
    // ========================================

    tabs.forEach(function (tab) {

        tab.addEventListener("click", function (event) {

            // Prevent normal anchor navigation.
            event.preventDefault();

            // Get the selected tab name.
            const tabName = tab.dataset.workspaceTab;

           // Add the selected tab to browser history.
        window.history.pushState(
            null,
            "",
            tab.getAttribute("href")
        );
            // Display the selected section.
            switchTab(tabName);

        });

    });


    // ========================================
    // HANDLE BROWSER BACK/FORWARD HASH CHANGES
    // ========================================

    // Handle Back and Forward navigation.
window.addEventListener("popstate", function () {
    switchTab(getTabFromURL());
});

// Handle hash changes from normal links.
window.addEventListener("hashchange", function () {
    switchTab(getTabFromURL());
});


    // ========================================
    // DISPLAY INITIAL SECTION
    // ========================================

    switchTab(getTabFromURL());



    // ========================================
    // REMOVE DEVELOPER CONFIRMATION MODAL
    // ========================================

    // Find the modal and its buttons.
    const removeModal = document.getElementById("remove-member-modal");

    const cancelRemoveButton = document.getElementById(
        "cancel-remove-member"
    );

    const confirmRemoveButton = document.getElementById(
        "confirm-remove-member"
    );

    // Store the form belonging to the selected developer.
    let selectedRemoveForm = null;
    // Remember the button that opened the modal.
    let removeTriggerButton = null;

    if (removeModal && cancelRemoveButton && confirmRemoveButton) {

        // Find every Remove Member form.
        const removeForms = document.querySelectorAll(
            ".remove-member-form"
        );

        // Open the modal when a Remove button is clicked.
        removeForms.forEach(function (form) {

            form.addEventListener("submit", function (event) {

                // Stop the form from submitting immediately.
                event.preventDefault();

                // Remember which developer should be removed.
                selectedRemoveForm = form;
                // Remember the button that opened the confirmation.
removeTriggerButton = event.submitter || form.querySelector(
    'button[type="submit"]'
);

                // Display the confirmation modal.
                removeModal.hidden = false;

                // Move keyboard focus into the modal.
                cancelRemoveButton.focus();

            });

        });

        // Close the modal without removing the developer.
function closeRemoveModal() {

    // Hide the confirmation modal.
    removeModal.hidden = true;

    // Return keyboard focus to the Remove button.
    if (removeTriggerButton) {
        removeTriggerButton.focus();
    }

    // Clear the selected form and button.
    selectedRemoveForm = null;
    removeTriggerButton = null;
}

        // Cancel removal.
        cancelRemoveButton.addEventListener("click", function () {
            closeRemoveModal();
        });

        // Confirm removal.
        confirmRemoveButton.addEventListener("click", function () {

            if (selectedRemoveForm) {

                // Submit the original Django form.
                // This includes its CSRF token.
                selectedRemoveForm.submit();

            }

        });

        // Close the modal when clicking outside its content.
        const modalOverlay = removeModal.querySelector(
            ".codeview-modal-overlay"
        );

        if (modalOverlay) {

            modalOverlay.addEventListener("click", function () {
                closeRemoveModal();
            });

        }

        // Close the modal when Escape is pressed.
        document.addEventListener("keydown", function (event) {

            if (event.key === "Escape" && !removeModal.hidden) {
                closeRemoveModal();
            }

        });

    }

            // ========================================
    // LEAVE GROUP CONFIRMATION MODAL
    // ========================================

    // Find the Leave Group form and modal.
    const leaveForm = document.querySelector(".leave-group-form");

    const leaveModal = document.getElementById("leave-group-modal");

    const cancelLeaveButton = document.getElementById(
        "cancel-leave-group"
    );

    const confirmLeaveButton = document.getElementById(
        "confirm-leave-group"
    );

    if (leaveForm && leaveModal && cancelLeaveButton && confirmLeaveButton) {

        // Open the modal when the developer clicks Leave Group.
        leaveForm.addEventListener("submit", function (event) {

            // Stop the form from submitting immediately.
            event.preventDefault();

            // Display the custom modal.
            leaveModal.hidden = false;

            // Move keyboard focus into the modal.
            cancelLeaveButton.focus();
        });

       function closeLeaveModal() {

    // Hide the confirmation modal.
    leaveModal.hidden = true;

    // Return focus to the Leave Group button.
    const leaveButton = leaveForm.querySelector(
        'button[type="submit"]'
    );

    if (leaveButton) {
        leaveButton.focus();
    }
}

        // Cancel leaving.
        cancelLeaveButton.addEventListener("click", closeLeaveModal);

        // Confirm leaving.
        confirmLeaveButton.addEventListener("click", function () {

            // Submit the original Django form with its CSRF token.
            leaveForm.submit();
        });

        // Close the modal when clicking outside.
        const leaveOverlay = leaveModal.querySelector(
            ".codeview-modal-overlay"
        );

        if (leaveOverlay) {
            leaveOverlay.addEventListener("click", closeLeaveModal);
        }
        // Close the modal when Escape is pressed.
        document.addEventListener("keydown", function (event) {

            if (event.key === "Escape" && !leaveModal.hidden) {
                closeLeaveModal();
            }

        });

    } // End of Leave Group confirmation modal.

}); // End of DOMContentLoaded.