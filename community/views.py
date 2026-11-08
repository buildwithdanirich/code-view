"""
CodeView community views.

Features:
- Public chat groups
- Private invitation-only development groups
- Group dashboard and membership management
- Discussions, comments, replies, likes, and hiding
- Group chat with text, code, voice notes, and files
- Message editing and deletion
- Private development meeting room
- GitHub repository connection and read-only file browsing

Private group membership is managed by invitation_views.py
and invitations.py.

The old membership-request approval and direct-add-member
workflows have been removed.
"""

import json
import logging

from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Q
from django.http import (
    HttpResponseBadRequest,
    HttpResponseForbidden,
    JsonResponse,
)
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .forms import (
    ProjectGroupForm,
    GroupDiscussionForm,
    GroupDiscussionCommentForm,
    GroupChatMessageForm,
    GroupRepositoryForm,
)
from .models import (
    ProjectGroup,
    GroupMember,
    GroupInvitation,  # Stores private group invitations.
    GroupDiscussion,
    GroupDiscussionComment,
    GroupDiscussionLike,
    HiddenDiscussion,
    GroupChatMessage,
    GroupMessageReaction,
    GroupRepository,
)

from .permissions import (
    is_group_owner,
    is_group_member,
    can_view_group,
    can_manage_group_members,
)

logger = logging.getLogger(__name__)


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def group_members_url(group_id):
    """Return the URL for the group members section."""

    return (
        reverse("group_detail", kwargs={"group_id": group_id})
        + "#group-members"
    )


def group_chat_url(group_id):
    """Return the URL for the group chat section."""

    return (
        reverse("group_detail", kwargs={"group_id": group_id})
        + "#group-chat"
    )


def is_ajax_request(request):
    """Check whether JavaScript submitted the request."""

    return (
        request.headers.get("X-Requested-With")
        == "XMLHttpRequest"
    )


def broadcast_group_event(group_name, event_type, data):
    """
    Send an event to connected WebSocket clients.

    This helper keeps the event format used by the
    existing CodeView Channels consumers.
    """

    channel_layer = get_channel_layer()

    if channel_layer is None:
        return

    async_to_sync(channel_layer.group_send)(
        group_name,
        {
            "type": event_type,
            "data": data,
        },
    )


def github_request_json(url):
    """
    Request JSON from the GitHub API.

    The timeout prevents an external service from
    keeping a Django request waiting indefinitely.
    """

    github_request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "CodeView",
        },
    )

    with urlopen(github_request, timeout=10) as response:
        return json.load(response)


# ============================================================
# 1. GROUP DASHBOARD
# ============================================================

# ============================================================
# 1. GROUP DASHBOARD
# ============================================================

@login_required
def groups(request):
    """
    Display the CodeView groups dashboard.

    Features:
    1. Show public groups.
    2. Show private groups the developer belongs to.
    3. Show groups owned by the developer.
    4. Count pending private group invitations.
    """

    # Find groups where the logged-in developer is a member.
    member_group_ids = GroupMember.objects.filter(
        user=request.user,
    ).values_list("group_id", flat=True)

    # Display public groups and private groups the user can access.
    project_groups = (
        ProjectGroup.objects
        .filter(
            Q(is_private=False)
            | Q(id__in=member_group_ids)
            | Q(owner=request.user)
        )
        .select_related("owner")
        .distinct()
    )

    # Check membership for each displayed group.
    for group in project_groups:

        group.is_member = is_group_member(
            group,
            request.user,
        )

        # Temporary compatibility with older templates.
        group.has_pending_request = False

    # ========================================================
    # COUNT PENDING INVITATIONS
    # ========================================================

    # Count only invitations received by the logged-in user.
    # Accepted and declined invitations are excluded.
    pending_invitation_count = GroupInvitation.objects.filter(
        invited_user=request.user,
        status="pending",
    ).count()

    # ========================================================
    # RENDER GROUP DASHBOARD
    # ========================================================

    return render(
        request,
        "community/groups.html",
        {
            "groups": project_groups,

            # Used by the My Invitations notification badge.
            "pending_invitation_count": pending_invitation_count,
        },
    )


# ============================================================
# 2. CREATE GROUP
# ============================================================

@login_required
def create_group(request):
    """
    Create either a public chat group or private development group.

    Public groups use open joining.
    Private groups use invitations.
    """

    if request.method == "POST":
        form = ProjectGroupForm(request.POST)

        if form.is_valid():

            with transaction.atomic():

                group = form.save(commit=False)

                # The logged-in developer owns the group.
                group.owner = request.user

                # Never trust the browser to choose joining rules.
                group.join_policy = (
                    "invite" if group.is_private else "open"
                )

                group.save()

                # The owner is the first group member.
                GroupMember.objects.create(
                    group=group,
                    user=request.user,
                    role="admin",
                )

            messages.success(
                request,
                "Your group was created successfully!",
            )

            return redirect("groups")

    else:
        form = ProjectGroupForm()

    return render(
        request,
        "community/create_group.html",
        {
            "form": form,
        },
    )


# ============================================================
# 3. JOIN PUBLIC GROUP
# ============================================================

