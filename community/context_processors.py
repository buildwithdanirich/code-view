"""
Context processors for ColabVerse private development groups.

Provide shared template data for authenticated developers.

This module currently supplies the number of pending
private group invitations belonging to the logged-in user.
"""

from community.models import GroupInvitation


def pending_group_invitations(request):
    """
    Return the number of pending group invitations.

    Django makes the returned dictionary available to
    templates that use RequestContext.

    Anonymous visitors receive a count of zero.
    """

    # Get the developer associated with this request.
    user = request.user

    # Anonymous visitors cannot receive group invitations.
    if not user.is_authenticated:
        return {
            "pending_invitation_count": 0,
        }

    # Count only pending invitations received by this developer.
    # Invitations sent by the developer are not included.
    pending_count = GroupInvitation.objects.filter(
        invited_user=user,
        status="pending",
    ).count()

    # Make the count available to Django templates.
    return {
        "pending_invitation_count": pending_count,
    }