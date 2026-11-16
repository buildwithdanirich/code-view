/**
 * ColabVerse — Developer Profile Picture
 *
 * Features:
 * 1. Open the file picker using the camera button.
 * 2. Preview the selected profile picture.
 * 3. Validate image type and file size.
 * 4. Keep the image inside the existing Django form.
 *
 * The developer must click "Save changes" to upload
 * the selected picture permanently.
 */

"use strict";

document.addEventListener("DOMContentLoaded", () => {

    // Django's existing avatar upload field.
    const input = document.getElementById("id_avatar");

    // Circular profile picture.
    const preview = document.getElementById("cv-avatar-preview");

    // Username initial shown when no picture exists.
    const fallback = document.getElementById("cv-avatar-fallback");

    // WhatsApp-style camera button.
    const cameraButton = document.getElementById("cv-camera-button");

    // Displays upload instructions and errors.
    const status = document.getElementById("cv-photo-status");

    // Maximum permitted file size: 3 MB.
    const MAX_FILE_SIZE = 3 * 1024 * 1024;

    // Supported image formats.
    const ALLOWED_TYPES = [
        "image/jpeg",
        "image/png",
        "image/webp"
    ];

    // Stop if the required HTML elements are missing.
    if (!input || !preview || !cameraButton) {
        return;
    }

    /**
     * Display a message to the developer.
     */
    function updateStatus(message, isError = false) {

        if (!status) {
            return;
        }

        status.textContent = message;

        status.classList.toggle(
            "cv-photo-error",
            isError
        );
    }

    /**
     * Open the file picker when the camera button is clicked.
     */
    cameraButton.addEventListener("click", () => {

        input.click();

    });

    /**
     * Validate the selected picture.
     */
    function validateImage(file) {

        if (!ALLOWED_TYPES.includes(file.type)) {

            updateStatus(
                "Please select a JPG, PNG, or WebP image.",
                true
            );

            return false;
        }

        if (file.size > MAX_FILE_SIZE) {

            updateStatus(
                "Your picture must not exceed 3 MB.",
                true
            );

            return false;
        }

        return true;
    }

    /**
     * Preview the selected picture.
     */
    input.addEventListener("change", () => {

        const file = input.files && input.files[0];

        // The developer cancelled the file picker.
        if (!file) {
            return;
        }

        // Reject unsupported images.
        if (!validateImage(file)) {

            input.value = "";

            return;
        }

        // Read the selected image.
        const reader = new FileReader();

        reader.onload = () => {

            // Display the newly selected image.
            preview.src = reader.result;

            preview.hidden = false;

            // Hide the username initial.
            if (fallback) {
                fallback.hidden = true;
            }

            updateStatus(
                "Picture selected. Click Save changes to upload it."
            );
        };

        reader.onerror = () => {

            input.value = "";

            updateStatus(
                "Could not preview this picture. Please try another.",
                true
            );
        };

        reader.readAsDataURL(file);

    });

});