@login_required
@require_POST
def join_group(request, group_id):
    """
    Allow registered developers to join public chat groups.

    Private groups require invitations and cannot be joined here.
    """

    with transaction.atomic():

        group = get_object_or_404(
            ProjectGroup.objects.select_for_update(),
            id=group_id,
        )

        if is_group_member(group, request.user):

            messages.info(
                request,
                "You are already a member of this group.",
            )

            return redirect(
                "group_detail",
                group_id=group.id,
            )

        # Private groups must use the invitation service.
        if group.is_private:
            return HttpResponseForbidden(
                "Private development groups require an invitation."
            )

        # Public groups allow direct joining.
        if group.join_policy != "open":
            return HttpResponseForbidden(
                "This group does not allow direct joining."
            )

        GroupMember.objects.get_or_create(
            group=group,
            user=request.user,
            defaults={
                "role": "member",
            },
        )

    messages.success(
        request,
        "You joined the community successfully!",
    )

    return redirect(
        "group_detail",
        group_id=group.id,
    )


# ============================================================
# 4. GROUP DETAILS
# ============================================================

@login_required
def group_detail(request, group_id):
    """
    Display the group workspace.

    Includes:
    - Group members
    - Discussions
    - Chat messages
    """

    group = get_object_or_404(
        ProjectGroup.objects.select_related("owner"),
        id=group_id,
    )

    if not can_view_group(group, request.user):
        return HttpResponseForbidden(
            "You must be a member to access this private group."
        )

    is_member = is_group_member(
        group,
        request.user,
    )

    is_owner = is_group_owner(
        group,
        request.user,
    )

    members = (
        GroupMember.objects
        .filter(group=group)
        .select_related("user")
        .order_by("joined_at")
    )

    # --------------------------------------------------------
    # DISCUSSIONS
    # --------------------------------------------------------

    hidden_discussion_ids = HiddenDiscussion.objects.filter(
        user=request.user,
    ).values_list("discussion_id", flat=True)

    discussions = list(
        GroupDiscussion.objects
        .filter(group=group)
        .exclude(id__in=hidden_discussion_ids)
        .select_related("author")
        .annotate(
            like_count=Count("likes", distinct=True),
            comment_count=Count("comments", distinct=True),
        )
        .order_by("-created_at")[:20]
    )

    liked_discussion_ids = set(
        GroupDiscussionLike.objects
        .filter(
            user=request.user,
            discussion__in=discussions,
        )
        .values_list("discussion_id", flat=True)
    )

    for discussion in discussions:
        discussion.liked_by_user = (
            discussion.id in liked_discussion_ids
        )

    # --------------------------------------------------------
    # GROUP CHAT
    # --------------------------------------------------------

    chat_messages = []
    chat_form = None

    if is_member:

        chat_messages = list(
            GroupChatMessage.objects
            .filter(group=group)
            .select_related(
                "sender",
                "reply_to",
                "reply_to__sender",
            )
            .order_by("-created_at", "-id")[:50]
        )

        chat_messages.reverse()

        chat_form = GroupChatMessageForm()

    return render(
        request,
        "community/group_detail.html",
        {
            "group": group,
            "members": members,
            "is_member": is_member,
            "is_owner": is_owner,

            # Existing templates may still use is_admin.
            # Only the owner has administrator permissions.
            "is_admin": is_owner,

            # Old approval requests no longer exist.
            "pending_request": False,

            "discussions": discussions,
            "chat_messages": chat_messages,
            "chat_form": chat_form,
        },
    )


# ============================================================
# 5. REMOVE GROUP MEMBER
# ============================================================

@login_required
@require_POST
def remove_group_member(request, group_id, member_id):
    """
    Allow only the group owner to remove members.

    The owner cannot remove themselves.
    """

    with transaction.atomic():

        group = get_object_or_404(
            ProjectGroup.objects.select_for_update(),
            id=group_id,
        )

        if not can_manage_group_members(group, request.user):
            return HttpResponseForbidden(
                "Only the group owner can remove members."
            )

        target = get_object_or_404(
            GroupMember.objects.select_for_update(),
            id=member_id,
            group=group,
        )

        if target.user_id == group.owner_id:
            return HttpResponseForbidden(
                "The group owner cannot be removed."
            )

        username = target.user.username

        target.delete()

    messages.success(
        request,
        f"{username} was removed from the group.",
    )

    return redirect(group_members_url(group_id))


# ============================================================
# 6. LEAVE GROUP
# ============================================================

@login_required
@require_POST
def leave_group(request, group_id):
    """
    Allow members to leave voluntarily.

    The group owner cannot leave while still owning the group.
    """

    with transaction.atomic():

        group = get_object_or_404(
            ProjectGroup.objects.select_for_update(),
            id=group_id,
        )

        if is_group_owner(group, request.user):
            return HttpResponseForbidden(
                "The group owner cannot leave their own group."
            )

        membership = GroupMember.objects.filter(
            group=group,
            user=request.user,
        ).first()

        if membership is None:
            return HttpResponseBadRequest(
                "You are not a member of this group."
            )

        membership.delete()

    messages.success(
        request,
        "You have left the group successfully.",
    )

    return redirect("groups")


