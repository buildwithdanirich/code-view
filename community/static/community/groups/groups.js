// ============================================================
// CODEVIEW — GROUPS PAGE JAVASCRIPT
// ============================================================

// Wait until the HTML page has finished loading.
document.addEventListener("DOMContentLoaded", () => {

    // Find the group search input.
    const searchInput = document.getElementById("group-search");

    // Find all existing group cards.
    const groupCards = document.querySelectorAll(
        "[data-group-card]"
    );

    // Find the message displayed when no groups match.
    const searchEmpty = document.getElementById(
        "group-search-empty"
    );

    // Find the group selection dropdown.
    const groupSelect = document.getElementById("group-select");

    // Find the button used to open a selected group.
    const openGroupButton = document.getElementById(
        "open-selected-group"
    );

    // Stop if the required elements are missing.
    if (
        !searchInput ||
        !searchEmpty ||
        !groupSelect ||
        !openGroupButton
    ) {
        return;
    }


    // ========================================================
    // FUNCTION 1 — SEARCH EXISTING GROUPS
    // ========================================================

    function filterGroups() {

        // Read the search text and ignore capitalization.
        const searchText = searchInput.value
            .trim()
            .toLocaleLowerCase();

        let visibleCount = 0;

        // Check each existing group.
        groupCards.forEach((card) => {

            const groupName = (card.dataset.groupName || "")
            .toLowerCase();

            // Check whether the group name contains the search.
            const matches = groupName.includes(searchText);

            // Show matching groups and hide others.
            card.hidden = !matches;

            if (matches) {
                visibleCount++;
            }

        });

        // Display a message if no groups match.
        searchEmpty.hidden =
            visibleCount > 0 || groupCards.length === 0;

        // Filter the group selection dropdown too.
        Array.from(groupSelect.options).forEach((option) => {

            // Keep the default placeholder option.
            if (!option.value) {
                return;
            }

            const groupName = option.dataset.groupName
                .toLocaleLowerCase();

            option.hidden = !groupName.includes(searchText);

        });

        // Clear the selected group if it no longer matches.
        const selectedOption = groupSelect.selectedOptions[0];

        if (selectedOption && selectedOption.hidden) {
            groupSelect.value = "";
        }

        // Update the Open Group button.
        openGroupButton.disabled = !groupSelect.value;
    }


    // ========================================================
    // FUNCTION 2 — OPEN SELECTED GROUP
    // ========================================================

    function openSelectedGroup() {

        // Get the selected group's existing Django URL.
        const selectedGroupUrl = groupSelect.value;

        // Only navigate when a group has been selected.
        if (selectedGroupUrl) {
            window.location.assign(selectedGroupUrl);
        }
    }


    // ========================================================
    // EVENT LISTENERS
    // ========================================================

    // Filter groups whenever the developer types.
    searchInput.addEventListener("input", filterGroups);

    // Enable or disable the button when selection changes.
    groupSelect.addEventListener("change", () => {

        openGroupButton.disabled = !groupSelect.value;

    });

    // Open the selected group when the button is clicked.
    openGroupButton.addEventListener(
        "click",
        openSelectedGroup
    );

});