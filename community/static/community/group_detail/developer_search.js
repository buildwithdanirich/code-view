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

    // Stop if developer search is unavailable.
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

    // Prevent outdated requests from updating the interface.
    let searchVersion = 0;


    // =====================================================
    // 3. HELPER: CLEAR SELECTED DEVELOPER
    // =====================================================

    function clearSelection() {

        selectedDeveloper = null;

        if (selectedUserInput) {
            selectedUserInput.value = "";
        }

    }


    // =====================================================
    // 4. HELPER: CREATE STATUS MESSAGE
    // =====================================================

    function showMessage(message) {

        resultsBox.replaceChildren();

        const paragraph = document.createElement("p");

        paragraph.className = "developer-search-message";

        paragraph.textContent = message;

        resultsBox.appendChild(paragraph);

    }


    // =====================================================
    // 5. HELPER: BUILD PUBLIC PROFILE URL
    // =====================================================

    function getProfileURL(developer) {

        // Use the profile URL supplied by Django when available.
        if (
            typeof developer.profile_url === "string" &&
            developer.profile_url.startsWith("/") &&
            !developer.profile_url.startsWith("//")
        ) {
            return developer.profile_url;
        }

        // Fall back to the existing ColabVerse profile route.
        return "/developers/" +
            encodeURIComponent(developer.username) +
            "/";

    }


    // =====================================================
    // 6. HELPER: CREATE DEVELOPER AVATAR
    // =====================================================

    function createAvatar(developer) {

        const avatar = document.createElement("span");

        avatar.className = "developer-result-avatar";

        // Display the uploaded photo if Django provides one.
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
    // 7. SELECT DEVELOPER FOR INVITATION
    // =====================================================

    function selectDeveloper(developer) {

        // Remember the selected developer.
        selectedDeveloper = developer;

        // Display the selected username.
        searchInput.value = developer.username;

        // Store the selected developer ID.
        if (selectedUserInput) {
            selectedUserInput.value = developer.id;
        }

        // Cancel pending searches.
        clearTimeout(searchTimer);

        if (controller) {
            controller.abort();
        }

        searchVersion += 1;

        // Close the results dropdown.
        resultsBox.replaceChildren();

        // Return focus to the search input.
        searchInput.focus();

    }


    // =====================================================
    // 8. CREATE ONE DEVELOPER SEARCH RESULT
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

        avatarLink.target = "_blank";

        avatarLink.rel = "noopener noreferrer";

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

        usernameLink.target = "_blank";

        usernameLink.rel = "noopener noreferrer";

        usernameLink.textContent = developer.username;


        // Secondary profile link.
        const profileLink = document.createElement("a");

        profileLink.className = "developer-result-profile-link";

        profileLink.href = getProfileURL(developer);

        profileLink.target = "_blank";

        profileLink.rel = "noopener noreferrer";

        profileLink.textContent = "View Profile";


        information.appendChild(usernameLink);

        information.appendChild(profileLink);

        identity.appendChild(avatarLink);

        identity.appendChild(information);


        // -------------------------------------------------
        // Invitation selection button
        // -------------------------------------------------

        const inviteButton = document.createElement("button");

        inviteButton.type = "button";

        inviteButton.className = "developer-result-invite";

        inviteButton.textContent = "Select";

        inviteButton.setAttribute(
            "aria-label",
            "Select " + developer.username + " for invitation"
        );

        inviteButton.addEventListener("click", function () {

            selectDeveloper(developer);

        });


        // -------------------------------------------------
        // Assemble result
        // -------------------------------------------------

        result.appendChild(identity);

        result.appendChild(inviteButton);

        return result;

    }


    // =====================================================
    // 9. SEARCH REGISTERED DEVELOPERS
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

        // Require at least two characters.
        if (query.length < 2) {
            return;
        }

        searchTimer = setTimeout(async function () {

            const requestController = new AbortController();

            controller = requestController;

            try {

                // Build the Django search URL.
                const url = new URL(
                    searchURL,
                    window.location.origin
                );

                url.searchParams.set("q", query);


                // Request matching developers.
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

                // Ignore outdated responses.
                if (
                    currentVersion !== searchVersion ||
                    searchInput.value.trim() !== query
                ) {
                    return;
                }

                resultsBox.replaceChildren();


                // -------------------------------------------------
                // No matching developers
                // -------------------------------------------------

                if (data.users.length === 0) {

                    showMessage("No developers found.");

                    return;
                }


                // -------------------------------------------------
                // Display matching developers
                // -------------------------------------------------

                data.users.forEach(function (developer) {

                    // Skip invalid results.
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
    // 10. CLOSE RESULTS WHEN CLICKING OUTSIDE
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
    // 11. VALIDATE INVITATION FORM
    // =====================================================

    if (invitationForm) {

        invitationForm.addEventListener("submit", function (event) {

            // A developer must be selected from search results.
            if (!selectedDeveloper) {

                event.preventDefault();

                alert(
                    "Please select a developer from the search results."
                );

                searchInput.focus();

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

            // Prevent duplicate submissions.
            const submitButton = invitationForm.querySelector(
                'button[type="submit"]'
            );

            if (submitButton) {

                submitButton.disabled = true;

                submitButton.textContent = "Sending Invitation...";

            }

            // Django performs the final authorization checks.
        });

    }

});