# ============================================================
# 7. SEARCH DEVELOPERS FOR INVITATIONS
# ============================================================
@login_required
@require_GET
def search_group_developers(request, group_id):
    """
    Allow private-group owners to search registered developers.

    Rules:
    1. Only private-group owners can search.
    2. Existing members are excluded.
    3. Developers with pending invitations are excluded.
    4. Searching does not automatically add members.
    """

    # Find the requested group.
    group = get_object_or_404(
        ProjectGroup,
        id=group_id,
    )

    # Only the owner of a private group can search developers.
    if not group.is_private or not is_group_owner(
        group,
        request.user,
    ):
        return JsonResponse(
            {"error": "Permission denied."},
            status=403,
        )

    # Get the developer's search text.
    query = request.GET.get("q", "").strip()

    # Require at least two characters.
    if len(query) < 2:
        return JsonResponse({"users": []})

    User = get_user_model()

    # Find developers who already belong to this group.
    existing_members = GroupMember.objects.filter(
        group=group,
    ).values_list("user_id", flat=True)

    # Find developers who already have pending invitations.
    pending_invitees = GroupInvitation.objects.filter(
        group=group,
        status="pending",
    ).values_list("invited_user_id", flat=True)

    # Search registered developers.
    developers = (
        User.objects
        .filter(
            username__icontains=query,
            is_active=True,
        )
        .exclude(id__in=existing_members)
        .exclude(id__in=pending_invitees)
        .exclude(id=group.owner_id)
        .order_by("username")[:10]
    )

    # Prepare results for developer_search.js.
    results = [
        {
            "id": developer.id,
            "username": developer.username,
        }
        for developer in developers
    ]

    return JsonResponse({
        "users": results,
    })


# ============================================================
# 8. PRIVATE DEVELOPMENT MEETING ROOM
# ============================================================

@login_required
def meeting_room(request, group_id):
    """
    Display the private development workspace.

    LiveKit meeting functionality will be connected later.
    """

    group = get_object_or_404(
        ProjectGroup,
        id=group_id,
    )

    if not group.is_private:
        return HttpResponseForbidden(
            "Meeting rooms are only available to private groups."
        )

    if not is_group_member(group, request.user):
        return HttpResponseForbidden(
            "You must belong to this group to enter its meeting room."
        )

    repository = GroupRepository.objects.filter(
        group=group,
    ).first()

    repository_form = GroupRepositoryForm()

    recent_messages = list(
        GroupChatMessage.objects
        .filter(group=group)
        .select_related(
            "sender",
            "reply_to",
            "reply_to__sender",
        )
        .order_by("-created_at", "-id")[:50]
    )

    recent_messages.reverse()

    return render(
        request,
        "community/meeting_room.html",
        {
            "group": group,
            "repository": repository,
            "repository_form": repository_form,
            "can_manage_repository": is_group_owner(
                group,
                request.user,
            ),
            "chat_messages": recent_messages,
        },
    )


# ============================================================
# 9. CREATE DISCUSSION
# ============================================================

@login_required
@require_POST
def create_discussion(request, group_id):
    """Allow group members to create discussions."""

    group = get_object_or_404(
        ProjectGroup,
        id=group_id,
    )

    if not is_group_member(group, request.user):
        return HttpResponseForbidden(
            "You must be a group member to create discussions."
        )

    form = GroupDiscussionForm(request.POST)

    if form.is_valid():

        discussion = form.save(commit=False)

        discussion.group = group
        discussion.author = request.user

        discussion.save()

        messages.success(
            request,
            "Your discussion was posted successfully!",
        )

    else:

        messages.error(
            request,
            "Please enter a valid discussion title and message.",
        )

    return redirect(
        "group_detail",
        group_id=group.id,
    )


# ============================================================
# 10. DISCUSSION DETAILS
# ============================================================

@login_required
def discussion_detail(request, group_id, discussion_id):
    """Display a discussion and its comments."""

    group = get_object_or_404(
        ProjectGroup,
        id=group_id,
    )

    if not can_view_group(group, request.user):
        return HttpResponseForbidden(
            "You must be a member to view this discussion."
        )

    discussion = get_object_or_404(
        GroupDiscussion.objects.select_related("author"),
        id=discussion_id,
        group=group,
    )

    if HiddenDiscussion.objects.filter(
        discussion=discussion,
        user=request.user,
    ).exists():
        return HttpResponseForbidden(
            "You have hidden this discussion."
        )

    comments = (
        GroupDiscussionComment.objects
        .filter(discussion=discussion)
        .select_related("author", "parent")
        .order_by("created_at", "-id")
    )

    liked_by_user = GroupDiscussionLike.objects.filter(
        discussion=discussion,
        user=request.user,
    ).exists()

    return render(
        request,
        "community/discussion_detail.html",
        {
            "group": group,
            "discussion": discussion,
            "comments": comments,
            "liked_by_user": liked_by_user,
            "is_member": is_group_member(group, request.user),
            "comment_form": GroupDiscussionCommentForm(),
        },
    )


# ============================================================
# 11. ADD DISCUSSION COMMENT OR REPLY
# ============================================================

@login_required
@require_POST
def add_discussion_comment(request, group_id, discussion_id):
    """Allow members to comment and reply to discussions."""

    group = get_object_or_404(
        ProjectGroup,
        id=group_id,
    )

    if not is_group_member(group, request.user):
        return HttpResponseForbidden(
            "You must be a group member to comment."
        )

    discussion = get_object_or_404(
        GroupDiscussion,
        id=discussion_id,
        group=group,
    )

    form = GroupDiscussionCommentForm(request.POST)

    if not form.is_valid():

        if is_ajax_request(request):
            return JsonResponse(
                {
                    "success": False,
                    "error": "Please enter a valid comment.",
                    "errors": form.errors.get_json_data(),
                },
                status=400,
            )

        messages.error(
            request,
            "Please enter a valid comment.",
        )

        return redirect(
            "discussion_detail",
            group_id=group.id,
            discussion_id=discussion.id,
        )

    comment = form.save(commit=False)

    comment.discussion = discussion
    comment.author = request.user

    parent_id = request.POST.get("parent_id", "").strip()

    if parent_id:

        parent_comment = get_object_or_404(
            GroupDiscussionComment,
            id=parent_id,
            discussion=discussion,
        )

        comment.parent = parent_comment

    with transaction.atomic():

        comment.save()

        comment_count = GroupDiscussionComment.objects.filter(
            discussion=discussion,
        ).count()

        event = {
            "event": "discussion_comment",
            "discussion_id": discussion.id,
            "comment_count": comment_count,
            "comment_id": comment.id,
            "author": request.user.username,
            "content": comment.content,
            "parent_id": comment.parent_id,
            "parent_author": (
                comment.parent.author.username
                if comment.parent_id
                else None
            ),
            "created_at": comment.created_at.strftime(
                "%b %d, %Y - %H:%M"
            ),
        }

        transaction.on_commit(
            lambda: broadcast_group_event(
                f"group_discussions_{group.id}",
                "discussion.comment",
                event,
            )
        )

    if is_ajax_request(request):
        return JsonResponse(
            {
                "success": True,
                "comment_id": comment.id,
            }
        )

    return redirect(
        "discussion_detail",
        group_id=group.id,
        discussion_id=discussion.id,
    )


