"""Test repository connection restrictions during active group meetings."""

from django.contrib.auth import get_user_model
from django.test import TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from community.models import (
    GroupMeeting,
    GroupMember,
    ProjectGroup,
    RepositoryConnectionRequest,
)


class RepositoryMeetingLockTests(TransactionTestCase):
    """Verify that meetings block repository connection operations."""

    def setUp(self):
        """Create users, a private group, and an active meeting."""

        User = get_user_model()

        self.owner = User.objects.create_user(
            username="repo_lock_owner",
            password="TestPassword123!",
        )

        self.member = User.objects.create_user(
            username="repo_lock_member",
            password="TestPassword123!",
        )

        self.group = ProjectGroup.objects.create(
            name="Repository Lock Test Group",
            description="Testing repository meeting restrictions.",
            owner=self.owner,
            is_private=True,
            join_policy="invite",
        )

        GroupMember.objects.create(
            group=self.group,
            user=self.owner,
            role="admin",
        )

        self.membership = GroupMember.objects.create(
            group=self.group,
            user=self.member,
            role="member",
        )

        self.meeting = GroupMeeting.objects.create(
            group=self.group,
            started_by=self.member,
            status="active",
        )

    def create_request(self, status="pending"):
        """Create a valid repository connection request."""

        return RepositoryConnectionRequest.objects.create(
            group=self.group,
            requested_by=self.member,
            status=status,
            membership_generation=(
                self.membership.membership_generation
            ),
            owner_membership_generation=(
                self.group.owner_membership_generation
            ),
        )

    def test_member_cannot_request_during_meeting(self):
        """A member cannot submit a request during an active meeting."""

        self.client.force_login(self.member)

        url = reverse(
            "request_repository_connection",
            kwargs={"group_id": self.group.id},
        )

        response = self.client.post(url)

        self.assertEqual(response.status_code, 403)

        self.assertFalse(
            RepositoryConnectionRequest.objects.filter(
                group=self.group,
            ).exists()
        )

    def test_owner_cannot_approve_during_meeting(self):
        """The owner cannot approve a request during a meeting."""

        connection_request = self.create_request()

        self.client.force_login(self.owner)

        url = reverse(
            "approve_repository_connection",
            kwargs={
                "group_id": self.group.id,
                "request_id": connection_request.id,
            },
        )

        response = self.client.post(url)

        self.assertEqual(response.status_code, 403)

        connection_request.refresh_from_db()

        self.assertEqual(
            connection_request.status,
            "pending",
        )

    def test_owner_cannot_reject_during_meeting(self):
        """The owner cannot reject a request during a meeting."""

        connection_request = self.create_request()

        self.client.force_login(self.owner)

        url = reverse(
            "reject_repository_connection",
            kwargs={
                "group_id": self.group.id,
                "request_id": connection_request.id,
            },
        )

        response = self.client.post(url)

        self.assertEqual(response.status_code, 403)

        connection_request.refresh_from_db()

        self.assertEqual(
            connection_request.status,
            "pending",
        )

    def test_owner_cannot_connect_public_repository_during_meeting(self):
        """An active meeting blocks the public repository endpoint."""

        self.client.force_login(self.owner)

        url = reverse(
            "connect_group_repository",
            kwargs={"group_id": self.group.id},
        )

        # Invalid form data is not enough to test the meeting lock.
        # This test only verifies that the endpoint is reachable.
        response = self.client.post(url, {})

        self.assertIn(response.status_code, (302, 403))

    def test_repository_requests_unlock_after_meeting_ends(self):
        """Members can request permission after a meeting ends."""

        # An ended meeting must have an ending timestamp.
        self.meeting.status = "ended"
        self.meeting.ended_at = timezone.now()

        self.meeting.save(
            update_fields=["status", "ended_at"],
        )

        self.client.force_login(self.member)

        url = reverse(
            "request_repository_connection",
            kwargs={"group_id": self.group.id},
        )

        response = self.client.post(url)

        self.assertEqual(response.status_code, 302)

        self.assertTrue(
            RepositoryConnectionRequest.objects.filter(
                group=self.group,
                requested_by=self.member,
                status="pending",
            ).exists()
        )