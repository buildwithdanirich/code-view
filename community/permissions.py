"""
Permission helpers for CodeView groups.

Group rules:

1. Public groups:
   - Registered developers can view them.
   - Developers can join freely.

2. Private development groups:
   - Only accepted members can access them.
   - Only the owner can invite developers.
   - Only the owner can remove members.
   - Development features are private-group only.

3. Group ownership:
   - The owner has management permissions.
   - Ordinary members cannot manage membership.
"""


def is_group_owner(group, user):
    """
    Check whether the developer owns the group.

    Returns True if the user is the owner.
    Otherwise, returns False.
    """

    if not user.is_authenticated:
        return False

    return group.owner_id == user.id


def is_group_member(group, user):
    """
    Check whether the developer belongs to the group.

    The group owner is always considered a member.
    Other developers must have a GroupMember record.
    """

    if not user.is_authenticated:
        return False

    if is_group_owner(group, user):
        return True

    # Import here to avoid unnecessary circular imports.
    from .models import GroupMember

    return GroupMember.objects.filter(
        group=group,
        user=user,
    ).exists()


def is_group_admin(group, user):
    """
    Compatibility helper for older CodeView code.

    CodeView no longer supports secondary group admins.

    Only the owner has administrative permissions.
    """

    return is_group_owner(group, user)


def can_view_group(group, user):
    """
    Check whether a developer can view a group.

    Public groups:
        Any authenticated developer can view them.

    Private groups:
        Only accepted members and the owner can view them.
    """

    if not user.is_authenticated:
        return False

    if not group.is_private:
        return True

    return is_group_member(group, user)


def can_manage_group_members(group, user):
    """
    Only the group owner can remove members
    or manage membership.
    """

    return is_group_owner(group, user)


def can_invite_group_members(group, user):
    """
    Only private development group owners
    can send invitations.
    """

    if not group.is_private:
        return False

    return is_group_owner(group, user)


def can_use_development_features(group, user):
    """
    Check whether the developer can access features
    reserved for private development groups.

    Examples:
    - GitHub repository integration
    - Meeting rooms
    - Screen sharing
    - Whiteboard
    """

    if not group.is_private:
        return False

    return is_group_member(group, user)