# ============================================================
# 12. LIKE OR UNLIKE DISCUSSION
# ============================================================

@login_required
@require_POST
def toggle_discussion_like(request, group_id, discussion_id):
    """Toggle a discussion like and notify connected browsers."""

    group = get_object_or_404(
        ProjectGroup,
        id=group_id,
    )

    if not is_group_member(group, request.user):
        return HttpResponseForbidden(
            "You must be a group member to like discussions."
        )

    discussion = get_object_or_404(
        GroupDiscussion,
        id=discussion_id,
        group=group,
    )

    with transaction.atomic():

        # Serialize overlapping likes from the same developer.
        User = get_user_model()

        User.objects.select_for_update().get(
            pk=request.user.pk,
        )

        existing_like = GroupDiscussionLike.objects.filter(
            discussion=discussion,
            user=request.user,
        ).first()

        if existing_like:

            existing_like.delete()
            liked = False

        else:

            GroupDiscussionLike.objects.create(
                discussion=discussion,
                user=request.user,
            )

            liked = True

        like_count = GroupDiscussionLike.objects.filter(
            discussion=discussion,
        ).count()

        event = {
            "event": "discussion_like",
            "discussion_id": discussion.id,
            "like_count": like_count,
        }

        transaction.on_commit(
            lambda: broadcast_group_event(
                f"group_discussions_{group.id}",
                "discussion.like",
                event,
            )
        )

    if is_ajax_request(request):
        return JsonResponse(
            {
                "liked": liked,
                "like_count": like_count,
            }
        )

    return redirect(
        "discussion_detail",
        group_id=group.id,
        discussion_id=discussion.id,
    )


# ============================================================
# 13. HIDE DISCUSSION
# ============================================================

@login_required
@require_POST
def hide_discussion(request, group_id, discussion_id):
    """Hide a discussion from the current developer."""

    group = get_object_or_404(
        ProjectGroup,
        id=group_id,
    )

    if not is_group_member(group, request.user):
        return HttpResponseForbidden(
            "You must be a group member to hide discussions."
        )

    discussion = get_object_or_404(
        GroupDiscussion,
        id=discussion_id,
        group=group,
    )

    HiddenDiscussion.objects.get_or_create(
        discussion=discussion,
        user=request.user,
    )

    messages.success(
        request,
        "Discussion hidden from your feed.",
    )

    return redirect(
        "group_detail",
        group_id=group.id,
    )


# ============================================================
# 14. GROUP CHAT ROOM
# ============================================================
# ============================================================
# GROUP CHAT PAGE
# ============================================================

@login_required
def group_chat(request, group_id):
    """
    Display chat history to authorized group members.

    Features:
        - Load the latest 50 messages.
        - Load saved emoji reactions.
        - Count reactions for each message.
        - Identify the logged-in developer's reaction.
    """

    # ========================================================
    # 1. FIND THE GROUP
    # ========================================================

    group = get_object_or_404(
        ProjectGroup,
        id=group_id,
    )

    # Only authorized group members can access the chat.
    if not is_group_member(group, request.user):

        return HttpResponseForbidden(
            "You must be a group member to access its chat."
        )

    # ========================================================
    # 2. LOAD THE LATEST 50 MESSAGES
    # ========================================================

    recent_messages = list(
        GroupChatMessage.objects
        .filter(group=group)
        .select_related(
            "sender",
            "reply_to",
            "reply_to__sender",
        )
        .prefetch_related(
            "reactions",
        )
        .order_by("-created_at", "-id")[:50]
    )

    # Display oldest messages first.
    recent_messages.reverse()

    # ========================================================
    # 3. PREPARE SAVED EMOJI REACTIONS
    # ========================================================

    for chat_message in recent_messages:

        # Store reaction totals for this message.
        reaction_summary = {}

        # Store the logged-in developer's selected emoji.
        my_reaction = None

        # Deleted messages should not display reactions.
        if chat_message.deleted_at is None:

            # Read prefetched reactions without extra queries.
            for reaction in chat_message.reactions.all():

                emoji = reaction.emoji

                # Count how many developers selected this emoji.
                reaction_summary[emoji] = (
                    reaction_summary.get(emoji, 0) + 1
                )

                # Identify the logged-in developer's reaction.
                if reaction.user_id == request.user.id:

                    my_reaction = emoji

        # Make these values available in the HTML template.
        chat_message.reaction_summary = reaction_summary

        chat_message.my_reaction = my_reaction

    # ========================================================
    # 4. DISPLAY THE CHAT PAGE
    # ========================================================

    return render(
        request,
        "community/group_chat.html",
        {
            "group": group,
            "chat_messages": recent_messages,
            "chat_form": GroupChatMessageForm(),
        },
    )


