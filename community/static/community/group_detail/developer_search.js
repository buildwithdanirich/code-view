document.addEventListener("DOMContentLoaded", function () {

    // =====================================================
    // 1. GET HTML ELEMENTS
    // =====================================================

    // Input where the group owner searches for developers.
    const searchInput = document.getElementById("developer-search");

    // Container where matching developers appear.
    const resultsBox = document.getElementById("developer-search-results");

    // Hidden input that stores the selected developer's ID.
    const selectedUserInput = document.getElementById("invite-user-id");

    // Invitation form.
    const invitationForm = document.getElementById("invite-developer-form");

    // Stop if this page does not contain developer search.
    if (!searchInput || !resultsBox) {
        return;
    }

    // Get the Django search endpoint from the HTML.
    const searchURL = searchInput.dataset.searchUrl;

    if (!searchURL) {
        console.error("Developer search URL is missing.");
        return;
    }


    // =====================================================
    // 2. SEARCH SETTINGS
    // =====================================================

    // Timer used to delay searches while the user types.
    let searchTimer = null;

    // Controller used to cancel previous requests.
    let controller = null;

    // Keep track of the developer selected from search results.
    let selectedDeveloper = null;


    // =====================================================
    // 3. SEARCH DEVELOPERS
    // =====================================================

    searchInput.addEventListener("input", function () {

        // Clear the previously selected developer.
        selectedDeveloper = null;

        // Clear the hidden user ID.
        if (selectedUserInput) {
            selectedUserInput.value = "";
        }

        // Stop the previous search timer.
        clearTimeout(searchTimer);

        // Cancel the previous network request.
        if (controller) {
            controller.abort();
        }

        // Get the username being searched.
        const query = searchInput.value.trim();

        // Clear previous search results.
        resultsBox.replaceChildren();

        // Require at least two characters.
        if (query.length < 2) {
            return;
        }

        // Wait 250 milliseconds before searching.
        searchTimer = setTimeout(async function () {

            controller = new AbortController();

            try {

                // Build the search URL safely.
                const url = new URL(
                    searchURL,
                    window.location.origin
                );

                // Add the developer username to the URL.
                url.searchParams.set("q", query);

                // Send the search request to Django.
                const response = await fetch(
                    url.toString(),
                    {
                        method: "GET",
                        credentials: "same-origin",
                        signal: controller.signal
                    }
                );

                // Check whether Django accepted the request.
                if (!response.ok) {
                    throw new Error("Developer search failed.");
                }

                // Convert the JSON response into JavaScript data.
                const data = await response.json();

                // Confirm that Django returned a list.
                if (!Array.isArray(data.users)) {
                    throw new Error("Invalid developer search response.");
                }

                // Ignore results from an outdated search.
                if (searchInput.value.trim() !== query) {
                    return;
                }

                // Clear old suggestions.
                resultsBox.replaceChildren();


                // =====================================================
                // 4. HANDLE EMPTY SEARCH RESULTS
                // =====================================================

                if (data.users.length === 0) {

                    const message = document.createElement("p");

                    message.textContent = "No developers found.";

                    resultsBox.appendChild(message);

                    return;
                }


                // =====================================================
                // 5. DISPLAY MATCHING DEVELOPERS
                // =====================================================

                data.users.forEach(function (developer) {

                    // Create a button for each matching developer.
                    const option = document.createElement("button");

                    option.type = "button";

                    option.className = "developer-search-option";

                    // Display the developer's username safely.
                    option.textContent = developer.username;


                    // =================================================
                    // 6. SELECT A DEVELOPER
                    // =================================================

                    option.addEventListener("click", function () {

                        // Display the selected username.
                        searchInput.value = developer.username;

                        // Remember the selected developer.
                        selectedDeveloper = developer;

                        // Store the developer's ID for the backend.
                        if (selectedUserInput) {
                            selectedUserInput.value = developer.id;
                        }

                        // Hide the search suggestions.
                        resultsBox.replaceChildren();

                    });

                    // Add the developer to the results container.
                    resultsBox.appendChild(option);

                });

            } catch (error) {

                // Ignore cancelled requests.
                if (error.name === "AbortError") {
                    return;
                }

                // Ignore outdated searches.
                if (searchInput.value.trim() !== query) {
                    return;
                }

                console.error("Developer search error:", error);

                resultsBox.textContent =
                    "Unable to search developers.";

            }

        }, 250);

    });


    // =====================================================
    // 7. VALIDATE THE INVITATION FORM
    // =====================================================

    // Only private group owners have this form.
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

            // Confirm that the hidden input contains the selected ID.
            if (
                selectedUserInput &&
                !selectedUserInput.value
            ) {

                event.preventDefault();

                alert("Developer ID is missing.");

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

            // The browser now submits the form to Django.
            // Django must validate the user ID and permissions.
        });

    }

});