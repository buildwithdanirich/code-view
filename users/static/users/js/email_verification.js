/**
 * ColabVerse — Automatic Email Verification Login
 *
 * This script runs on the registration waiting page.
 *
 * 1. Checks whether the developer has verified their email.
 * 2. Waits if verification is incomplete.
 * 3. Completes login using a CSRF-protected POST request.
 * 4. Redirects the original laptop to the dashboard.
 *
 * The server, not JavaScript, decides whether login is allowed.
 */

"use strict";

document.addEventListener("DOMContentLoaded", () => {

    // Find the email-verification waiting page.
    const waitingPage = document.querySelector(
        ".email-verification-waiting"
    );

    // Do nothing on other ColabVerse pages.
    if (!waitingPage) {
        return;
    }

    // Read the backend endpoint from the HTML template.
    const statusUrl = waitingPage.dataset.verificationStatusUrl;

    // Find the element that displays verification progress.
    const statusElement = document.getElementById(
        "verification-status"
    );

    // Check verification every three seconds.
    const POLLING_INTERVAL = 3000;

    let pollingTimer = null;

    // Prevent multiple login requests from running together.
    let loginInProgress = false;

    /**
     * Display a message on the waiting page.
     */
    function updateStatus(message) {

        if (statusElement) {
            statusElement.textContent = message;
        }
    }

    /**
     * Read a cookie by name.
     *
     * Django uses the csrftoken cookie to protect
     * POST requests against cross-site request forgery.
     */
    function getCookie(name) {

        const cookies = document.cookie.split(";");

        for (const cookie of cookies) {

            const trimmedCookie = cookie.trim();

            if (trimmedCookie.startsWith(`${name}=`)) {

                return decodeURIComponent(
                    trimmedCookie.substring(name.length + 1)
                );
            }
        }

        return null;
    }

    /**
     * Stop checking the server.
     */
    function stopPolling() {

        if (pollingTimer !== null) {

            clearInterval(pollingTimer);

            pollingTimer = null;
        }
    }

    /**
     * Complete login on the original registration browser.
     *
     * The server checks:
     * - The original registration session.
     * - Whether the email has been verified.
     * - Whether the temporary authorization is still valid.
     * - Django's CSRF protection.
     */
    async function completeLogin() {

        if (loginInProgress) {
            return;
        }

        loginInProgress = true;

        stopPolling();

        updateStatus(
            "Email verified! Signing you in to ColabVerse..."
        );

        try {

            const csrfToken = getCookie("csrftoken");

            if (!csrfToken) {
                throw new Error("CSRF token unavailable.");
            }

            const response = await fetch(statusUrl, {

                method: "POST",

                credentials: "same-origin",

                headers: {
                    "X-CSRFToken": csrfToken,
                    "Accept": "application/json"
                }
            });

            if (response.status === 403) {

                updateStatus(
                    "Your registration session has expired. " +
                    "Please sign in manually."
                );

                return;
            }

            if (!response.ok) {

                throw new Error(
                    `Login request failed: ${response.status}`
                );
            }

            const data = await response.json();

            // The server must confirm successful authentication.
            if (data.verified && data.redirect_url) {

                updateStatus(
                    "Login successful! Opening your dashboard..."
                );

                // Navigate to the dashboard URL returned by Django.
                window.location.assign(data.redirect_url);

                return;
            }

            throw new Error(
                "The server did not confirm login."
            );

        } catch (error) {

            console.error(
                "ColabVerse automatic login error:",
                error
            );

            updateStatus(
                "Automatic login could not be completed. " +
                "Please wait or sign in manually."
            );

            loginInProgress = false;

            // Retry after a temporary network or server failure.
            startPolling();
        }
    }

    /**
     * Ask Django whether email verification is complete.
     *
     * GET only checks status.
     * It never creates an authenticated session.
     */
    async function checkVerificationStatus() {

        // Avoid overlapping requests.
        if (loginInProgress) {
            return;
        }

        try {

            const response = await fetch(statusUrl, {

                method: "GET",

                credentials: "same-origin",

                headers: {
                    "Accept": "application/json"
                },

                cache: "no-store"
            });

            if (response.status === 403) {

                stopPolling();

                updateStatus(
                    "Your registration session has expired. " +
                    "Please sign in manually."
                );

                return;
            }

            if (!response.ok) {

                throw new Error(
                    `Verification check failed: ${response.status}`
                );
            }

            const data = await response.json();

            // The developer has verified their email.
            if (data.verified) {

                await completeLogin();

                return;
            }

            // Still waiting for verification.
            updateStatus(
                "Waiting for email verification..."
            );

        } catch (error) {

            console.error(
                "ColabVerse verification check error:",
                error
            );

            updateStatus(
                "Connection interrupted. Retrying verification..."
            );
        }
    }

    /**
     * Start checking verification status.
     */
    function startPolling() {

        if (pollingTimer !== null) {
            return;
        }

        pollingTimer = setInterval(
            checkVerificationStatus,
            POLLING_INTERVAL
        );
    }

    // Stop polling when the browser leaves the page.
    window.addEventListener("pagehide", stopPolling);

    // Check immediately instead of waiting three seconds.
    checkVerificationStatus();

    // Continue checking while the page remains open.
    startPolling();

});