# ============================================================
# 15. SEND GROUP CHAT MESSAGE
# ============================================================
@login_required
@require_POST
def send_group_message(request, group_id):
    """
    Save a chat message and broadcast it through WebSockets.

    Supports:
        - Text messages
        - Code snippets
        - Voice notes
        - File attachments
        - Replies

    Attachments use protected download URLs.
    """

    # Find the group receiving the message.
    group = get_object_or_404(
        ProjectGroup,
        id=group_id,
    )

    # Only group members can send messages.
    if not is_group_member(group, request.user):
        return HttpResponseForbidden(
            "You must be a group member to send messages."
        )

    # Validate the submitted message and uploaded files.
    form = GroupChatMessageForm(
        request.POST,
        request.FILES,
    )

    if not form.is_valid():

        # Return validation errors for JavaScript requests.
        if is_ajax_request(request):
            return JsonResponse(
                {
                    "success": False,
                    "error": "Your message is invalid.",
                    "details": form.errors.get_json_data(),
                },
                status=400,
            )

        # Show an error for normal form submissions.
        messages.error(
            request,
            "Your message is invalid. Check the content or attachment.",
        )

        return redirect(group_chat_url(group.id))

    # Create the message object without saving it yet.
    chat_message = form.save(commit=False)

    # Associate the message with its group and sender.
    chat_message.group = group
    chat_message.sender = request.user

    # Check whether the message is replying to another message.
    reply_to_id = request.POST.get(
        "reply_to_id",
        "",
    ).strip()

    if reply_to_id:

        # Replies must reference messages in the same group.
        reply_to_message = get_object_or_404(
            GroupChatMessage,
            id=reply_to_id,
            group=group,
            deleted_at__isnull=True,
        )

        chat_message.reply_to = reply_to_message

    # Save the message inside a database transaction.
    with transaction.atomic():

        chat_message.save()

        # Default to no attachment.
        attachment_url = None

        # Generate a protected URL when an attachment exists.
        if chat_message.attachment:

            attachment_url = reverse(
                "download_group_attachment",
                args=[
                    group.id,
                    chat_message.id,
                ],
            )

        # Prepare the message for WebSocket broadcasting.
        message_data = {
            "type": "message_created",
            "message_id": chat_message.id,
            "group_id": group.id,
            "sender_id": request.user.id,
            "sender": request.user.username,
            "content": chat_message.content,
            "message_type": chat_message.message_type,
            "created_at": chat_message.created_at.isoformat(),
            "reply_to_id": chat_message.reply_to_id,
            "attachment_url": attachment_url,
        }

        # Broadcast only after the database transaction succeeds.
        transaction.on_commit(
            lambda: broadcast_group_event(
                f"group_chat_{group.id}",
                "chat.message",
                message_data,
            )
        )

    # Return JSON for JavaScript requests.
    if is_ajax_request(request):
        return JsonResponse(
            {
                "success": True,
                "message_id": chat_message.id,
                "message": "Message sent successfully.",
            },
            status=201,
        )

    # Redirect normal form submissions back to the group chat.
    return redirect(group_chat_url(group.id))


# ============================================================
# 16. EDIT GROUP CHAT MESSAGE
# ============================================================

@login_required
@require_POST
def edit_group_message(request, group_id, message_id):
    """Allow developers to edit their own text messages."""

    group = get_object_or_404(
        ProjectGroup,
        id=group_id,
    )

    if not is_group_member(group, request.user):
        return HttpResponseForbidden(
            "You must be a group member to edit messages."
        )

    chat_message = get_object_or_404(
        GroupChatMessage,
        id=message_id,
        group=group,
    )

    if chat_message.sender_id != request.user.id:
        return HttpResponseForbidden(
            "You can only edit your own messages."
        )

    if chat_message.message_type != "text":

        if is_ajax_request(request):
            return JsonResponse(
                {
                    "success": False,
                    "error": "Only text messages can be edited.",
                },
                status=400,
            )

        messages.error(
            request,
            "Only text messages can be edited.",
        )

        return redirect(group_chat_url(group.id))

    # Do not allow editing a deleted message.
    if chat_message.deleted_at is not None:
        return HttpResponseBadRequest(
            "Deleted messages cannot be edited."
        )

    new_content = request.POST.get(
        "content",
        "",
    ).strip()

    if not new_content:

        if is_ajax_request(request):
            return JsonResponse(
                {
                    "success": False,
                    "error": "Your message cannot be empty.",
                },
                status=400,
            )

        messages.error(
            request,
            "Your message cannot be empty.",
        )

        return redirect(group_chat_url(group.id))

    with transaction.atomic():

        chat_message.content = new_content
        chat_message.edited_at = timezone.now()

        chat_message.save(
            update_fields=[
                "content",
                "edited_at",
            ],
        )

        message_data = {
            "type": "message_edited",
            "message_id": chat_message.id,
            "group_id": group.id,
            "content": chat_message.content,
            "edited_at": chat_message.edited_at.isoformat(),
        }

        transaction.on_commit(
            lambda: broadcast_group_event(
                f"group_chat_{group.id}",
                "chat.message",
                message_data,
            )
        )

    if is_ajax_request(request):
        return JsonResponse(
            {
                "success": True,
                "message_id": chat_message.id,
                "content": chat_message.content,
                "edited_at": chat_message.edited_at.isoformat(),
                "message": "Message updated successfully.",
            }
        )

    messages.success(
        request,
        "Message updated successfully.",
    )

    return redirect(group_chat_url(group.id))


