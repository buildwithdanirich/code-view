"""
ColabVerse - Private Development Group Permission Tests

These tests verify:

1. Group ownership permissions.
2. Group administrator permissions.
3. Accepted member permissions.
4. Private group access.
5. Public group access is rejected.
6. Pending invitations do not grant membership.
7. Only group owners can manage invitations.
8. Development features require membership.
9. Anonymous users cannot access groups.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import TestCase

from community.models import (
    ProjectGroup,
    GroupMember,
)

from community.permissions import (
    is_group_owner,
    is_group_admin,
    is_group_member,
    can_view_group,
    can_manage_group_members,
    can_invite_group_members,
    can_use_development_features,
)


User = get_user_model()


class GroupPermissionTests(TestCase):
    """Test ColabVerse private group access and permissions."""

    def setUp(self):
        """Create developers and a private development group."""

        # Create the group owner.
        self.owner = User.objects.create_user(
            username="owner",
            password="TestPassword123!",
        )

        # Create a legacy administrator.
        self.admin = User.objects.create_user(
            username="administrator",
            password="TestPassword123!",
        )

        # Create an ordinary group member.
        self.member = User.objects.create_user(
            username="developer",
            password="TestPassword123!",
        )

        # Create a developer who is not a group member.
        self.outsider = User.objects.create_user(
            username="outsider",
            password="TestPassword123!",
        )

        # Create a developer with a pending invitation.
        self.invited_developer = User.objects.create_user(
            username="invited_developer",
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

        # Add the legacy administrator as an accepted member.
        GroupMember.objects.create(
            group=self.private_group,
            user=self.admin,
            role="admin",
        )

        # Add the ordinary developer as an accepted member.
        GroupMember.objects.create(
            group=self.private_group,
            user=self.member,
            role="member",
        )

    # ========================================================
    # 1. GROUP OWNERSHIP
    # ========================================================

    def test_owner_is_recognized(self):
        """The group owner must be recognized as the owner."""

        self.assertTrue(
            is_group_owner(
                self.private_group,
                self.owner,
            )
        )

        self.assertFalse(
            is_group_owner(
                self.private_group,
                self.member,
            )
        )

    def test_owner_has_admin_permissions(self):
        """Only the owner has administrative permissions."""

        self.assertTrue(
            is_group_admin(
                self.private_group,
                self.owner,
            )
        )

        self.assertTrue(
            can_manage_group_members(
                self.private_group,
                self.owner,
            )
        )

        self.assertTrue(
            can_invite_group_members(
                self.private_group,
                self.owner,
            )
        )

    # ========================================================
    # 2. LEGACY ADMINISTRATOR PERMISSIONS
    # ========================================================

    def test_administrator_cannot_manage_members(self):
        """
        A developer with role='admin' is not automatically
        the group owner.
        """

        self.assertFalse(
            is_group_owner(
                self.private_group,
                self.admin,
            )
        )

        self.assertFalse(
            is_group_admin(
                self.private_group,
                self.admin,
            )
        )

        self.assertFalse(
            can_manage_group_members(
                self.private_group,
                self.admin,
            )
        )

        self.assertFalse(
            can_invite_group_members(
                self.private_group,
                self.admin,
            )
        )

    # ========================================================
    # 3. ORDINARY MEMBER PERMISSIONS
    # ========================================================

    def test_ordinary_member_cannot_manage_members(self):
        """An ordinary member cannot manage other members."""

        self.assertTrue(
            is_group_member(
                self.private_group,
                self.member,
            )
        )

        self.assertFalse(
            is_group_admin(
                self.private_group,
                self.member,
            )
        )

        self.assertFalse(
            can_manage_group_members(
                self.private_group,
                self.member,
            )
        )

        self.assertFalse(
            can_invite_group_members(
                self.private_group,
                self.member,
            )
        )

    # ========================================================
    # 4. PRIVATE GROUP ACCESS
    # ========================================================

    def test_members_can_access_private_group(self):
        """The owner and accepted members can access the group."""

        for user in (
            self.owner,
            self.admin,
            self.member,
        ):
            with self.subTest(username=user.username):

                self.assertTrue(
                    can_view_group(
                        self.private_group,
                        user,
                    )
                )

    def test_outsider_cannot_access_private_group(self):
        """An outsider cannot access a private group."""

        self.assertFalse(
            is_group_member(
                self.private_group,
                self.outsider,
            )
        )

        self.assertFalse(
            can_view_group(
                self.private_group,
                self.outsider,
            )
        )

    # ========================================================
    # 5. PUBLIC GROUP ACCESS MUST BE REJECTED
    # ========================================================

    def test_public_group_access_is_rejected(self):
        """
        ColabVerse no longer permits public group access.

        Test the permission helper using a simulated
        non-private group without saving an invalid group
        to the database.
        """

        # Use the existing group object without changing
        # its database record.
        public_group = ProjectGroup(
            id=self.private_group.id,
            name="Legacy Public Group",
            description="Testing public group rejection.",
            owner=self.owner,
            is_private=False,
            join_policy="open",
        )

        # Even the owner cannot access a non-private group.
        self.assertFalse(
            can_view_group(
                public_group,
                self.owner,
            )
        )

        # Accepted members cannot access non-private groups.
        self.assertFalse(
            can_view_group(
                public_group,
                self.member,
            )
        )

        # Outsiders cannot access non-private groups.
        self.assertFalse(
            can_view_group(
                public_group,
                self.outsider,
            )
        )

    # ========================================================
    # 6. PENDING INVITATIONS
    # ========================================================

    def test_pending_invitation_does_not_grant_access(self):
        """
        A developer must become an accepted group member
        before receiving group permissions.

        Being invited alone is insufficient.
        """

        # This developer has no GroupMember record.
        self.assertFalse(
            is_group_member(
                self.private_group,
                self.invited_developer,
            )
        )

        self.assertFalse(
            can_view_group(
                self.private_group,
                self.invited_developer,
            )
        )

        self.assertFalse(
            can_use_development_features(
                self.private_group,
                self.invited_developer,
            )
        )

    # ========================================================
    # 7. OUTSIDER PERMISSIONS
    # ========================================================

    def test_outsider_cannot_manage_members(self):
        """An outsider cannot manage group membership."""

        self.assertFalse(
            can_manage_group_members(
                self.private_group,
                self.outsider,
            )
        )

        self.assertFalse(
            can_invite_group_members(
                self.private_group,
                self.outsider,
            )
        )

    # ========================================================
    # 8. DEVELOPMENT FEATURE PERMISSIONS
    # ========================================================

    def test_owner_can_use_development_features(self):
        """The group owner can access development features."""

        self.assertTrue(
            can_use_development_features(
                self.private_group,
                self.owner,
            )
        )

    def test_accepted_member_can_use_development_features(self):
        """Accepted members can access development features."""

        self.assertTrue(
            can_use_development_features(
                self.private_group,
                self.member,
            )
        )

    def test_outsider_cannot_use_development_features(self):
        """Outsiders cannot access development features."""

        self.assertFalse(
            can_use_development_features(
                self.private_group,
                self.outsider,
            )
        )

    # ========================================================
    # 9. ANONYMOUS USER PERMISSIONS
    # ========================================================

    def test_anonymous_user_cannot_access_group(self):
        """Unauthenticated visitors cannot access private groups."""

        anonymous_user = AnonymousUser()

        self.assertFalse(
            is_group_owner(
                self.private_group,
                anonymous_user,
            )
        )

        self.assertFalse(
            is_group_member(
                self.private_group,
                anonymous_user,
            )
        )

        self.assertFalse(
            can_view_group(
                self.private_group,
                anonymous_user,
            )
        )

        self.assertFalse(
            can_manage_group_members(
                self.private_group,
                anonymous_user,
            )
        )

        self.assertFalse(
            can_invite_group_members(
                self.private_group,
                anonymous_user,
            )
        )

        self.assertFalse(
            can_use_development_features(
                self.private_group,
                anonymous_user,
            )
        )