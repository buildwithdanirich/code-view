"""
CodeView — Group Management Tests.

Verify:
1. Only the group owner can remove members.
2. Ordinary members cannot remove other members.
3. Legacy admin roles do not grant owner permissions.
4. The group owner cannot be removed.
5. Members can leave voluntarily.
6. The group owner cannot leave their own group.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from community.models import ProjectGroup, GroupMember


class GroupManagementTests(TestCase):
    """Test CodeView's current group membership rules."""

    def setUp(self):
        User = get_user_model()

        # Create the group owner.
        self.owner = User.objects.create_user(
            username="test_owner",
            password="TestPassword123!",
        )

        # Create a developer with a legacy admin role.
        self.admin = User.objects.create_user(
            username="test_admin",
            password="TestPassword123!",
        )

        # Create an ordinary group member.
        self.member = User.objects.create_user(
            username="test_member",
            password="TestPassword123!",
        )

        # Create a private development group.
        self.group = ProjectGroup.objects.create(
            name="Test Private Group",
            description="A group for testing.",
            owner=self.owner,
            is_private=True,
            join_policy="approval",
        )

        # Store the owner's membership.
        self.owner_membership = GroupMember.objects.create(
            group=self.group,
            user=self.owner,
            role="admin",
        )

        # Keep a legacy admin record to verify that
        # the role does not grant ownership permissions.
        self.admin_membership = GroupMember.objects.create(
            group=self.group,
            user=self.admin,
            role="admin",
        )

        # Store the ordinary member's membership.
        self.member_membership = GroupMember.objects.create(
            group=self.group,
            user=self.member,
            role="member",
        )

    # ========================================================
    # OWNER REMOVAL PERMISSIONS
    # ========================================================

    def test_owner_can_remove_member(self):
        """The group owner can remove an ordinary member."""

        self.client.force_login(self.owner)

        url = reverse(
            "remove_group_member",
            args=[self.group.id, self.member_membership.id],
        )

        response = self.client.post(url)

        self.assertEqual(response.status_code, 302)

        self.assertFalse(
            GroupMember.objects.filter(
                group=self.group,
                user=self.member,
            ).exists()
        )

    def test_owner_can_remove_legacy_admin(self):
        """A legacy admin is still removable by the owner."""

        self.client.force_login(self.owner)

        url = reverse(
            "remove_group_member",
            args=[self.group.id, self.admin_membership.id],
        )

        response = self.client.post(url)

        self.assertEqual(response.status_code, 302)

        self.assertFalse(
            GroupMember.objects.filter(
                group=self.group,
                user=self.admin,
            ).exists()
        )

    def test_admin_cannot_remove_owner(self):
        """A legacy admin cannot remove the group owner."""

        self.client.force_login(self.admin)

        url = reverse(
            "remove_group_member",
            args=[self.group.id, self.owner_membership.id],
        )

        response = self.client.post(url)

        self.assertEqual(response.status_code, 403)

    def test_admin_cannot_remove_another_member(self):
        """A legacy admin cannot remove an ordinary member."""

        self.client.force_login(self.admin)

        url = reverse(
            "remove_group_member",
            args=[self.group.id, self.member_membership.id],
        )

        response = self.client.post(url)

        self.assertEqual(response.status_code, 403)

        # Confirm the member was not removed.
        self.assertTrue(
            GroupMember.objects.filter(
                group=self.group,
                user=self.member,
            ).exists()
        )

    def test_member_cannot_remove_another_member(self):
        """Ordinary members cannot remove other developers."""

        self.client.force_login(self.member)

        url = reverse(
            "remove_group_member",
            args=[self.group.id, self.admin_membership.id],
        )

        response = self.client.post(url)

        self.assertEqual(response.status_code, 403)

        # Confirm the target still belongs to the group.
        self.assertTrue(
            GroupMember.objects.filter(
                group=self.group,
                user=self.admin,
            ).exists()
        )

    def test_owner_cannot_remove_themselves(self):
        """The owner cannot remove their own membership."""

        self.client.force_login(self.owner)

        url = reverse(
            "remove_group_member",
            args=[self.group.id, self.owner_membership.id],
        )

        response = self.client.post(url)

        self.assertEqual(response.status_code, 403)

        self.assertTrue(
            GroupMember.objects.filter(
                group=self.group,
                user=self.owner,
            ).exists()
        )

    # ========================================================
    # LEAVING GROUPS
    # ========================================================

    def test_member_can_leave_group(self):
        """An ordinary member can voluntarily leave."""

        self.client.force_login(self.member)

        url = reverse(
            "leave_group",
            args=[self.group.id],
        )

        response = self.client.post(url)

        self.assertEqual(response.status_code, 302)

        self.assertFalse(
            GroupMember.objects.filter(
                group=self.group,
                user=self.member,
            ).exists()
        )

    def test_owner_cannot_leave_group(self):
        """The owner cannot leave while owning the group."""

        self.client.force_login(self.owner)

        url = reverse(
            "leave_group",
            args=[self.group.id],
        )

        response = self.client.post(url)

        self.assertEqual(response.status_code, 403)

        # Confirm the group still belongs to the owner.
        self.group.refresh_from_db()

        self.assertEqual(
            self.group.owner_id,
            self.owner.id,
        )