# ============================================================
# 17. DELETE GROUP CHAT MESSAGE
# ============================================================

@login_required
@require_POST
def delete_group_message(request, group_id, message_id):
    """
    Soft-delete a chat message.

    The database record remains available for audit purposes,
    but its content and attachment are no longer displayed.
    """

    group = get_object_or_404(
        ProjectGroup,
        id=group_id,
    )

    if not is_group_member(group, request.user):
        return HttpResponseForbidden(
            "You must be a group member to delete messages."
        )

    chat_message = get_object_or_404(
        GroupChatMessage,
        id=message_id,
        group=group,
    )

    if chat_message.sender_id != request.user.id:
        return HttpResponseForbidden(
            "You can only delete your own messages."
        )

    with transaction.atomic():

        # Check whether the message has already been deleted.
        if chat_message.deleted_at is None:

            # Record when the message was deleted.
            chat_message.deleted_at = timezone.now()

            # Save only the deletion timestamp.
            chat_message.save(
                update_fields=["deleted_at"],
            )

        message_data = {
            "type": "message_deleted",
            "message_id": chat_message.id,
            "group_id": group.id,
        }

        transaction.on_commit(
            lambda: broadcast_group_event(
                f"group_chat_{group.id}",
                "chat.message",
                message_data,
            )
        )

    if is_ajax_request(request):
        return JsonResponse(
            {
                "success": True,
                "message_id": chat_message.id,
                "message": "Message deleted successfully.",
            }
        )

    messages.success(
        request,
        "Message deleted successfully.",
    )

    return redirect(group_chat_url(group.id))


# ============================================================
# 18. CONNECT GITHUB REPOSITORY
# ============================================================

@login_required
@require_POST
def connect_group_repository(request, group_id):
    """
    Connect a verified public GitHub repository.

    Only the owner of a private development group
    can connect or replace its repository.
    """

    group = get_object_or_404(
        ProjectGroup,
        id=group_id,
    )

    if not group.is_private:
        return HttpResponseForbidden(
            "Repository connections are only available to private groups."
        )

    if not is_group_owner(group, request.user):
        return HttpResponseForbidden(
            "Only the group owner can connect repositories."
        )

    form = GroupRepositoryForm(request.POST)

    if not form.is_valid():

        messages.error(
            request,
            "Enter a valid GitHub repository URL.",
        )

        return redirect(
            "meeting_room",
            group_id=group.id,
        )

    owner = form.cleaned_data["github_owner"]
    repository_name = form.cleaned_data["repository_name"]

    api_url = (
        f"https://api.github.com/repos/"
        f"{quote(owner, safe='')}/"
        f"{quote(repository_name, safe='')}"
    )

    try:
        repository_data = github_request_json(api_url)

    except HTTPError as error:

        if error.code == 404:
            message = "GitHub repository not found or not public."

        elif error.code in (403, 429):
            message = (
                "GitHub is temporarily limiting requests. "
                "Try again later."
            )

        else:
            message = "GitHub could not verify this repository."

        messages.error(request, message)

        return redirect(
            "meeting_room",
            group_id=group.id,
        )

    except (URLError, TimeoutError, ValueError, OSError):

        messages.error(
            request,
            "Unable to contact GitHub. Please try again.",
        )

        return redirect(
            "meeting_room",
            group_id=group.id,
        )

    if repository_data.get("private", True):

        messages.error(
            request,
            "Only public repositories are supported for now.",
        )

        return redirect(
            "meeting_room",
            group_id=group.id,
        )

    verified_owner = repository_data.get(
        "owner",
        {},
    ).get("login")

    verified_name = repository_data.get("name")
    default_branch = repository_data.get("default_branch")

    if not all(
        [
            verified_owner,
            verified_name,
            default_branch,
        ]
    ):

        messages.error(
            request,
            "GitHub returned incomplete repository information.",
        )

        return redirect(
            "meeting_room",
            group_id=group.id,
        )

    with transaction.atomic():

        locked_group = ProjectGroup.objects.select_for_update().get(
            id=group.id,
        )

        # Recheck ownership after the external GitHub request.
        if not is_group_owner(locked_group, request.user):
            return HttpResponseForbidden(
                "You no longer have permission to connect repositories."
            )

        GroupRepository.objects.update_or_create(
            group=locked_group,
            defaults={
                "github_owner": verified_owner,
                "repository_name": verified_name,
                "default_branch": default_branch,
            },
        )

    messages.success(
        request,
        "GitHub repository connected successfully!",
    )

    return redirect(
        "meeting_room",
        group_id=group.id,
    )


# ============================================================
# 19. GITHUB REPOSITORY FILE EXPLORER
# ============================================================

