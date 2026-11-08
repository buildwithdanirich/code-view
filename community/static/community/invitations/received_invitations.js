/**
 * CodeView - Received Group Invitations
 *
 * Features:
 * 1. Confirm before accepting an invitation.
 * 2. Confirm before declining an invitation.
 * 3. Prevent duplicate form submissions.
 * 4. Display feedback while submitting.
 *
 * Security:
 * Django handles authentication, CSRF protection,
 * invitation ownership, and group capacity.
 */

document.addEventListener("DOMContentLoaded", function () {

    // =====================================================
    // 1. GET INVITATION FORMS
    // =====================================================

    // Find all invitation acceptance forms.
    const acceptForms = document.querySelectorAll(
        ".accept-invitation-form"
    );

    // Find all invitation decline forms.
    const declineForms = document.querySelectorAll(
        ".decline-invitation-form"
    );


    // =====================================================
    // 2. HANDLE ACCEPT INVITATION
    // =====================================================

    acceptForms.forEach(function (form) {

        // Listen for the form submission.
        form.addEventListener("submit", function (event) {

            // Stop repeated submissions.
            if (form.dataset.submitting === "true") {
                event.preventDefault();
                return;
            }

            // Ask the developer to confirm.
            const confirmed = window.confirm(
                "Do you want to accept this invitation and join the group?"
            );

            // Cancel if the developer chooses No.
            if (!confirmed) {
                event.preventDefault();
                return;
            }

            // Mark the form as submitting.
            form.dataset.submitting = "true";

            // Find the submit button.
            const button = form.querySelector(
                'button[type="submit"]'
            );

            if (button) {

                // Prevent additional clicks.
                button.disabled = true;

                // Show submission feedback.
                button.textContent = "Joining Group...";

            }

            // Allow the browser to submit the form to Django.
        });

    });


    // =====================================================
    // 3. HANDLE DECLINE INVITATION
    // =====================================================

    declineForms.forEach(function (form) {

        form.addEventListener("submit", function (event) {

            // Stop repeated submissions.
            if (form.dataset.submitting === "true") {
                event.preventDefault();
                return;
            }

            // Ask for confirmation before declining.
            const confirmed = window.confirm(
                "Are you sure you want to decline this invitation?"
            );

            if (!confirmed) {
                event.preventDefault();
                return;
            }

            // Mark the form as submitting.
            form.dataset.submitting = "true";

            // Find the decline button.
            const button = form.querySelector(
                'button[type="submit"]'
            );

            if (button) {

                // Disable the button.
                button.disabled = true;

                // Display feedback.
                button.textContent = "Declining...";

            }

            // The browser submits the form to Django.
        });

    });

});