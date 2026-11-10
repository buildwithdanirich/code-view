"""
CodeView - Group Permission Tests

These tests verify:
1. Group owner permissions
2. Administrator permissions
3. Ordinary member permissions
4. Private group access
5. Public group access
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

from community.models import ProjectGroup, GroupMember

from community.permissions import (
    is_group_owner,
    is_group_admin,
    is_group_member,
    can_view_group,
    can_manage_group_members,
)


User = get_user_model()


class GroupPermissionTests(TestCase):
    """Test CodeView group access and permissions."""

    def setUp(self):
        """Create developers and groups for testing."""

        # Create the group owner.
        self.owner = User.objects.create_user(
            username="owner",
            password="TestPassword123!",
        )

        # Create an administrator.
        self.admin = User.objects.create_user(
            username="administrator",
            password="TestPassword123!",
        )

        # Create an ordinary member.
        self.member = User.objects.create_user(
            username="developer",
            password="TestPassword123!",
        )

        # Create someone who has not joined the group.
        self.outsider = User.objects.create_user(
            username="outsider",
            password="TestPassword123!",
        )

        # Create a private development group.
        self.private_group = ProjectGroup.objects.create(
            name="Python Developers",
            description="Private Python development group.",
            owner=self.owner,
            is_private=True,
            join_policy="invite",
        )

        # Create a public community.
        self.public_group = ProjectGroup.objects.create(
            name="Go Developers",
            description="Public Go programming community.",
            owner=self.owner,
            is_private=False,
            join_policy="open",
        )

        # Add the administrator to the private group.
        GroupMember.objects.create(
            group=self.private_group,
            user=self.admin,
            role="admin",
        )

        # Add the ordinary developer.
        GroupMember.objects.create(
            group=self.private_group,
            user=self.member,
            role="member",
        )

    def test_owner_is_recognized(self):
        """The group owner must be recognized as the owner."""

        self.assertTrue(
            is_group_owner(self.private_group, self.owner)
        )

        self.assertFalse(
            is_group_owner(self.private_group, self.member)
        )

    def test_owner_has_admin_permissions(self):
        """The owner must have administrator permissions."""

        self.assertTrue(
            is_group_admin(self.private_group, self.owner)
        )

        self.assertTrue(
            can_manage_group_members(
                self.private_group,
                self.owner,
            )
        )

    def test_administrator_cannot_manage_members(self):
        """
        Only the group owner has administrator permissions.

        A developer with role="admin" who is not the owner
        must not receive administrative permissions.
        """

        # The developer has an admin role in the database,
        # but is not the actual group owner.
        self.assertFalse(
            is_group_owner(
                self.private_group,
                self.admin,
            )
        )

        # Only the owner is recognized as a group administrator.
        self.assertFalse(
            is_group_admin(
                self.private_group,
                self.admin,
            )
        )

        # A non-owner cannot invite or remove group members.
        self.assertFalse(
            can_manage_group_members(
                self.private_group,
                self.admin,
            )
        )

    def test_ordinary_member_cannot_manage_members(self):
        """An ordinary member cannot manage other members."""

        self.assertTrue(
            is_group_member(self.private_group, self.member)
        )

        self.assertFalse(
            is_group_admin(self.private_group, self.member)
        )

        self.assertFalse(
            can_manage_group_members(
                self.private_group,
                self.member,
            )
        )

    def test_outsider_cannot_access_private_group(self):
        """An outsider cannot access a private group."""

        self.assertFalse(
            is_group_member(self.private_group, self.outsider)
        )

        self.assertFalse(
            can_view_group(self.private_group, self.outsider)
        )

    def test_members_can_access_private_group(self):
        """Owners, administrators and members can view private groups."""

        for user in (self.owner, self.admin, self.member):
            with self.subTest(username=user.username):
                self.assertTrue(
                    can_view_group(self.private_group, user)
                )

    def test_authenticated_user_can_view_public_group(self):
        """Authenticated developers can view public communities."""

        self.assertTrue(
            can_view_group(self.public_group, self.outsider)
        )

    def test_outsider_cannot_manage_members(self):
        """An outsider cannot manage group members."""

        self.assertFalse(
            can_manage_group_members(
                self.private_group,
                self.outsider,
            )
        )