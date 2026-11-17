"""
Permission helpers for ColabVerse private development groups.

Security rules:

1. Every ColabVerse group is private.
2. Only the group owner and accepted members can access a group.
3. Pending invitations do not grant access.
4. Only the group owner can invite or remove members.
5. Only the group owner has administrative permissions.
6. Development features require authorized group membership.
"""


# ============================================================
# 1. GROUP OWNERSHIP
# ============================================================

def is_group_owner(group, user):
    """
    Check whether the developer owns the group.

    Returns True only when:
        - The developer is authenticated.
        - The developer owns the group.
        - The group is private.
    """

    if not user.is_authenticated:
        return False

    if not group.is_private:
        return False

    return group.owner_id == user.pk


# ============================================================
# 2. GROUP MEMBERSHIP
# ============================================================

def is_group_member(group, user):
    """
    Check whether a developer belongs to a private group.

    The owner automatically has membership permissions.

    Other developers must have an existing GroupMember record.

    Pending invitations do not count as membership.
    """

    if not user.is_authenticated:
        return False

    # Reject access to non-private groups.
    if not group.is_private:
        return False

    # The group owner always has access.
    if is_group_owner(group, user):
        return True

    # Import locally to avoid circular imports.
    from .models import GroupMember

    # Only accepted/current members have GroupMember records.
    return GroupMember.objects.filter(
        group_id=group.pk,
        user_id=user.pk,
    ).exists()


# ============================================================
# 3. GROUP ADMINISTRATION
# ============================================================

def is_group_admin(group, user):
    """
    Compatibility helper for existing CodeView functionality.

    Only the group owner has administrative permissions.

    Ordinary members cannot manage the group.
    """

    return is_group_owner(group, user)


# ============================================================
# 4. GROUP VISIBILITY
# ============================================================

def can_view_group(group, user):
    """
    Check whether a developer can access a private group.

    Allowed:
        - Group owner.
        - Accepted group members.

    Denied:
        - Anonymous visitors.
        - Developers outside the group.
        - Developers with pending invitations.
        - Developers removed from the group.
        - Non-private groups.
    """

    # All groups must be private.
    if not group.is_private:
        return False

    # Membership verification includes the group owner.
    return is_group_member(group, user)


# ============================================================
# 5. MEMBERSHIP MANAGEMENT
# ============================================================

def can_manage_group_members(group, user):
    """
    Only the private group owner can manage membership.

    Examples:
        - Remove members.
        - Manage membership permissions.
    """

    return is_group_owner(group, user)


# ============================================================
# 6. GROUP INVITATIONS
# ============================================================

def can_invite_group_members(group, user):
    """
    Only the private group owner can invite developers.

    Ordinary members cannot send group invitations.
    """

    return is_group_owner(group, user)


# ============================================================
# 7. DEVELOPMENT FEATURES
# ============================================================

def can_use_development_features(group, user):
    """
    Check whether a developer can access development features.

    Examples:
        - GitHub repository integration.
        - Meeting rooms.
        - Screen sharing.
        - Collaborative whiteboard.

    Only the group owner and accepted members are allowed.
    """

    return is_group_member(group, user)