"""Centralized permission checks for CodeView groups."""

from .models import GroupMember


# ============================================================
# 1. CHECK GROUP OWNER
# ============================================================

def is_group_owner(group, user):
    """Return True if the user owns the group."""

    # Anonymous users cannot own or manage groups.
    if not user.is_authenticated:
        return False

    # Compare the group's owner ID with the user's ID.
    return group.owner_id == user.pk


# ============================================================
# 2. CHECK GROUP ADMINISTRATOR
# ============================================================

def is_group_admin(group, user):
    """Return True if the user is the owner or an administrator."""

    # Reject anonymous users.
    if not user.is_authenticated:
        return False

    # The group owner always has administrator permissions.
    if is_group_owner(group, user):
        return True

    # Check whether the user has an administrator membership.
    return GroupMember.objects.filter(
        group=group,
        user=user,
        role="admin",
    ).exists()


# ============================================================
# 3. CHECK GROUP MEMBERSHIP
# ============================================================

def is_group_member(group, user):
    """Return True if the user owns or belongs to the group."""

    # Reject anonymous users.
    if not user.is_authenticated:
        return False

    # The owner is automatically considered a member.
    if is_group_owner(group, user):
        return True

    # Check whether the developer has a membership record.
    return GroupMember.objects.filter(
        group=group,
        user=user,
    ).exists()


# ============================================================
# 4. CHECK PRIVATE GROUP ACCESS
# ============================================================

def can_view_group(group, user):
    """Check whether a developer can view a group's main page."""

    # Group pages require authentication.
    if not user.is_authenticated:
        return False

    # Public communities are visible to logged-in developers.
    if not group.is_private:
        return True

    # Private groups are accessible only to their members.
    return is_group_member(group, user)


# ============================================================
# 5. CHECK MEMBER MANAGEMENT PERMISSIONS
# ============================================================

def can_manage_group_members(group, user):
    """Check whether a developer can manage group memberships."""

    # Only owners and administrators can manage members.
    return is_group_admin(group, user)
    