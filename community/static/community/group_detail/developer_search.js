document.addEventListener("DOMContentLoaded", function () {

    // =====================================================
    // 1. GET HTML ELEMENTS
    // =====================================================

    const searchInput = document.getElementById("developer-search");

    const resultsBox = document.getElementById(
        "developer-search-results"
    );

    const selectedUserInput = document.getElementById(
        "invite-user-id"
    );

    const invitationForm = document.getElementById(
        "invite-developer-form"
    );

    if (!searchInput || !resultsBox) {
        return;
    }

    const searchURL = searchInput.dataset.searchUrl;

    if (!searchURL) {
        console.error("Developer search URL is missing.");
        return;
    }

    // =====================================================
    // 2. SEARCH SETTINGS
    // =====================================================

    let searchTimer = null;
    let controller = null;
    let selectedDeveloper = null;
    let searchVersion = 0;

    // =====================================================
    // 3. CLEAR SELECTED DEVELOPER
    // =====================================================

    function clearSelection() {

        selectedDeveloper = null;

        if (selectedUserInput) {
            selectedUserInput.value = "";
        }
    }

    // =====================================================
    // 4. DISPLAY SEARCH STATUS
    // =====================================================

    function showMessage(message) {

        resultsBox.replaceChildren();

        const paragraph = document.createElement("p");

        paragraph.className = "developer-search-message";
        paragraph.textContent = message;

        resultsBox.appendChild(paragraph);
    }

    // =====================================================
    // 5. BUILD DEVELOPER PROFILE URL
    // =====================================================

    function getProfileURL(developer) {

        let profilePath;

        if (
            typeof developer.profile_url === "string" &&
            developer.profile_url.startsWith("/") &&
            !developer.profile_url.startsWith("//")
        ) {
            profilePath = developer.profile_url;
        } else {
            profilePath = "/developers/" +
                encodeURIComponent(developer.username) +
                "/";
        }

        const profileURL = new URL(
            profilePath,
            window.location.origin
        );

        // Return to this group's Members section.
        const returnURL = new URL(window.location.href);

        returnURL.hash = "group-members";

        profileURL.searchParams.set(
            "next",
            returnURL.pathname +
            returnURL.search +
            returnURL.hash
        );

        return profileURL.pathname + profileURL.search;
    }

    // =====================================================
    // 6. CREATE DEVELOPER AVATAR
    // =====================================================

    function createAvatar(developer) {

        const avatar = document.createElement("span");

        avatar.className = "developer-result-avatar";

        if (
            typeof developer.avatar_url === "string" &&
            developer.avatar_url.startsWith("/") &&
            !developer.avatar_url.startsWith("//")
        ) {

            const image = document.createElement("img");

            image.src = developer.avatar_url;
            image.alt = "";
            image.loading = "lazy";
            image.width = 40;
            image.height = 40;

            avatar.appendChild(image);

        } else {

            avatar.textContent = developer.username
                .charAt(0)
                .toUpperCase();
        }

        return avatar;
    }

    // =====================================================
    // 7. CHECK INVITATION STATUS
    // =====================================================

    function isAlreadyInvited(developer) {

        // Pending means the invitation is awaiting a response.
        return developer.invitation_status === "pending";
    }

    // =====================================================
    // 8. SELECT DEVELOPER FOR INVITATION
    // =====================================================

    function selectDeveloper(developer) {

        // Never select a developer with a pending invitation.
        if (isAlreadyInvited(developer)) {
            return;
        }

        selectedDeveloper = developer;

        searchInput.value = developer.username;

        if (selectedUserInput) {
            selectedUserInput.value = developer.id;
        }

        clearTimeout(searchTimer);

        if (controller) {
            controller.abort();
        }

        searchVersion += 1;

        resultsBox.replaceChildren();

        searchInput.focus();
    }

    // =====================================================
    // 9. CREATE DEVELOPER SEARCH RESULT
    // =====================================================

    function createDeveloperResult(developer) {

        const result = document.createElement("div");

        result.className = "developer-search-result";

        // -------------------------------------------------
        // Developer identity
        // -------------------------------------------------

        const identity = document.createElement("div");

        identity.className = "developer-result-identity";

        // Clickable avatar.
        const avatarLink = document.createElement("a");

        avatarLink.className = "developer-result-avatar-link";
        avatarLink.href = getProfileURL(developer);

        // No target="_blank": open in the SAME tab.
        avatarLink.setAttribute(
            "aria-label",
            "View " + developer.username + "'s profile"
        );

        avatarLink.appendChild(createAvatar(developer));

        // Username and profile link.
        const information = document.createElement("div");

        information.className = "developer-result-information";

        const usernameLink = document.createElement("a");

        usernameLink.className = "developer-result-username";
        usernameLink.href = getProfileURL(developer);
        usernameLink.textContent = developer.username;

        // Secondary profile link.
        const profileLink = document.createElement("a");

        profileLink.className = "developer-result-profile-link";
        profileLink.href = getProfileURL(developer);
        profileLink.textContent = "View Profile";

        information.appendChild(usernameLink);
        information.appendChild(profileLink);

        identity.appendChild(avatarLink);
        identity.appendChild(information);

        // -------------------------------------------------
        // Invitation status / selection button
        // -------------------------------------------------

        const inviteButton = document.createElement("button");

        inviteButton.type = "button";
        inviteButton.className = "developer-result-invite";

        if (isAlreadyInvited(developer)) {

            // Developer already has a pending invitation.
            inviteButton.textContent = "✓ Invited";

            inviteButton.disabled = true;

            inviteButton.classList.add(
                "developer-result-invited"
            );

            inviteButton.setAttribute(
                "aria-label",
                developer.username + " has already been invited"
            );

            result.classList.add(
                "developer-search-result-invited"
            );

        } else {

            // Developer can be selected for invitation.
            inviteButton.textContent = "Select";

            inviteButton.setAttribute(
                "aria-label",
                "Select " + developer.username + " for invitation"
            );

            inviteButton.addEventListener("click", function () {

                selectDeveloper(developer);
            });
        }

        result.appendChild(identity);
        result.appendChild(inviteButton);

        return result;
    }

    // =====================================================
    // 10. SEARCH REGISTERED DEVELOPERS
    // =====================================================

    searchInput.addEventListener("input", function () {

        clearSelection();

        clearTimeout(searchTimer);

        if (controller) {
            controller.abort();
        }

        searchVersion += 1;

        const currentVersion = searchVersion;

        const query = searchInput.value.trim();

        resultsBox.replaceChildren();

        if (query.length < 2) {
            return;
        }

        searchTimer = setTimeout(async function () {

            const requestController = new AbortController();

            controller = requestController;

            try {

                const url = new URL(
                    searchURL,
                    window.location.origin
                );

                url.searchParams.set("q", query);

                const response = await fetch(
                    url.toString(),
                    {
                        method: "GET",
                        credentials: "same-origin",
                        signal: requestController.signal
                    }
                );

                if (!response.ok) {
                    throw new Error("Developer search failed.");
                }

                const data = await response.json();

                if (!Array.isArray(data.users)) {
                    throw new Error(
                        "Invalid developer search response."
                    );
                }

                // Ignore outdated search responses.
                if (
                    currentVersion !== searchVersion ||
                    searchInput.value.trim() !== query
                ) {
                    return;
                }

                resultsBox.replaceChildren();

                if (data.users.length === 0) {

                    showMessage("No developers found.");
                    return;
                }

                data.users.forEach(function (developer) {

                    // Validate the developer information.
                    if (
                        !developer ||
                        typeof developer.username !== "string" ||
                        !developer.username ||
                        !Number.isSafeInteger(developer.id) ||
                        developer.id <= 0
                    ) {
                        return;
                    }

                    const result = createDeveloperResult(developer);

                    resultsBox.appendChild(result);
                });

                if (!resultsBox.children.length) {
                    showMessage("No developers found.");
                }

            } catch (error) {

                if (error.name === "AbortError") {
                    return;
                }

                if (currentVersion !== searchVersion) {
                    return;
                }

                console.error("Developer search error:", error);

                showMessage("Unable to search developers.");
            }

        }, 250);
    });

    // =====================================================
    // 11. CLOSE RESULTS WHEN CLICKING OUTSIDE
    // =====================================================

    document.addEventListener("click", function (event) {

        if (
            !searchInput.contains(event.target) &&
            !resultsBox.contains(event.target)
        ) {
            resultsBox.replaceChildren();
        }
    });

    // =====================================================
    // 12. VALIDATE INVITATION FORM
    // =====================================================

    if (invitationForm) {

        invitationForm.addEventListener("submit", function (event) {

            if (!selectedDeveloper) {

                event.preventDefault();

                alert(
                    "Please select a developer from the search results."
                );

                searchInput.focus();
                return;
            }

            // Prevent submitting a pending invitation again.
            if (isAlreadyInvited(selectedDeveloper)) {

                event.preventDefault();

                alert(
                    "This developer already has a pending invitation."
                );

                return;
            }

            // Verify the selected developer ID.
            if (
                selectedUserInput &&
                String(selectedDeveloper.id) !==
                selectedUserInput.value
            ) {

                event.preventDefault();

                alert("Developer selection is invalid.");
                return;
            }

            // Prevent accidental duplicate submissions.
            const submitButton = invitationForm.querySelector(
                'button[type="submit"]'
            );

            if (submitButton) {

                submitButton.disabled = true;
                submitButton.textContent = "Sending Invitation...";
            }

            // Django performs the final permission,
            // invitation-status, and membership checks.
        });
    }

});