"""
Security tests for CodeView screen-sharing permissions.

Tests cover:
- Screen-sharing permission detection.
- Restricted and unrestricted LiveKit permissions.
- Recovery when participants disconnect.
- Recovery when someone is actively sharing.
- Recovery when LiveKit revocation fails.
- Successful recovery and database release.
- Advisory-lock acquisition and cleanup.

These tests mock LiveKit and database operations.
Real PostgreSQL advisory locks are tested separately.
"""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch

from django.core.exceptions import ValidationError
from livekit import api

from community import screen_share_recovery as recovery


# ============================================================
# 1. TEST HELPERS
# ============================================================

def make_participant(
    identity,
    sources=None,
    can_publish=True,
    tracks=None,
):
    """
    Create a fake LiveKit participant.

    An empty source list means unrestricted publishing
    when can_publish=True.
    """

    if sources is None:
        sources = [
            api.TrackSource.MICROPHONE,
            api.TrackSource.CAMERA,
        ]

    return SimpleNamespace(
        identity=str(identity),
        permission=SimpleNamespace(
            can_publish=can_publish,
            can_publish_sources=sources,
        ),
        tracks=tracks if tracks is not None else [],
    )


def make_screen_track():
    """Create a fake published screen-sharing track."""

    return SimpleNamespace(
        source=api.TrackSource.SCREEN_SHARE,
    )


def make_snapshot():
    """Return a sample incomplete approval."""

    return {
        "meeting_id": 10,
        "room_name": "codeview-test-room",
        "creator_id": 1,
        "presenter_id": 2,
    }


# ============================================================
# 2. PERMISSION DETECTION TESTS
# ============================================================

class ScreenSharePermissionTests(IsolatedAsyncioTestCase):
    """
    Verify that permission detection follows LiveKit rules.
    """

    def test_camera_only_cannot_share_screen(self):
        """Camera and microphone access must not allow screen sharing."""

        participant = make_participant(
            identity=2,
            sources=[
                api.TrackSource.MICROPHONE,
                api.TrackSource.CAMERA,
            ],
        )

        self.assertFalse(
            recovery._can_publish_screen(participant)
        )

    def test_screen_permission_is_detected(self):
        """Explicit screen-sharing permission must be recognized."""

        participant = make_participant(
            identity=2,
            sources=[
                api.TrackSource.MICROPHONE,
                api.TrackSource.CAMERA,
                api.TrackSource.SCREEN_SHARE,
            ],
        )

        self.assertTrue(
            recovery._can_publish_screen(participant)
        )

    def test_unrestricted_publishing_allows_screen(self):
        """An empty source restriction permits all sources."""

        participant = make_participant(
            identity=2,
            sources=[],
            can_publish=True,
        )

        self.assertTrue(
            recovery._can_publish_screen(participant)
        )

    def test_disabled_publishing_blocks_screen(self):
        """Publishing disabled means screen sharing is disabled."""

        participant = make_participant(
            identity=2,
            sources=[],
            can_publish=False,
        )

        self.assertFalse(
            recovery._can_publish_screen(participant)
        )

    def test_screen_track_is_detected(self):
        """An active screen track must be recognized."""

        participant = make_participant(
            identity=2,
            tracks=[make_screen_track()],
        )

        self.assertTrue(
            recovery._has_screen_track(participant)
        )

    def test_camera_track_is_not_screen_sharing(self):
        """A camera track must not be mistaken for a screen track."""

        participant = make_participant(
            identity=2,
            tracks=[
                SimpleNamespace(
                    source=api.TrackSource.CAMERA,
                ),
            ],
        )

        self.assertFalse(
            recovery._has_screen_track(participant)
        )


# ============================================================
# 3. RECOVERY TESTS
# ============================================================

