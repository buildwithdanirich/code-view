document.addEventListener("DOMContentLoaded", function () {

    // Get the search input and results container.
    const searchInput = document.getElementById("developer-search");
    const resultsBox = document.getElementById("developer-search-results");

    // Stop if the search elements are missing.
    if (!searchInput || !resultsBox) return;

    // Get the Django search URL from the HTML input.
// Get the Django search endpoint.
const searchURL = searchInput.dataset.searchUrl;

// Stop if Django did not provide a search URL.
if (!searchURL) {
    console.error("Developer search URL is missing.");
    return;
}
    let searchTimer;
    let controller;

    // Run whenever the administrator types.
    searchInput.addEventListener("input", function () {

        clearTimeout(searchTimer);

        // Cancel any previous search request.
        if (controller) controller.abort();

        const query = searchInput.value.trim();

        // Remove previous suggestions.
        resultsBox.replaceChildren();

        // Search only when at least two characters are entered.
        if (query.length < 2) return;

        // Wait briefly so we don't send a request for every keystroke.
        searchTimer = setTimeout(async function () {

            controller = new AbortController();

            try {

                // Send the search text to Django.
                const response = await fetch(
                    `${searchURL}?q=${encodeURIComponent(query)}`,
                    { signal: controller.signal }
                );

                if (!response.ok) {
                    throw new Error("Search request failed");
                }

                // Convert Django's JSON response into JavaScript data.
                const data = await response.json();
                
                // Confirm Django returned a list of developers.
            if (!Array.isArray(data.users)) {
            throw new Error("Invalid developer search response.");
         }

                // Ignore results from an outdated search.
                if (searchInput.value.trim() !== query) return;

                resultsBox.replaceChildren();

                // Display a message when no users match.
                if (data.users.length === 0) {
                    resultsBox.textContent = "No developers found.";
                    return;
                }

                // Display each matching developer.
                data.users.forEach(function (developer) {

                    const option = document.createElement("button");

                    option.type = "button";
                    option.className = "developer-search-option";
                    option.textContent = developer.username;

                    // Fill the input when a developer is selected.
                    option.addEventListener("click", function () {

                        searchInput.value = developer.username;

                        resultsBox.replaceChildren();

                    });

                    resultsBox.appendChild(option);

                });

          } catch (error) {

    // Ignore cancelled searches.
    if (error.name === "AbortError") return;

    // Ignore errors from searches that are no longer current.
    if (searchInput.value.trim() !== query) return;

    // Inform the administrator that the search failed.
    resultsBox.textContent = "Unable to search developers.";

}

        }, 250);

    });

});