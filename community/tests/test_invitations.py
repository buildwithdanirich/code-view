"""
Tests for CodeView private development group invitations.

Rules:
1. Only the group owner can send invitations.
2. A private group supports a maximum of 10 members.
3. The owner counts as one member.
4. Only invited developers can accept invitations.
5. A full group cannot accept additional members.
"""

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from community.models import (
    ProjectGroup,
    GroupMember,
)

from community.invitations import (
    send_group_invitation,
    accept_group_invitation,
)


User = get_user_model()


class GroupInvitationLimitTests(TestCase):
    """Verify private group invitation and membership limits."""

    def setUp(self):
        """Create a group owner and private development group."""

        # Create the group owner.
        self.owner = User.objects.create_user(
            username="invitation_owner",
            password="TestPassword123!",
        )

        # Create a private development group.
        self.group = ProjectGroup.objects.create(
            name="LiveKit Development Team",
            description="Private development group for testing.",
            owner=self.owner,
            is_private=True,
            join_policy="invite",
        )

        # Create the owner's membership record.
        GroupMember.objects.get_or_create(
            group=self.group,
            user=self.owner,
            defaults={"role": "admin"},
        )

    def create_developer(self, number):
        """Create a developer for invitation testing."""

        return User.objects.create_user(
            username=f"invited_developer_{number}",
            password="TestPassword123!",
        )

    def add_nine_members(self):
        """Add nine developers through the invitation workflow."""

        for number in range(1, 10):

            # Create a developer.
            developer = self.create_developer(number)

            # The owner sends an invitation.
            invitation = send_group_invitation(
                group=self.group,
                invited_by=self.owner,
                invited_user=developer,
            )

            # The developer accepts the invitation.
            accept_group_invitation(
                invitation_id=invitation.id,
                user=developer,
            )

    def test_owner_counts_toward_ten_member_limit(self):
        """The owner and nine developers make ten members."""

        # Add nine developers.
        self.add_nine_members()

        # Count every membership record.
        member_count = GroupMember.objects.filter(
            group=self.group,
        ).count()

        # One owner + nine developers = ten members.
        self.assertEqual(member_count, 10)

    def test_ninth_additional_developer_can_join(self):
        """The ninth invited developer can join successfully."""

        self.add_nine_members()

        # Confirm the group has exactly ten members.
        self.assertEqual(
            GroupMember.objects.filter(
                group=self.group,
            ).count(),
            10,
        )

    def test_eleventh_developer_cannot_be_invited(self):
        """The owner cannot invite another developer to a full group."""

        # Fill the group.
        self.add_nine_members()

        # Create an eleventh developer.
        extra_developer = self.create_developer(10)

        # Sending another invitation must fail.
        with self.assertRaises(ValidationError):

            send_group_invitation(
                group=self.group,
                invited_by=self.owner,
                invited_user=extra_developer,
            )

    def test_pending_invitation_cannot_exceed_limit(self):
        """An invitation cannot be accepted after the group becomes full."""

        # Create a developer before filling the group.
        extra_developer = self.create_developer(10)

        # Send an invitation while space is available.
        invitation = send_group_invitation(
            group=self.group,
            invited_by=self.owner,
            invited_user=extra_developer,
        )

        # Nine other developers accept their invitations.
        self.add_nine_members()

        # The group is now full.
        self.assertEqual(
            GroupMember.objects.filter(
                group=self.group,
            ).count(),
            10,
        )

        # The pending invitation must not bypass the limit.
        with self.assertRaises(ValidationError):

            accept_group_invitation(
                invitation_id=invitation.id,
                user=extra_developer,
            )

        # Confirm the extra developer was not added.
        self.assertFalse(
            GroupMember.objects.filter(
                group=self.group,
                user=extra_developer,
            ).exists()
        )

    def test_group_never_exceeds_ten_members(self):
        """Rejected invitations must not increase membership."""

        self.add_nine_members()

        extra_developer = self.create_developer(10)

        # Attempt to exceed the group limit.
        with self.assertRaises(ValidationError):

            send_group_invitation(
                group=self.group,
                invited_by=self.owner,
                invited_user=extra_developer,
            )

        # Membership must remain at ten.
        self.assertEqual(
            GroupMember.objects.filter(
                group=self.group,
            ).count(),
            10,
        )