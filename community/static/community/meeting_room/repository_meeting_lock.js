/**
 * CodeView - Repository Meeting Lock
 *
 * Keeps repository connection controls synchronized
 * with the active group meeting status in Django.
 *
 * Security:
 * Django enforces the actual repository restrictions.
 * This file only manages the browser interface.
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

    // Determine whether Django initially rendered
    // the repository as locked.
    const initiallyLocked = Boolean(
        lockMessage && !lockMessage.hidden
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

            // Hidden inputs include Django's CSRF token.
            // They do not need to be disabled.
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

            // A button disabled only because of the
            // initial meeting lock should become available
            // again when Django confirms the meeting ended.
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

    let repositoryLocked = true;

    function applyRepositoryLock(locked) {
        repositoryLocked = locked;

        repositorySection.dataset.repositoryLocked = String(
            locked
        );

        if (lockMessage) {
            lockMessage.hidden = !locked;
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

            // Only Django's confirmed status can
            // unlock repository connection controls.
            applyRepositoryLock(
                data.repository_locked
            );

        } catch (error) {
            console.error(
                "CodeView repository lock status error:",
                error
            );

            // If the server cannot confirm the status,
            // keep repository mutation controls disabled.
            applyRepositoryLock(true);

        } finally {
            requestInProgress = false;
        }
    }

    // =====================================================
    // 6. INITIALIZE
    // =====================================================

    // Prevent mutations until Django confirms
    // whether a meeting is currently active.
    applyRepositoryLock(true);

    if (!statusUrl) {
        console.error(
            "CodeView meeting status URL is missing."
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

    // Refresh immediately when the developer
    // returns to the browser tab.
    document.addEventListener(
        "visibilitychange",
        () => {
            if (!document.hidden) {
                checkMeetingStatus();
            }
        }
    );

    // Refresh when navigating back to this page.
    window.addEventListener("pageshow", () => {
        checkMeetingStatus();
    });

    // Stop polling when the page is unloaded.
    window.addEventListener("pagehide", () => {
        window.clearInterval(intervalId);
    });
});