@login_required
@require_GET
def group_repository_files(request, group_id):
    """Retrieve the connected repository's file tree."""

    group = get_object_or_404(
        ProjectGroup,
        id=group_id,
    )

    if not group.is_private:
        return HttpResponseForbidden(
            "Repository files are only available to private groups."
        )

    if not is_group_member(group, request.user):
        return HttpResponseForbidden(
            "You must belong to this group to view repository files."
        )

    repository = GroupRepository.objects.filter(
        group=group,
    ).first()

    if repository is None:
        return JsonResponse(
            {"error": "No GitHub repository connected."},
            status=404,
        )

    owner = quote(repository.github_owner, safe="")
    repo_name = quote(repository.repository_name, safe="")
    branch = quote(repository.default_branch, safe="")

    api_url = (
        f"https://api.github.com/repos/{owner}/{repo_name}"
        f"/git/trees/{branch}?recursive=1"
    )

    try:
        repository_data = github_request_json(api_url)

    except HTTPError as error:

        if error.code == 404:
            message = "Repository or branch not found."

        elif error.code in (403, 429):
            message = "GitHub request limit reached. Try again later."

        else:
            message = "Unable to retrieve repository files."

        return JsonResponse(
            {"error": message},
            status=502,
        )

    except (URLError, TimeoutError, ValueError, OSError):

        return JsonResponse(
            {"error": "Unable to contact GitHub."},
            status=502,
        )

    if repository_data.get("truncated"):

        return JsonResponse(
            {
                "error": (
                    "This repository is too large to load completely. "
                    "Folder-by-folder loading will be added later."
                )
            },
            status=422,
        )

    files = []

    for item in repository_data.get("tree", []):

        if item.get("type") not in ("blob", "tree"):
            continue

        files.append(
            {
                "name": item["path"].split("/")[-1],
                "path": item["path"],
                "type": (
                    "folder"
                    if item["type"] == "tree"
                    else "file"
                ),
            }
        )

    return JsonResponse(
        {
            "repository": (
                f"{repository.github_owner}/"
                f"{repository.repository_name}"
            ),
            "branch": repository.default_branch,
            "files": files,
        }
    )


# ============================================================
# 20. GITHUB REPOSITORY FILE CONTENT
# ============================================================

@login_required
@require_GET
def group_repository_file_content(request, group_id):
    """Retrieve a text file from the connected GitHub repository."""

    group = get_object_or_404(
        ProjectGroup,
        id=group_id,
    )

    if not group.is_private:
        return HttpResponseForbidden(
            "Repository files are only available to private groups."
        )

    if not is_group_member(group, request.user):
        return HttpResponseForbidden(
            "You must belong to this group to view repository files."
        )

    repository = GroupRepository.objects.filter(
        group=group,
    ).first()

    if repository is None:
        return JsonResponse(
            {"error": "No GitHub repository connected."},
            status=404,
        )

    file_path = request.GET.get("path", "")

    if (
        not file_path
        or file_path.startswith("/")
        or "\\" in file_path
        or any(
            part in ("", ".", "..")
            for part in file_path.split("/")
        )
    ):
        return JsonResponse(
            {"error": "Invalid repository file path."},
            status=400,
        )

    owner = quote(repository.github_owner, safe="")
    repo_name = quote(repository.repository_name, safe="")
    branch = quote(repository.default_branch, safe="")

    encoded_path = "/".join(
        quote(part, safe="")
        for part in file_path.split("/")
    )

    api_url = (
        f"https://api.github.com/repos/{owner}/{repo_name}"
        f"/contents/{encoded_path}?ref={branch}"
    )

    github_request = Request(
        api_url,
        headers={
            "Accept": "application/vnd.github.raw+json",
            "User-Agent": "CodeView",
        },
    )

    try:

        with urlopen(github_request, timeout=10) as response:

            # Limit previews to 1 MiB.
            raw_content = response.read(
                1024 * 1024 + 1
            )

    except HTTPError as error:

        if error.code == 404:
            message = "File not found in the connected repository."

        elif error.code in (403, 429):
            message = "GitHub request limit reached. Try again later."

        else:
            message = "Unable to retrieve this file."

        return JsonResponse(
            {"error": message},
            status=502,
        )

    except (URLError, TimeoutError, OSError):

        return JsonResponse(
            {"error": "Unable to contact GitHub."},
            status=502,
        )

    if len(raw_content) > 1024 * 1024:
        return JsonResponse(
            {"error": "This file is too large to preview."},
            status=413,
        )

    try:
        content = raw_content.decode("utf-8")

    except UnicodeDecodeError:

        return JsonResponse(
            {
                "error": (
                    "This file is not supported as a text preview."
                )
            },
            status=415,
        )

    return JsonResponse(
        {
            "path": file_path,
            "content": content,
            "branch": repository.default_branch,
        }
    )

@login_required
def download_group_attachment(request, group_id, message_id):
    """
    Securely serve group chat attachments.

    Security rules:
    1. The developer must be logged in.
    2. The developer must belong to the group.
    3. The message must belong to that group.
    4. Deleted messages cannot expose attachments.

    File behavior:
    - Voice notes play inside the browser.
    - Other attachments are downloaded.
    """

    # Find the requested group.
    group = get_object_or_404(
        ProjectGroup,
        id=group_id,
    )

    # Only group members can access attachments.
    if not is_group_member(group, request.user):
        raise Http404("Attachment not found.")

    # Find the message inside the requested group.
    chat_message = get_object_or_404(
        GroupChatMessage,
        id=message_id,
        group=group,
    )

    # Deleted messages must not expose attachments.
    if chat_message.deleted_at is not None:
        raise Http404("Attachment not found.")

    # Confirm that the message contains a file.
    if not chat_message.attachment:
        raise Http404("This message has no attachment.")

    # Get the original filename.
    filename = chat_message.attachment.name.rsplit("/", 1)[-1]

    # Identify whether this attachment is a voice note.
    is_voice_note = chat_message.message_type == "voice"

    # Supported browser audio formats.
    audio_content_types = {
        ".mp3": "audio/mpeg",
        ".wav": "audio/wav",
        ".ogg": "audio/ogg",
        ".webm": "audio/webm",
        ".m4a": "audio/mp4",
    }

    # Get the file extension.
    extension = (
        "." + filename.rsplit(".", 1)[-1].lower()
        if "." in filename
        else ""
    )

    # Open the private attachment.
    try:
        attachment_file = chat_message.attachment.open("rb")

    except (FileNotFoundError, OSError):
        raise Http404("Attachment file not found.")

    # Voice notes should play directly inside the browser.
    if is_voice_note:

        # Only allow supported audio extensions for inline playback.
        if extension not in audio_content_types:
            attachment_file.close()
            raise Http404("Unsupported voice note format.")

        response = FileResponse(
            attachment_file,
            as_attachment=False,
            content_type=audio_content_types[extension],
        )

    else:

        # Other attachments should download normally.
        response = FileResponse(
            attachment_file,
            as_attachment=True,
            filename=filename,
            content_type="application/octet-stream",
        )

    # Prevent browsers and shared caches from storing private files.
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"

    return response

    # ============================================================
