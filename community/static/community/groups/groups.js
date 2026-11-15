// ============================================================
// COLABVERSE — MY GROUPS SEARCH
//
// Purpose:
// 1. Search existing development groups.
// 2. Support Enter and Search button.
// 3. Display matching group cards.
// 4. Show a message when no groups match.
// 5. Clear search and restore all groups.
//
// This searches only groups already loaded into the HTML.
// ============================================================


// Wait until the HTML document has loaded.
document.addEventListener("DOMContentLoaded", () => {

    // ========================================================
    // 1. GET HTML ELEMENTS
    // ========================================================

    // Find the search form.
    const searchForm = document.getElementById(
        "group-search-form"
    );

    // Find the search input.
    const searchInput = document.getElementById(
        "group-search"
    );

    // Find the Clear button.
    const clearButton = document.getElementById(
        "group-search-clear"
    );

    // Find the message displayed when no groups match.
    const searchEmpty = document.getElementById(
        "group-search-empty"
    );

    // Find all group cards.
    const groupCards = document.querySelectorAll(
        "[data-group-card]"
    );

    // Stop if the required elements are missing.
    if (
        !searchForm ||
        !searchInput ||
        !clearButton ||
        !searchEmpty
    ) {
        return;
    }


    // ========================================================
    // 2. SEARCH GROUPS
    // ========================================================

    function searchGroups() {

        // Read the search text.
        // trim() removes unnecessary spaces.
        // toLowerCase() ignores capitalization.
        const searchText = searchInput.value
            .trim()
            .toLowerCase();

        // Count matching groups.
        let visibleCount = 0;

        // Check each group card.
        groupCards.forEach((card) => {

            // Get the group name from the HTML.
            const groupName = (
                card.dataset.groupName || ""
            ).toLowerCase();

            // Check whether the group name matches.
            const matches = groupName.includes(searchText);

            // Show matching groups and hide others.
            card.hidden = !matches;

            // Increase the count for matching groups.
            if (matches) {
                visibleCount++;
            }

        });


        // ====================================================
        // 3. SHOW OR HIDE EMPTY SEARCH MESSAGE
        // ====================================================

        // Only show the message when:
        // - A search was entered.
        // - Groups exist on the page.
        // - No groups matched.
        searchEmpty.hidden = !(
            searchText.length > 0 &&
            groupCards.length > 0 &&
            visibleCount === 0
        );


        // ====================================================
        // 4. SHOW OR HIDE CLEAR BUTTON
        // ====================================================

        // Show Clear when the search contains text.
        clearButton.hidden = searchText.length === 0;

    }


    // ========================================================
    // 5. CLEAR SEARCH
    // ========================================================

    function clearSearch() {

        // Empty the search input.
        searchInput.value = "";

        // Show all group cards again.
        groupCards.forEach((card) => {
            card.hidden = false;
        });

        // Hide the no-results message.
        searchEmpty.hidden = true;

        // Hide the Clear button.
        clearButton.hidden = true;

        // Put the cursor back into the search input.
        searchInput.focus();

    }


    // ========================================================
    // 6. SEARCH FORM SUBMISSION
    // ========================================================

    // The submit event runs when:
    // - The Search button is clicked.
    // - Enter is pressed inside the search field.
    searchForm.addEventListener("submit", (event) => {

        // Prevent the browser from reloading the page.
        event.preventDefault();

        // Run the group search.
        searchGroups();

    });


    // ========================================================
    // 7. CLEAR BUTTON
    // ========================================================

    // Restore all groups when Clear is clicked.
    clearButton.addEventListener("click", clearSearch);


    // ========================================================
    // 8. INITIAL STATE
    // ========================================================

    // Hide the Clear button until a search is performed.
    clearButton.hidden = true;

    // Hide the no-results message initially.
    searchEmpty.hidden = true;

});