class ScreenShareRecoveryTests(IsolatedAsyncioTestCase):
    """
    Test interrupted approval recovery.

    Database operations, LiveKit calls, and the advisory
    lock are mocked.

    The actual PostgreSQL locking implementation is tested
    in test_screen_share_lock.py.
    """

    def setUp(self):
        """Prepare fake database, LiveKit, and locking operations."""

        self.snapshot = make_snapshot()

        self.creator = make_participant(
            identity=1,
            sources=[
                api.TrackSource.MICROPHONE,
                api.TrackSource.CAMERA,
            ],
        )

        self.presenter = make_participant(
            identity=2,
            sources=[
                api.TrackSource.MICROPHONE,
                api.TrackSource.CAMERA,
                api.TrackSource.SCREEN_SHARE,
            ],
        )

        # ----------------------------------------------------
        # Fake LiveKit room client.
        # ----------------------------------------------------

        self.room_client = MagicMock()
        self.room_client.update_participant = AsyncMock()

        self.livekit_client = MagicMock()
        self.livekit_client.room = self.room_client

        self.livekit_context = MagicMock()

        self.livekit_context.__aenter__ = AsyncMock(
            return_value=self.livekit_client,
        )

        self.livekit_context.__aexit__ = AsyncMock(
            return_value=False,
        )

        # ----------------------------------------------------
        # Fake database operations.
        # ----------------------------------------------------

        self.release_mock = MagicMock(
            return_value=SimpleNamespace(
                pk=10,
                screen_share_state="idle",
            )
        )

        self.snapshot_mock = MagicMock(
            return_value=self.snapshot,
        )

        def fake_sync_to_async(
            function,
            thread_sensitive=True,
        ):
            """
            Replace database operations with async wrappers.

            This allows the tests to run without accessing
            the real meeting database.
            """

            async def wrapper(*args, **kwargs):

                if function is recovery._get_recovery_snapshot:
                    return self.snapshot_mock(*args, **kwargs)

                if function is recovery._release_recovered_slot:
                    return self.release_mock(*args, **kwargs)

                raise AssertionError(
                    "Unexpected database function."
                )

            return wrapper

        # ----------------------------------------------------
        # Fake PostgreSQL advisory lock.
        # ----------------------------------------------------

        self.lock_acquisitions = []
        self.lock_releases = []

        @asynccontextmanager
        async def fake_screen_share_operation_lock(meeting_id):
            """
            Simulate successful advisory-lock acquisition.

            Record acquisition and release so tests can
            verify that recovery uses the lock correctly.

            The real lock is tested separately.
            """

            self.lock_acquisitions.append(meeting_id)

            try:
                yield

            finally:
                self.lock_releases.append(meeting_id)

        # ----------------------------------------------------
        # Configure patches.
        # ----------------------------------------------------

        self.sync_patch = patch.object(
            recovery,
            "sync_to_async",
            side_effect=fake_sync_to_async,
        )

        self.credentials_patch = patch.object(
            recovery,
            "_credentials",
            return_value=(
                "wss://example.invalid",
                "test-key",
                "test-secret",
            ),
        )

        self.livekit_patch = patch.object(
            recovery.api,
            "LiveKitAPI",
            return_value=self.livekit_context,
        )

        self.list_patch = patch.object(
            recovery,
            "_list_participants",
            new_callable=AsyncMock,
        )

        self.update_patch = patch.object(
            recovery,
            "_update_permission",
            new_callable=AsyncMock,
        )

        self.lock_patch = patch.object(
            recovery,
            "screen_share_operation_lock",
            new=fake_screen_share_operation_lock,
        )

        # ----------------------------------------------------
        # Start patches.
        # ----------------------------------------------------

        self.sync_patch.start()
        self.credentials_patch.start()
        self.livekit_patch.start()
        self.lock_patch.start()

        self.list_mock = self.list_patch.start()
        self.update_mock = self.update_patch.start()

        # ----------------------------------------------------
        # Register automatic cleanup.
        # ----------------------------------------------------

        self.addCleanup(self.sync_patch.stop)
        self.addCleanup(self.credentials_patch.stop)
        self.addCleanup(self.livekit_patch.stop)
        self.addCleanup(self.list_patch.stop)
        self.addCleanup(self.update_patch.stop)
        self.addCleanup(self.lock_patch.stop)

    # ========================================================
    # 4. RECOVERY FAILURE TESTS
    # ========================================================

    async def test_missing_creator_blocks_recovery(self):
        """Recovery must fail if the creator is disconnected."""

        self.list_mock.return_value = {
            "2": self.presenter,
        }

        with self.assertRaises(ValidationError):
            await recovery.recover_screen_share_approval(10)

        self.release_mock.assert_not_called()
        self.update_mock.assert_not_awaited()

    async def test_missing_presenter_blocks_recovery(self):
        """Recovery must fail if the presenter is disconnected."""

        self.list_mock.return_value = {
            "1": self.creator,
        }

        with self.assertRaises(ValidationError):
            await recovery.recover_screen_share_approval(10)

        self.release_mock.assert_not_called()
        self.update_mock.assert_not_awaited()

    async def test_active_screen_track_blocks_recovery(self):
        """Recovery must not proceed during active screen sharing."""

        sharing_creator = make_participant(
            identity=1,
            tracks=[make_screen_track()],
        )

        self.list_mock.return_value = {
            "1": sharing_creator,
            "2": self.presenter,
        }

        with self.assertRaises(ValidationError):
            await recovery.recover_screen_share_approval(10)

        self.release_mock.assert_not_called()
        self.update_mock.assert_not_awaited()

    async def test_livekit_failure_keeps_slot_reserved(self):
        """
        A failed LiveKit update must not release the
        database reservation.
        """

        self.list_mock.return_value = {
            "1": self.creator,
            "2": self.presenter,
        }

        self.update_mock.side_effect = RuntimeError(
            "LiveKit connection failed."
        )

        with self.assertRaises(RuntimeError):
            await recovery.recover_screen_share_approval(10)

        self.release_mock.assert_not_called()

    async def test_failed_verification_blocks_release(self):
        """
        If LiveKit still reports presenter screen permission,
        recovery must not release the reservation.
        """

        self.list_mock.return_value = {
            "1": self.creator,
            "2": self.presenter,
        }

        with self.assertRaises(ValidationError):
            await recovery.recover_screen_share_approval(10)

        self.release_mock.assert_not_called()

    # ========================================================
    # 5. SUCCESSFUL RECOVERY TEST
    # ========================================================

    async def test_successful_recovery_releases_slot(self):
        """
        Recovery succeeds only after LiveKit confirms:

        - Creator has screen permission.
        - Presenter has no screen permission.
        - Nobody is publishing a screen track.
        """

        initial_participants = {
            "1": self.creator,
            "2": self.presenter,
        }

        revoked_presenter = make_participant(
            identity=2,
        )

        after_revocation = {
            "1": self.creator,
            "2": revoked_presenter,
        }

        restored_creator = make_participant(
            identity=1,
            sources=[
                api.TrackSource.MICROPHONE,
                api.TrackSource.CAMERA,
                api.TrackSource.SCREEN_SHARE,
                api.TrackSource.SCREEN_SHARE_AUDIO,
            ],
        )

        final_participants = {
            "1": restored_creator,
            "2": revoked_presenter,
        }

        self.list_mock.side_effect = [
            initial_participants,
            after_revocation,
            final_participants,
        ]

        result = await recovery.recover_screen_share_approval(
            10
        )

        self.assertTrue(result["success"])

        self.assertEqual(
            result["screen_share_state"],
            "idle",
        )

        self.assertEqual(
            self.update_mock.await_count,
            2,
        )

        self.release_mock.assert_called_once_with(
            self.snapshot
        )

    # ========================================================
    # 6. ADVISORY-LOCK INTEGRATION TESTS
    # ========================================================

    async def test_recovery_acquires_correct_meeting_lock(self):
        """
        Recovery must acquire the advisory lock belonging
        to the meeting being recovered.
        """

        self.list_mock.return_value = {
            "2": self.presenter,
        }

        with self.assertRaises(ValidationError):
            await recovery.recover_screen_share_approval(10)

        self.assertEqual(
            self.lock_acquisitions,
            [10],
        )

        self.assertEqual(
            self.lock_releases,
            [10],
        )

    async def test_recovery_releases_lock_after_failure(self):
        """
        Even when LiveKit fails, recovery must exit
        its advisory-lock context.

        The database reservation must remain blocked.
        """

        self.list_mock.return_value = {
            "1": self.creator,
            "2": self.presenter,
        }

        self.update_mock.side_effect = RuntimeError(
            "Simulated LiveKit failure."
        )

        with self.assertRaises(RuntimeError):
            await recovery.recover_screen_share_approval(10)

        self.assertEqual(
            self.lock_acquisitions,
            [10],
        )

        self.assertEqual(
            self.lock_releases,
            [10],
        )

        self.release_mock.assert_not_called()