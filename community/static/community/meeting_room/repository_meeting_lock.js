/**
 * ColabVerse — Repository Meeting Lock
 *
 * Keeps repository connection controls synchronized
 * with the active group meeting status in Django.
 *
 * Security:
 * - Django enforces repository restrictions.
 * - Repository mutation controls remain disabled until
 *   the server confirms whether a meeting is active.
 * - The warning is displayed only when Django confirms
 *   that repository connections are locked.
 *
 * This file controls the browser interface only.
 */

document.addEventListener("DOMContentLoaded", () => {
    "use strict";

    // =====================================================
    // 1. FIND REPOSITORY ELEMENTS
    // =====================================================

    const repositorySection = document.querySelector(
        ".github-repository-section"
    );

    if (!repositorySection) {
        return;
    }

    const statusUrl = repositorySection.dataset.meetingStatusUrl;

    const lockMessage = document.getElementById(
        "repository-meeting-lock-message"
    );

    const repositoryForms = Array.from(
        repositorySection.querySelectorAll(
            "form[data-repository-mutation]"
        )
    );

    // Django may have rendered the controls disabled
    // because a meeting was active when the page loaded.
    const initiallyLocked = (
        repositorySection.dataset.repositoryLocked === "true"
    );

    // =====================================================
    // 2. REMEMBER ORIGINAL CONTROL STATES
    // =====================================================

    const controls = [];

    repositoryForms.forEach((form) => {
        const formControls = form.querySelectorAll(
            "button, input, select, textarea"
        );

        formControls.forEach((element) => {

            // Never disable hidden inputs such as CSRF tokens.
            if (
                element.tagName === "INPUT" &&
                element.type === "hidden"
            ) {
                return;
            }

            const lockedByDjango = (
                initiallyLocked &&
                element.hasAttribute(
                    "data-repository-mutation-control"
                )
            );

            // Preserve controls disabled for reasons
            // unrelated to the meeting lock.
            const originallyDisabled = (
                element.disabled && !lockedByDjango
            );

            controls.push({
                element,
                originallyDisabled,
            });
        });
    });

    // =====================================================
    // 3. APPLY REPOSITORY LOCK
    // =====================================================

    // Start locked until Django confirms the status.
    let repositoryLocked = true;

    function applyRepositoryLock(locked, confirmed = false) {

        repositoryLocked = locked;

        repositorySection.dataset.repositoryLocked = String(
            locked
        );

        // IMPORTANT:
        // Do not show the orange warning while the
        // initial meeting status request is pending.
        //
        // Show it only after Django confirms that
        // repository connections are locked.
        if (lockMessage) {
            lockMessage.hidden = !(confirmed && locked);
        }

        controls.forEach((control) => {
            const { element, originallyDisabled } = control;

            element.disabled = (
                locked || originallyDisabled
            );

            if (element.tagName === "BUTTON") {
                element.setAttribute(
                    "aria-disabled",
                    String(element.disabled)
                );
            }
        });
    }

    // =====================================================
    // 4. PREVENT SUBMISSION WHILE LOCKED
    // =====================================================

    repositoryForms.forEach((form) => {
        form.addEventListener("submit", (event) => {

            if (repositoryLocked) {

                event.preventDefault();
                event.stopPropagation();

                console.warn(
                    "Repository connections are locked during an active meeting."
                );
            }
        });
    });

    // =====================================================
    // 5. CHECK MEETING STATUS THROUGH DJANGO
    // =====================================================

    let requestInProgress = false;

    async function checkMeetingStatus() {

        if (requestInProgress) {
            return;
        }

        requestInProgress = true;

        try {

            const response = await fetch(statusUrl, {
                method: "GET",
                credentials: "same-origin",
                cache: "no-store",
                headers: {
                    Accept: "application/json",
                },
            });

            if (!response.ok) {
                throw new Error(
                    `Meeting status request failed: ${response.status}`
                );
            }

            const data = await response.json();

            if (
                data.success !== true ||
                typeof data.repository_locked !== "boolean"
            ) {
                throw new Error(
                    "Invalid meeting status response."
                );
            }

            // Django has confirmed the current status.
            // The warning can now be shown or hidden.
            applyRepositoryLock(
                data.repository_locked,
                true
            );

        } catch (error) {

            console.error(
                "ColabVerse repository lock status error:",
                error
            );

            // Security first:
            // Keep mutation controls disabled if the
            // server cannot confirm the meeting status.
            //
            // Do not display a misleading "active meeting"
            // warning when the status is unknown.
            applyRepositoryLock(true, false);

        } finally {
            requestInProgress = false;
        }
    }

    // =====================================================
    // 6. INITIALIZE
    // =====================================================

    // Keep repository mutations disabled while checking.
    // Hide the warning until the status is confirmed.
    applyRepositoryLock(true, false);

    if (!statusUrl) {

        console.error(
            "ColabVerse meeting status URL is missing."
        );

        return;
    }

    // Check immediately when the page loads.
    checkMeetingStatus();

    // =====================================================
    // 7. AUTOMATIC STATUS SYNCHRONIZATION
    // =====================================================

    const STATUS_CHECK_INTERVAL = 3000;

    const intervalId = window.setInterval(
        checkMeetingStatus,
        STATUS_CHECK_INTERVAL
    );

    // Refresh when returning to the browser tab.
    document.addEventListener(
        "visibilitychange",
        () => {

            if (!document.hidden) {
                checkMeetingStatus();
            }
        }
    );

    // Refresh when navigating back to the page.
    window.addEventListener("pageshow", () => {
        checkMeetingStatus();
    });

    // Stop polling when leaving the page.
    window.addEventListener("pagehide", () => {
        window.clearInterval(intervalId);
    });
});