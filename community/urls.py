"""
URL routes for CodeView groups.

Features:
- Normal chat groups
- Private development groups
- Owner-sent invitations
- Group discussions
- Group chat
- Group membership management
- GitHub repository integration
- Meeting rooms
"""

from django.urls import path

# Existing group functionality.
from . import views

# Private-group invitation functionality.
from . import invitation_views


urlpatterns = [

    # ========================================================
    # 1. GROUP DASHBOARD
    # ========================================================

    path(
        "",
        views.groups,
        name="groups",
    ),

    # ========================================================
    # 2. CREATE GROUP
    # ========================================================

    path(
        "create/",
        views.create_group,
        name="create_group",
    ),

    # ========================================================
    # 3. JOIN NORMAL CHAT GROUP
    # ========================================================

    # Private development groups must use invitations.
    # The join_group view must enforce this restriction.
    path(
        "<int:group_id>/join/",
        views.join_group,
        name="join_group",
    ),

    # ========================================================
    # 4. GROUP DETAILS
    # ========================================================

    path(
        "<int:group_id>/",
        views.group_detail,
        name="group_detail",
    ),

    # ========================================================
    # 5. PRIVATE-GROUP INVITATIONS
    # ========================================================

    # Only the private-group owner can send invitations.
    path(
        "<int:group_id>/invitations/send/",
        invitation_views.send_invitation_view,
        name="send_group_invitation",
    ),

    # Show invitations received by the logged-in developer.
    path(
        "invitations/received/",
        invitation_views.received_invitations_view,
        name="received_group_invitations",
    ),

    # Accept an invitation.
    path(
        "invitations/<int:invitation_id>/accept/",
        invitation_views.accept_invitation_view,
        name="accept_group_invitation",
    ),

    # Decline an invitation.
    path(
        "invitations/<int:invitation_id>/decline/",
        invitation_views.decline_invitation_view,
        name="decline_group_invitation",
    ),

    # ========================================================
    # 6. GROUP MEMBERSHIP MANAGEMENT
    # ========================================================

    # Search registered developers.
    # The view must restrict private-group invitation searches
    # to the group owner.
    path(
        "<int:group_id>/members/search/",
        views.search_group_developers,
        name="search_group_developers",
    ),

    # Only the group owner can remove private-group members.
    path(
        "<int:group_id>/members/<int:member_id>/remove/",
        views.remove_group_member,
        name="remove_group_member",
    ),

    # Allow developers to leave groups.
    path(
        "<int:group_id>/members/leave/",
        views.leave_group,
        name="leave_group",
    ),

    # ========================================================
    # 7. GROUP DISCUSSIONS
    # ========================================================

    # Create a discussion.
    path(
        "<int:group_id>/discussions/create/",
        views.create_discussion,
        name="create_discussion",
    ),

    # View a discussion and its comments.
    path(
        "<int:group_id>/discussions/<int:discussion_id>/",
        views.discussion_detail,
        name="discussion_detail",
    ),

    # Add a comment or reply.
    path(
        "<int:group_id>/discussions/<int:discussion_id>/comment/",
        views.add_discussion_comment,
        name="add_discussion_comment",
    ),

    # Like or unlike a discussion.
    path(
        "<int:group_id>/discussions/<int:discussion_id>/like/",
        views.toggle_discussion_like,
        name="toggle_discussion_like",
    ),

    # Hide a discussion.
    path(
        "<int:group_id>/discussions/<int:discussion_id>/hide/",
        views.hide_discussion,
        name="hide_discussion",
    ),

    # ========================================================
    # 8. GROUP CHAT
    # ========================================================

    # Open the group chat room.
    path(
        "<int:group_id>/chat/",
        views.group_chat,
        name="group_chat",
    ),

    # Send text, code snippets, voice notes, or files.
    path(
        "<int:group_id>/chat/send/",
        views.send_group_message,
        name="send_group_message",
    ),

    # Edit a message.
    path(
        "<int:group_id>/chat/<int:message_id>/edit/",
        views.edit_group_message,
        name="edit_group_message",
    ),

    # Delete a message.
    path(
        "<int:group_id>/chat/<int:message_id>/delete/",
        views.delete_group_message,
        name="delete_group_message",
    ),

        # ========================================================
    # GROUP CHAT MESSAGE REACTIONS
    # ========================================================

    # Add, change, or remove an emoji reaction.
    path(
        "<int:group_id>/chat/<int:message_id>/react/",
        views.toggle_group_message_reaction,
        name="toggle_group_message_reaction",
    ),

        # ========================================================
    # SECURE GROUP CHAT ATTACHMENT DOWNLOAD
    # ========================================================

    # Allow authorized group members to download attachments.
    # The view checks membership before returning the file.
    path(
        "<int:group_id>/chat/<int:message_id>/attachment/",
        views.download_group_attachment,
        name="download_group_attachment",
    ),

    # ========================================================
    # 9. GITHUB REPOSITORY INTEGRATION
    # ========================================================

    # Connect a repository to a private development group.
    path(
        "<int:group_id>/repository/connect/",
        views.connect_group_repository,
        name="connect_group_repository",
    ),

    # Display the repository's files.
    path(
        "<int:group_id>/repository/files/",
        views.group_repository_files,
        name="group_repository_files",
    ),

    # Display the content of a selected repository file.
    path(
        "<int:group_id>/repository/file-content/",
        views.group_repository_file_content,
        name="group_repository_file_content",
    ),

    # ========================================================
    # 10. PRIVATE-GROUP MEETING ROOM
    # ========================================================

    # LiveKit integration will be added later.
    path(
        "<int:group_id>/meeting/",
        views.meeting_room,
        name="meeting_room",
    ),

]