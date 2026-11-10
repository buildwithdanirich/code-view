"""Tests for CodeView private-group LiveKit meeting permissions.

LiveKit is mocked: these tests never create real video rooms.
"""

from unittest.mock import AsyncMock, MagicMock, patch

from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.test import TransactionTestCase, override_settings

from community.meeting_service import (
    end_group_meeting,
    get_active_group_meeting,
    join_group_meeting,
    start_group_meeting,
)
from community.models import GroupMeeting, GroupMember, ProjectGroup


@override_settings(
    LIVEKIT_URL="wss://test.livekit.cloud",
    LIVEKIT_API_KEY="test-key",
    LIVEKIT_API_SECRET="test-secret",
    LIVEKIT_MAX_PARTICIPANTS=10,
    LIVEKIT_TOKEN_TTL_SECONDS=600,
)
class GroupMeetingServiceTests(TransactionTestCase):
    """Exercise owner, member, outsider, and meeting-creator roles."""

    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(
            username="meeting_owner", password="TestPassword123!"
        )
        self.creator = User.objects.create_user(
            username="meeting_creator", password="TestPassword123!"
        )
        self.member = User.objects.create_user(
            username="meeting_member", password="TestPassword123!"
        )
        self.outsider = User.objects.create_user(
            username="meeting_outsider", password="TestPassword123!"
        )
        self.group = ProjectGroup.objects.create(
            name="Private meeting test",
            description="Test group",
            owner=self.owner,
            is_private=True,
            join_policy="invite",
        )
        GroupMember.objects.create(group=self.group, user=self.owner, role="admin")
        GroupMember.objects.create(group=self.group, user=self.creator, role="member")
        GroupMember.objects.create(group=self.group, user=self.member, role="member")

    def meeting(self, creator=None):
        """Create an active record without calling LiveKit."""
        return GroupMeeting.objects.create(
            group=self.group,
            started_by=creator or self.creator,
            status="active",
        )

    def livekit_mock(self):
        """Mock the asynchronous LiveKit context manager and room API."""
        client = MagicMock()
        client.room.create_room = AsyncMock()
        client.room.delete_room = AsyncMock()
        context = MagicMock()
        context.__aenter__ = AsyncMock(return_value=client)
        context.__aexit__ = AsyncMock(return_value=False)
        return context, client

    def test_ordinary_member_can_start_meeting(self):
        """The owner does not need to be online to start a call."""
        context, client = self.livekit_mock()
        with patch("community.meeting_service.api.LiveKitAPI", return_value=context):
            meeting = async_to_sync(start_group_meeting)(self.group.pk, self.creator)
        self.assertEqual(meeting.started_by_id, self.creator.pk)
        self.assertEqual(meeting.status, "active")
        request = client.room.create_room.await_args.args[0]
        self.assertEqual(request.max_participants, 10)
        self.assertEqual(request.name, str(meeting.room_name))

    def test_owner_can_start_meeting(self):
        context, _ = self.livekit_mock()
        with patch("community.meeting_service.api.LiveKitAPI", return_value=context):
            meeting = async_to_sync(start_group_meeting)(self.group.pk, self.owner)
        self.assertEqual(meeting.started_by_id, self.owner.pk)

    def test_outsider_cannot_start_meeting(self):
        with self.assertRaises(PermissionDenied):
            async_to_sync(start_group_meeting)(self.group.pk, self.outsider)
        self.assertFalse(GroupMeeting.objects.exists())

    def test_public_group_cannot_start_meeting(self):
        public = ProjectGroup.objects.create(
            name="Public group", description="Public", owner=self.owner,
            is_private=False, join_policy="open",
        )
        with self.assertRaises(PermissionDenied):
            async_to_sync(start_group_meeting)(public.pk, self.owner)

    def test_second_active_meeting_rejected(self):
        self.meeting()
        with self.assertRaises(ValidationError):
            self.meeting(creator=self.member)
        self.assertEqual(GroupMeeting.objects.filter(status="active").count(), 1)

    def test_database_constraint_rejects_duplicate(self):
        """Bypass model validation to test PostgreSQL's constraint directly."""
        self.meeting()
        duplicate = GroupMeeting(
            group=self.group, started_by=self.member, status="active"
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                GroupMeeting.objects.bulk_create([duplicate])

    def test_member_can_join(self):
        meeting = self.meeting()
        result = async_to_sync(join_group_meeting)(self.group.pk, self.member)
        self.assertEqual(result["room_name"], str(meeting.room_name))
        self.assertEqual(result["url"], "wss://test.livekit.cloud")
        self.assertTrue(result["token"])

    def test_outsider_cannot_join(self):
        self.meeting()
        with self.assertRaises(PermissionDenied):
            async_to_sync(join_group_meeting)(self.group.pk, self.outsider)

    def test_removed_member_cannot_get_new_token(self):
        self.meeting()
        GroupMember.objects.filter(group=self.group, user=self.member).delete()
        with self.assertRaises(PermissionDenied):
            async_to_sync(join_group_meeting)(self.group.pk, self.member)

    def test_meeting_creator_can_end(self):
        meeting = self.meeting()
        context, client = self.livekit_mock()
        with patch("community.meeting_service.api.LiveKitAPI", return_value=context):
            self.assertTrue(async_to_sync(end_group_meeting)(self.group.pk, self.creator))
        meeting.refresh_from_db()
        self.assertEqual(meeting.status, "ended")
        self.assertIsNotNone(meeting.ended_at)
        client.room.delete_room.assert_awaited_once()

    def test_group_owner_can_end_member_meeting(self):
        meeting = self.meeting()
        context, _ = self.livekit_mock()
        with patch("community.meeting_service.api.LiveKitAPI", return_value=context):
            self.assertTrue(async_to_sync(end_group_meeting)(self.group.pk, self.owner))
        meeting.refresh_from_db()
        self.assertEqual(meeting.status, "ended")

    def test_other_member_cannot_end_everyones_call(self):
        meeting = self.meeting()
        with self.assertRaises(PermissionDenied):
            async_to_sync(end_group_meeting)(self.group.pk, self.member)
        meeting.refresh_from_db()
        self.assertEqual(meeting.status, "active")

    def test_livekit_create_failure_releases_reservation(self):
        context, client = self.livekit_mock()
        client.room.create_room.side_effect = RuntimeError("LiveKit unavailable")
        with patch("community.meeting_service.api.LiveKitAPI", return_value=context):
            with self.assertRaises(RuntimeError):
                async_to_sync(start_group_meeting)(self.group.pk, self.creator)
        self.assertFalse(GroupMeeting.objects.filter(status="active").exists())

    def test_current_member_can_view_active_meeting(self):
        meeting = self.meeting()
        self.assertEqual(
            get_active_group_meeting(self.group.pk, self.member).pk,
            meeting.pk,
        )
        with self.assertRaises(PermissionDenied):
            get_active_group_meeting(self.group.pk, self.outsider)

    def test_creator_leaving_does_not_invalidate_history(self):
        """Ended records remain valid even after the creator leaves."""
        meeting = self.meeting()
        context, _ = self.livekit_mock()
        with patch("community.meeting_service.api.LiveKitAPI", return_value=context):
            async_to_sync(end_group_meeting)(self.group.pk, self.owner)
        GroupMember.objects.filter(group=self.group, user=self.creator).delete()
        meeting.refresh_from_db()
        self.assertEqual(meeting.status, "ended")
        self.assertEqual(meeting.started_by_id, self.creator.pk)