# GROUP CHAT MESSAGE REACTIONS
# ============================================================

@login_required
@require_POST
def toggle_group_message_reaction(request, group_id, message_id):
    """
    Add, change, or remove a developer's reaction.

    Rules:
        1. Only authenticated group members can react.
        2. Deleted messages cannot receive reactions.
        3. One developer can have one reaction per message.
        4. Clicking the same emoji removes the reaction.
        5. Clicking another emoji changes the reaction.
        6. Changes are broadcast through WebSockets.
    """

    # ========================================================
    # 1. CHECK GROUP MEMBERSHIP
    # ========================================================

    group = get_object_or_404(
        ProjectGroup,
        id=group_id,
    )

    if not is_group_member(group, request.user):

        return HttpResponseForbidden(
            "You must be a group member to react to messages."
        )

    # ========================================================
    # 2. FIND THE MESSAGE
    # ========================================================

    # The message must belong to this group and not be deleted.
    chat_message = get_object_or_404(
        GroupChatMessage,
        id=message_id,
        group=group,
        deleted_at__isnull=True,
    )

    # ========================================================
    # 3. READ THE SELECTED EMOJI
    # ========================================================

    # The browser will send JSON containing the emoji.
    try:

        data = json.loads(request.body)

    except (json.JSONDecodeError, UnicodeDecodeError):

        return JsonResponse(
            {
                "success": False,
                "error": "Invalid JSON data.",
            },
            status=400,
        )

    emoji = data.get("emoji")

    # Only allow supported emoji reactions.
    allowed_emojis = {
        choice[0]
        for choice in GroupMessageReaction.REACTION_CHOICES
    }

    if not isinstance(emoji, str) or emoji not in allowed_emojis:

        return JsonResponse(
            {
                "success": False,
                "error": "Unsupported emoji reaction.",
            },
            status=400,
        )

    # ========================================================
    # 4. ADD, CHANGE, OR REMOVE REACTION
    # ========================================================

    with transaction.atomic():

        # Serialize reaction changes for this message.
        # This also prevents concurrent requests from the same
        # developer from creating conflicting reactions.
        chat_message = (
            GroupChatMessage.objects
            .select_for_update()
            .get(
                pk=chat_message.pk,
                group=group,
                deleted_at__isnull=True,
            )
        )

        # Find the developer's existing reaction.
        existing_reaction = (
            GroupMessageReaction.objects
            .filter(
                message=chat_message,
                user=request.user,
            )
            .first()
        )

        if existing_reaction is None:

            # No previous reaction: create one.
            GroupMessageReaction.objects.create(
                message=chat_message,
                user=request.user,
                emoji=emoji,
            )

            action = "added"

        elif existing_reaction.emoji == emoji:

            # Same emoji clicked again: remove it.
            existing_reaction.delete()

            action = "removed"

        else:

            # Different emoji: replace the previous reaction.
            existing_reaction.emoji = emoji

            existing_reaction.save(
                update_fields=["emoji"],
            )

            action = "changed"

        # ====================================================
        # 5. COUNT ALL REACTIONS
        # ====================================================

        reaction_counts = (
            GroupMessageReaction.objects
            .filter(message=chat_message)
            .values("emoji")
            .annotate(count=Count("id"))
            .order_by("emoji")
        )

        # Example: {"❤️": 3, "😂": 2}
        reactions = {
            item["emoji"]: item["count"]
            for item in reaction_counts
        }

        # Get the developer's current reaction.
        current_reaction = (
            GroupMessageReaction.objects
            .filter(
                message=chat_message,
                user=request.user,
            )
            .values_list("emoji", flat=True)
            .first()
        )

        # ====================================================
        # 6. PREPARE WEBSOCKET EVENT
        # ====================================================

        message_data = {
            "type": "message_reaction",
            "group_id": group.id,
            "message_id": chat_message.id,
            "user_id": request.user.id,
            "emoji": emoji,
            "action": action,
            "reactions": reactions,
        }

        # Broadcast only after the transaction commits.
        transaction.on_commit(
            lambda: broadcast_group_event(
                f"group_chat_{group.id}",
                "chat.reaction",
                message_data,
            )
        )

    # ========================================================
    # 7. RETURN RESULT TO THE BROWSER
    # ========================================================

    return JsonResponse(
        {
            "success": True,
            "message_id": chat_message.id,
            "action": action,
            "reactions": reactions,
            "current_reaction": current_reaction,
        }
    )