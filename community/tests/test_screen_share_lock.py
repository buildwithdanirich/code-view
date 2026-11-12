"""
Tests for CodeView PostgreSQL screen-sharing advisory locks.

These tests verify:
- A meeting lock can be acquired.
- A second connection cannot acquire the same meeting lock.
- Different meetings can operate independently.
- Locks are released after successful operations.
- Locks are released after exceptions.
- Invalid meeting IDs are rejected.
"""

import asyncio
import unittest

from django.core.exceptions import ValidationError
from django.test import TransactionTestCase

from asgiref.sync import async_to_sync

from community.screen_share_lock import (
    screen_share_operation_lock,
)


class ScreenShareLockTests(TransactionTestCase):
    """
    Integration tests using the configured PostgreSQL database.

    TransactionTestCase is used because these tests need
    real database connections and advisory locks.
    """

    def test_lock_can_be_acquired(self):
        """A valid meeting can acquire its operation lock."""

        async def run_test():
            async with screen_share_operation_lock(1001):
                self.assertTrue(True)

        async_to_sync(run_test)()

    def test_same_meeting_cannot_acquire_two_locks(self):
        """
        Two separate connections must not acquire
        the same meeting's advisory lock simultaneously.
        """

        async def run_test():

            async with screen_share_operation_lock(1002):

                with self.assertRaises(ValidationError):

                    async with screen_share_operation_lock(1002):
                        self.fail(
                            "The second operation acquired the lock."
                        )

        async_to_sync(run_test)()

    def test_different_meetings_can_acquire_locks(self):
        """
        Operations on different meetings should
        not block one another.
        """

        async def run_test():

            async with screen_share_operation_lock(1003):

                async with screen_share_operation_lock(1004):
                    self.assertTrue(True)

        async_to_sync(run_test)()

    def test_lock_released_after_success(self):
        """
        A lock must be available again after
        the first operation completes.
        """

        async def run_test():

            async with screen_share_operation_lock(1005):
                pass

            async with screen_share_operation_lock(1005):
                self.assertTrue(True)

        async_to_sync(run_test)()

    def test_lock_released_after_exception(self):
        """
        Exceptions must not leave the meeting locked.
        """

        async def run_test():

            with self.assertRaises(RuntimeError):

                async with screen_share_operation_lock(1006):
                    raise RuntimeError(
                        "Simulated LiveKit failure."
                    )

            # The previous lock should now be released.
            async with screen_share_operation_lock(1006):
                self.assertTrue(True)

        async_to_sync(run_test)()

    def test_invalid_meeting_id_rejected(self):
        """Invalid meeting IDs must be rejected."""

        async def run_test():

            invalid_ids = [
                0,
                -1,
                None,
                "invalid",
                2147483648,
            ]

            for meeting_id in invalid_ids:

                with self.subTest(meeting_id=meeting_id):

                    with self.assertRaises(ValidationError):

                        async with screen_share_operation_lock(
                            meeting_id
                        ):
                            pass

        async_to_sync(run_test)()

    def test_lock_blocks_concurrent_operation(self):
        """
        Simulate two operations trying to modify
        the same meeting simultaneously.
        """

        async def run_test():

            first_operation_started = asyncio.Event()
            release_first_operation = asyncio.Event()

            async def first_operation():

                async with screen_share_operation_lock(1007):

                    first_operation_started.set()

                    await release_first_operation.wait()

            async def second_operation():

                await first_operation_started.wait()

                with self.assertRaises(ValidationError):

                    async with screen_share_operation_lock(1007):
                        self.fail(
                            "Concurrent operation was not blocked."
                        )

            first_task = asyncio.create_task(
                first_operation()
            )

            try:

                await asyncio.wait_for(
                    second_operation(),
                    timeout=5,
                )

            finally:

                release_first_operation.set()

                await asyncio.wait_for(
                    first_task,
                    timeout=5,
                )

        async_to_sync(run_test)()


if __name__ == "__main__":
    unittest.main()