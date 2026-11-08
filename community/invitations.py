"""
Private development group invitation services.

This file handles:
1. Sending invitations.
2. Accepting invitations.
3. Declining invitations.
4. Checking the 15-member limit.

Only private development groups use invitations.
"""

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import (
    ProjectGroup,
    GroupMember,
    GroupInvitation,
)

from .permissions import (
    is_group_owner,
)


# ============================================================
# 1. SEND GROUP INVITATION
# ============================================================

def send_group_invitation(group, invited_by, invited_user):
    """
    Allow a private-group owner to invite a developer.

    Example:
        Daniel owns a private development group.

        Daniel invites John.

        John receives a pending invitation.
    """

    # Only authenticated developers can send invitations.
    if not invited_by.is_authenticated:
        raise PermissionDenied(
            "You must log in to send invitations."
        )

    # The invited developer must exist.
    if invited_user is None or not invited_user.pk:
        raise ValidationError(
            "Select a valid developer to invite."
        )

    # Lock the group while checking invitation rules.
    with transaction.atomic():

        group = ProjectGroup.objects.select_for_update().get(
            pk=group.pk
        )

        # Normal chat groups do not use invitations.
        if not group.is_private:
            raise ValidationError(
                "Normal chat groups do not require invitations."
            )

        # Only the owner can invite developers.
        if not is_group_owner(group, invited_by):
            raise PermissionDenied(
                "Only the group owner can invite developers."
            )

        # The owner cannot invite themselves.
        if invited_user.pk == group.owner_id:
            raise ValidationError(
                "You cannot invite yourself."
            )

        # Prevent inviting an existing member.
        already_member = GroupMember.objects.filter(
            group=group,
            user=invited_user,
        ).exists()

        if already_member:
            raise ValidationError(
                "This developer is already a group member."
            )

        # Check how many developers are already members.
        member_count = GroupMember.objects.filter(
            group=group,
        ).exclude(
            user_id=group.owner_id,
        ).count()

        # The owner counts as one member.
        if member_count >= 14:
            raise ValidationError(
                "This private group already has 15 members."
            )

        # Look for an invitation sent previously.
        invitation = GroupInvitation.objects.filter(
            group=group,
            invited_user=invited_user,
        ).first()

        if invitation is not None:

            # Do not create another pending invitation.
            if invitation.status == "pending":
                raise ValidationError(
                    "This developer already has a pending invitation."
                )

            # Reuse an old accepted or declined invitation.
            invitation.status = "pending"
            invitation.responded_at = None
            invitation.invited_by = invited_by

            invitation.save()

            return invitation

        # Create a new pending invitation.
        try:
            invitation = GroupInvitation.objects.create(
                group=group,
                invited_by=invited_by,
                invited_user=invited_user,
                status="pending",
            )

        except IntegrityError:
            # The unique database constraint is a final safeguard.
            raise ValidationError(
                "An invitation already exists for this developer."
            )

        return invitation


# ============================================================
# 2. ACCEPT GROUP INVITATION
# ============================================================

def accept_group_invitation(invitation_id, user):
    """
    Allow an invited developer to accept an invitation.

    Example:
        John receives an invitation from Daniel.

        John clicks Accept.

        CodeView adds John to the private group.
    """

    # Only logged-in developers can accept invitations.
    if not user.is_authenticated:
        raise PermissionDenied(
            "You must log in to accept invitations."
        )

    with transaction.atomic():

        # Read the invitation to find its group.
        invitation = GroupInvitation.objects.get(
            pk=invitation_id
        )

        # Lock the group to prevent simultaneous acceptances
        # from exceeding the 15-member limit.
        group = ProjectGroup.objects.select_for_update().get(
            pk=invitation.group_id
        )

        # Lock the invitation after locking the group.
        invitation = GroupInvitation.objects.select_for_update().get(
            pk=invitation_id
        )

        # Only the invited developer can accept.
        if invitation.invited_user_id != user.pk:
            raise PermissionDenied(
                "This invitation does not belong to you."
            )

        # Only pending invitations can be accepted.
        if invitation.status != "pending":
            raise ValidationError(
                "This invitation is no longer pending."
            )

        # Invitations are only valid for private groups.
        if not group.is_private:
            raise ValidationError(
                "This group does not support invitations."
            )

        # Check whether the developer is already a member.
        already_member = GroupMember.objects.filter(
            group=group,
            user=user,
        ).exists()

        if already_member or group.owner_id == user.pk:
            raise ValidationError(
                "You are already a member of this group."
            )

        # Count members other than the owner.
        member_count = GroupMember.objects.filter(
            group=group,
        ).exclude(
            user_id=group.owner_id,
        ).count()

        # Maximum: 14 members + 1 owner.
        if member_count >= 14:
            raise ValidationError(
                "This private group has reached its 15-member limit."
            )

        # Add the invited developer to the group.
        GroupMember.objects.create(
            group=group,
            user=user,
            role="member",
        )

        # Mark the invitation as accepted.
        invitation.status = "accepted"
        invitation.responded_at = timezone.now()

        invitation.save()

        return invitation


# ============================================================
# 3. DECLINE GROUP INVITATION
# ============================================================

def decline_group_invitation(invitation_id, user):
    """
    Allow an invited developer to decline an invitation.

    Declining does not create a group membership.
    """

    if not user.is_authenticated:
        raise PermissionDenied(
            "You must log in to decline invitations."
        )

    with transaction.atomic():

        # Lock the invitation while updating its status.
        invitation = GroupInvitation.objects.select_for_update().get(
            pk=invitation_id
        )

        # Only the invited developer can decline.
        if invitation.invited_user_id != user.pk:
            raise PermissionDenied(
                "This invitation does not belong to you."
            )

        # Prevent responding more than once.
        if invitation.status != "pending":
            raise ValidationError(
                "This invitation is no longer pending."
            )

        # Mark the invitation as declined.
        invitation.status = "declined"
        invitation.responded_at = timezone.now()

        invitation.save()

        return invitation


# ============================================================
# 4. GET PENDING INVITATIONS
# ============================================================

def get_pending_invitations(user):
    """
    Return invitations waiting for a developer's response.

    Example:
        John logs into CodeView.

        CodeView displays:
            Python Developers — Accept / Decline
            Backend Team — Accept / Decline
    """

    if not user.is_authenticated:
        return GroupInvitation.objects.none()

    return (
        GroupInvitation.objects
        .filter(
            invited_user=user,
            status="pending",
            group__is_private=True,
        )
        .select_related(
            "group",
            "invited_by",
        )
        .order_by("-created_at")
    )