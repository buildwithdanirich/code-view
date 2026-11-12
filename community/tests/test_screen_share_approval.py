"""
Tests for CodeView screen-sharing approval security.

These tests verify:
- Only the meeting creator can approve requests.
- The creator cannot approve themselves.
- Only one screen-sharing reservation is allowed.
- Rejected and cancelled requests cannot be approved.
- A valid approval can be finalized.
- Invalid finalization cannot release a reserved slot.
- Duplicate finalization is rejected.

These are PostgreSQL database tests.
LiveKit permission changes are tested separately.
"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import (
    PermissionDenied,
    ValidationError,
)
from django.test import TestCase

from community.models import (
    GroupMeeting,
    GroupMember,
    MeetingScreenShareRequest,
    ProjectGroup,
)

from community.screen_share_approval import (
    finalize_screen_share_approval,
    reserve_screen_share_approval,
)


User = get_user_model()


class ScreenShareApprovalTests(TestCase):
    """
    Test screen-sharing reservation and finalization.
    """

    def setUp(self):
        """
        Create real database records for the tests.
        """

        # ----------------------------------------------------
        # 1. Create developers.
        # ----------------------------------------------------

        self.creator = User.objects.create_user(
            username="approval_creator",
            password="TestPassword123!",
        )

        self.presenter = User.objects.create_user(
            username="approval_presenter",
            password="TestPassword123!",
        )

        self.other_presenter = User.objects.create_user(
            username="approval_other_presenter",
            password="TestPassword123!",
        )

        # ----------------------------------------------------
        # 2. Create a private development group.
        # ----------------------------------------------------

        self.group = ProjectGroup.objects.create(
            name="Screen Sharing Test Group",
            description="Private group for approval tests.",
            owner=self.creator,
            is_private=True,
            join_policy="approval",
        )

        # ----------------------------------------------------
        # 3. Add developers as group members.
        # ----------------------------------------------------

        GroupMember.objects.create(
            group=self.group,
            user=self.presenter,
            role="member",
        )

        GroupMember.objects.create(
            group=self.group,
            user=self.other_presenter,
            role="member",
        )

        # ----------------------------------------------------
        # 4. Create an active meeting.
        # ----------------------------------------------------

        self.meeting = GroupMeeting.objects.create(
            group=self.group,
            started_by=self.creator,
            status="active",
            screen_share_state="idle",
        )

        # ----------------------------------------------------
        # 5. Mock only the meeting lookup.
        #
        # We still use real PostgreSQL records for all
        # reservation and finalization operations.
        # ----------------------------------------------------

        self.meeting_lookup = patch(
            "community.screen_share_approval."
            "_active_meeting_for_member",
            return_value=self.meeting,
        )

        self.meeting_lookup.start()

        self.addCleanup(
            self.meeting_lookup.stop
        )

    # ========================================================
    # HELPER: CREATE SCREEN-SHARING REQUEST
    # ========================================================

    def _create_request(
        self,
        requested_by=None,
        status="pending",
    ):
        """
        Create a real screen-sharing request.
        """

        return MeetingScreenShareRequest.objects.create(
            meeting=self.meeting,
            requested_by=requested_by or self.presenter,
            status=status,
        )

    # ========================================================
    # 1. CREATOR CAN RESERVE A REQUEST
    # ========================================================

    def test_creator_can_reserve_pending_request(self):
        """
        The meeting creator can reserve a free slot.
        """

        screen_request = self._create_request()

        reservation = reserve_screen_share_approval(
            self.group.pk,
            self.creator.pk,
            screen_request.pk,
        )

        self.assertEqual(
            reservation["meeting_id"],
            self.meeting.pk,
        )

        self.assertEqual(
            reservation["presenter_id"],
            self.presenter.pk,
        )

        self.assertEqual(
            reservation["state"],
            "granting",
        )

        self.meeting.refresh_from_db()

        self.assertEqual(
            self.meeting.screen_share_state,
            "granting",
        )

        self.assertEqual(
            self.meeting.active_screen_sharer_id,
            self.presenter.pk,
        )

    # ========================================================
    # 2. ORDINARY MEMBER CANNOT APPROVE
    # ========================================================

    def test_non_creator_cannot_approve(self):
        """
        Only the meeting creator can approve requests.
        """

        screen_request = self._create_request()

        with self.assertRaises(PermissionDenied):

            reserve_screen_share_approval(
                self.group.pk,
                self.presenter.pk,
                screen_request.pk,
            )

        self.meeting.refresh_from_db()

        self.assertEqual(
            self.meeting.screen_share_state,
            "idle",
        )

    # ========================================================
    # 3. CREATOR CANNOT APPROVE THEMSELVES
    # ========================================================

    def test_creator_cannot_approve_self(self):
        """
        Creator self-approval must be rejected.
        """

        screen_request = self._create_request(
            requested_by=self.creator,
        )

        with self.assertRaises(ValidationError):

            reserve_screen_share_approval(
                self.group.pk,
                self.creator.pk,
                screen_request.pk,
            )

        self.meeting.refresh_from_db()

        self.assertIsNone(
            self.meeting.active_screen_sharer_id
        )

    # ========================================================
    # 4. SECOND RESERVATION MUST BE BLOCKED
    # ========================================================

    def test_second_reservation_is_blocked(self):
        """
        Only one developer can reserve the screen slot.
        """

        first_request = self._create_request()

        second_request = self._create_request(
            requested_by=self.other_presenter,
        )

        reserve_screen_share_approval(
            self.group.pk,
            self.creator.pk,
            first_request.pk,
        )

        with self.assertRaises(ValidationError):

            reserve_screen_share_approval(
                self.group.pk,
                self.creator.pk,
                second_request.pk,
            )

        self.meeting.refresh_from_db()

        self.assertEqual(
            self.meeting.active_screen_sharer_id,
            self.presenter.pk,
        )

        self.assertEqual(
            self.meeting.screen_share_state,
            "granting",
        )

    # ========================================================
    # 5. REJECTED REQUEST CANNOT BE APPROVED
    # ========================================================

    def test_rejected_request_cannot_be_approved(self):
        """
        Rejected requests cannot reserve screen sharing.
        """

        screen_request = self._create_request(
            status="rejected",
        )

        with self.assertRaises(ValidationError):

            reserve_screen_share_approval(
                self.group.pk,
                self.creator.pk,
                screen_request.pk,
            )

        self.meeting.refresh_from_db()

        self.assertEqual(
            self.meeting.screen_share_state,
            "idle",
        )

    # ========================================================
    # 6. CANCELLED REQUEST CANNOT BE APPROVED
    # ========================================================

    def test_cancelled_request_cannot_be_approved(self):
        """
        Cancelled requests cannot reserve screen sharing.
        """

        screen_request = self._create_request(
            status="cancelled",
        )

        with self.assertRaises(ValidationError):

            reserve_screen_share_approval(
                self.group.pk,
                self.creator.pk,
                screen_request.pk,
            )

        self.meeting.refresh_from_db()

        self.assertEqual(
            self.meeting.screen_share_state,
            "idle",
        )

    # ========================================================
    # 7. VALID APPROVAL CAN BE FINALIZED
    # ========================================================

    def test_valid_approval_can_be_finalized(self):
        """
        A reserved approval can transition to ready.

        LiveKit verification is performed by the calling
        coordinator, not by this database function.
        """

        screen_request = self._create_request()

        reserve_screen_share_approval(
            self.group.pk,
            self.creator.pk,
            screen_request.pk,
        )

        result = finalize_screen_share_approval(
            self.meeting.pk,
            screen_request.pk,
            self.creator.pk,
            self.presenter.pk,
        )

        self.assertEqual(
            result.status,
            "approved",
        )

        self.assertEqual(
            result.reviewed_by_id,
            self.creator.pk,
        )

        self.assertIsNotNone(
            result.reviewed_at
        )

        self.meeting.refresh_from_db()

        self.assertEqual(
            self.meeting.screen_share_state,
            "ready",
        )

        self.assertEqual(
            self.meeting.active_screen_sharer_id,
            self.presenter.pk,
        )

    # ========================================================
    # 8. WRONG PRESENTER CANNOT FINALIZE
    # ========================================================

    def test_wrong_presenter_cannot_finalize(self):
        """
        Finalization must reject a different presenter.
        """

        screen_request = self._create_request()

        reserve_screen_share_approval(
            self.group.pk,
            self.creator.pk,
            screen_request.pk,
        )

        with self.assertRaises(ValidationError):

            finalize_screen_share_approval(
                self.meeting.pk,
                screen_request.pk,
                self.creator.pk,
                self.other_presenter.pk,
            )

        self.meeting.refresh_from_db()

        self.assertEqual(
            self.meeting.screen_share_state,
            "granting",
        )

    # ========================================================
    # 9. SAME REQUEST CANNOT BE FINALIZED TWICE
    # ========================================================

    def test_same_request_cannot_be_finalized_twice(self):
        """
        Duplicate finalization must be rejected.
        """

        screen_request = self._create_request()

        reserve_screen_share_approval(
            self.group.pk,
            self.creator.pk,
            screen_request.pk,
        )

        finalize_screen_share_approval(
            self.meeting.pk,
            screen_request.pk,
            self.creator.pk,
            self.presenter.pk,
        )

        with self.assertRaises(ValidationError):

            finalize_screen_share_approval(
                self.meeting.pk,
                screen_request.pk,
                self.creator.pk,
                self.presenter.pk,
            )

        screen_request.refresh_from_db()

        self.assertEqual(
            screen_request.status,
            "approved",
        )

    # ========================================================
    # 10. FAILED FINALIZATION KEEPS RESERVATION
    # ========================================================

    def test_failed_finalization_keeps_reservation(self):
        """
        Invalid finalization must not release the slot.
        """

        screen_request = self._create_request()

        reserve_screen_share_approval(
            self.group.pk,
            self.creator.pk,
            screen_request.pk,
        )

        with self.assertRaises(ValidationError):

            finalize_screen_share_approval(
                self.meeting.pk,
                screen_request.pk,
                self.creator.pk,
                self.other_presenter.pk,
            )

        self.meeting.refresh_from_db()

        screen_request.refresh_from_db()

        self.assertEqual(
            self.meeting.screen_share_state,
            "granting",
        )

        self.assertEqual(
            self.meeting.active_screen_sharer_id,
            self.presenter.pk,
        )

        self.assertEqual(
            screen_request.status,
            "pending",
        )