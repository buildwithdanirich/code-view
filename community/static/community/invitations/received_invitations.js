/**
 * CodeView - Received Group Invitations
 *
 * Features:
 * 1. Open a custom confirmation modal.
 * 2. Confirm accepting or declining an invitation.
 * 3. Close the modal using Cancel, X, backdrop, or Escape.
 * 4. Keep keyboard focus inside the modal.
 * 5. Restore focus when the modal closes.
 * 6. Prevent duplicate form submissions.
 * 7. Display feedback while submitting.
 *
 * Security:
 * Django remains responsible for authentication,
 * CSRF protection, invitation ownership, and capacity.
 */

document.addEventListener("DOMContentLoaded", function () {

    // =====================================================
    // 1. GET HTML ELEMENTS
    // =====================================================

    const invitationForms = document.querySelectorAll(
        "[data-invitation-form]"
    );

    const modal = document.getElementById(
        "invitation-confirm-modal"
    );

    const modalDialog = modal?.querySelector(
        ".invitation-modal-dialog"
    );

    const modalTitle = document.getElementById(
        "invitation-modal-title"
    );

    const modalDescription = document.getElementById(
        "invitation-modal-description"
    );

    const modalIcon = document.getElementById(
        "invitation-modal-icon"
    );

    const confirmButton = document.getElementById(
        "invitation-modal-confirm"
    );

    const cancelButton = document.getElementById(
        "invitation-modal-cancel"
    );

    const closeButtons = modal?.querySelectorAll(
        "[data-modal-close]"
    );


    // =====================================================
    // 2. VERIFY REQUIRED ELEMENTS
    // =====================================================

    // If the modal is missing, preserve normal Django forms.
    if (
        !modal ||
        !modalDialog ||
        !modalTitle ||
        !modalDescription ||
        !modalIcon ||
        !confirmButton ||
        !cancelButton
    ) {
        return;
    }


    // =====================================================
    // 3. MODAL STATE
    // =====================================================

    // Store the form the developer wants to submit.
    let selectedForm = null;

    // Remember the element focused before opening the modal.
    let previousFocusedElement = null;

    // Prevent opening another modal while submitting.
    let isSubmitting = false;


    // =====================================================
    // 4. OPEN CONFIRMATION MODAL
    // =====================================================

    function openModal(form) {

        if (isSubmitting) {
            return;
        }

        // Save the selected form.
        selectedForm = form;

        // Remember the previously focused element.
        previousFocusedElement = document.activeElement;

        // Read information provided by the HTML form.
        const action = form.dataset.invitationAction;

        const groupName = form.dataset.groupName || "this group";

        // Reset modal button state.
        confirmButton.disabled = false;

        confirmButton.classList.remove("is-decline");

        modalIcon.classList.remove("is-decline");


        // -------------------------------------------------
        // ACCEPT INVITATION
        // -------------------------------------------------

        if (action === "accept") {

            modalTitle.textContent = "Join Development Group?";

            modalDescription.textContent =
                `Do you want to accept the invitation to "${groupName}" ` +
                "and become a member of this development group?";

            modalIcon.textContent = "✓";

            confirmButton.textContent = "Yes, Join Group";

        }


        // -------------------------------------------------
        // DECLINE INVITATION
        // -------------------------------------------------

        else if (action === "decline") {

            modalTitle.textContent = "Decline Invitation?";

            modalDescription.textContent =
                `Are you sure you want to decline the invitation ` +
                `to "${groupName}"?`;

            modalIcon.textContent = "✕";

            modalIcon.classList.add("is-decline");

            confirmButton.textContent = "Yes, Decline";

            confirmButton.classList.add("is-decline");

        }

        else {
            selectedForm = null;
            return;
        }


        // Display the modal.
        modal.hidden = false;

        // Prevent scrolling behind the modal.
        document.body.style.overflow = "hidden";

        // Move keyboard focus inside the modal.
        cancelButton.focus();

    }


    // =====================================================
    // 5. CLOSE CONFIRMATION MODAL
    // =====================================================

    function closeModal() {

        // Do not close while submitting to Django.
        if (isSubmitting) {
            return;
        }

        // Hide the modal.
        modal.hidden = true;

        // Restore normal page scrolling.
        document.body.style.overflow = "";

        // Clear the selected form.
        selectedForm = null;

        // Restore focus to the original button.
        if (
            previousFocusedElement &&
            typeof previousFocusedElement.focus === "function"
        ) {
            previousFocusedElement.focus();
        }

        previousFocusedElement = null;

    }


    // =====================================================
    // 6. INTERCEPT INVITATION FORMS
    // =====================================================

    invitationForms.forEach(function (form) {

        form.addEventListener("submit", function (event) {

            // JavaScript controls confirmation.
            event.preventDefault();

            // Block repeated submissions.
            if (
                isSubmitting ||
                form.dataset.submitting === "true"
            ) {
                return;
            }

            // Open CodeView's custom confirmation.
            openModal(form);

        });

    });


    // =====================================================
    // 7. CANCEL OR CLOSE MODAL
    // =====================================================

    closeButtons?.forEach(function (button) {

        button.addEventListener("click", function () {
            closeModal();
        });

    });


    // =====================================================
    // 8. CONFIRM INVITATION ACTION
    // =====================================================

    confirmButton.addEventListener("click", function () {

        if (
            !selectedForm ||
            isSubmitting ||
            selectedForm.dataset.submitting === "true"
        ) {
            return;
        }

        // Save the form before changing modal state.
        const form = selectedForm;

        const action = form.dataset.invitationAction;

        // Mark submission as started.
        isSubmitting = true;

        form.dataset.submitting = "true";

        // Prevent repeated confirmation clicks.
        confirmButton.disabled = true;

        // Display submission feedback.
        confirmButton.textContent =
            action === "accept"
                ? "Joining Group..."
                : "Declining...";

        // Disable the original form button.
        const submitButton = form.querySelector(
            'button[type="submit"]'
        );

        if (submitButton) {

            submitButton.disabled = true;

            submitButton.textContent =
                action === "accept"
                    ? "Joining Group..."
                    : "Declining...";

        }

        // Submit the existing Django POST form.
        // This includes its CSRF token.
        //
        // form.submit() bypasses the submit event,
        // so the confirmation modal will not reopen.
        HTMLFormElement.prototype.submit.call(form);

    });


    // =====================================================
    // 9. KEYBOARD ACCESSIBILITY
    // =====================================================

    modal.addEventListener("keydown", function (event) {

        if (modal.hidden || isSubmitting) {
            return;
        }


        // -------------------------------------------------
        // ESCAPE CLOSES MODAL
        // -------------------------------------------------

        if (event.key === "Escape") {

            event.preventDefault();

            closeModal();

            return;
        }


        // -------------------------------------------------
        // TAB KEY STAYS INSIDE MODAL
        // -------------------------------------------------

        if (event.key !== "Tab") {
            return;
        }

        // Find keyboard-focusable elements.
        const focusableElements = Array.from(
            modalDialog.querySelectorAll(
                'button:not([disabled]), ' +
                'a[href], ' +
                'input:not([disabled]), ' +
                'select:not([disabled]), ' +
                'textarea:not([disabled]), ' +
                '[tabindex]:not([tabindex="-1"])'
            )
        ).filter(function (element) {
            return element.getClientRects().length > 0;
        });

        if (focusableElements.length === 0) {

            event.preventDefault();

            modalDialog.focus();

            return;
        }

        const firstElement = focusableElements[0];

        const lastElement = focusableElements[
            focusableElements.length - 1
        ];


        // Shift + Tab from the first element.
        if (
            event.shiftKey &&
            document.activeElement === firstElement
        ) {

            event.preventDefault();

            lastElement.focus();

        }


        // Tab from the last element.
        else if (
            !event.shiftKey &&
            document.activeElement === lastElement
        ) {

            event.preventDefault();

            firstElement.focus();

        }

    });


    // =====================================================
    // 10. RESTORE BUTTONS IF PAGE IS REVISITED
    // =====================================================

    // Browsers may restore pages from their back-forward cache.
    // Reset the submission state when that happens.

    window.addEventListener("pageshow", function () {

        isSubmitting = false;

        selectedForm = null;

        modal.hidden = true;

        document.body.style.overflow = "";

        confirmButton.disabled = false;

        invitationForms.forEach(function (form) {

            form.dataset.submitting = "false";

            const button = form.querySelector(
                'button[type="submit"]'
            );

            if (!button) {
                return;
            }

            button.disabled = false;

            button.textContent =
                form.dataset.invitationAction === "accept"
                    ? "✓ Accept Invitation"
                    : "✕ Decline";

        });

    });

});