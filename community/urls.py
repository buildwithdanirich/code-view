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
- Repository connection approval requests
- Meeting rooms
"""

from django.urls import path

# Existing group functionality.
from . import views

# Private-group invitation functionality.
from . import invitation_views

# GitHub repository connection approval functionality.
from . import repository_request_views


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

    path(
        "<int:group_id>/invitations/send/",
        invitation_views.send_invitation_view,
        name="send_group_invitation",
    ),

    path(
        "invitations/received/",
        invitation_views.received_invitations_view,
        name="received_group_invitations",
    ),

    path(
        "invitations/<int:invitation_id>/accept/",
        invitation_views.accept_invitation_view,
        name="accept_group_invitation",
    ),

    path(
        "invitations/<int:invitation_id>/decline/",
        invitation_views.decline_invitation_view,
        name="decline_group_invitation",
    ),

    # ========================================================
    # 6. GROUP MEMBERSHIP MANAGEMENT
    # ========================================================

    path(
        "<int:group_id>/members/search/",
        views.search_group_developers,
        name="search_group_developers",
    ),

    path(
        "<int:group_id>/members/<int:member_id>/remove/",
        views.remove_group_member,
        name="remove_group_member",
    ),

    path(
        "<int:group_id>/members/leave/",
        views.leave_group,
        name="leave_group",
    ),

    # ========================================================
    # 7. GROUP DISCUSSIONS
    # ========================================================

    path(
        "<int:group_id>/discussions/create/",
        views.create_discussion,
        name="create_discussion",
    ),

    path(
        "<int:group_id>/discussions/<int:discussion_id>/",
        views.discussion_detail,
        name="discussion_detail",
    ),

    path(
        "<int:group_id>/discussions/<int:discussion_id>/comment/",
        views.add_discussion_comment,
        name="add_discussion_comment",
    ),

    path(
        "<int:group_id>/discussions/<int:discussion_id>/like/",
        views.toggle_discussion_like,
        name="toggle_discussion_like",
    ),

    path(
        "<int:group_id>/discussions/<int:discussion_id>/hide/",
        views.hide_discussion,
        name="hide_discussion",
    ),

    # ========================================================
    # 8. GROUP CHAT
    # ========================================================

    path(
        "<int:group_id>/chat/",
        views.group_chat,
        name="group_chat",
    ),

    path(
        "<int:group_id>/chat/send/",
        views.send_group_message,
        name="send_group_message",
    ),

    path(
        "<int:group_id>/chat/<int:message_id>/edit/",
        views.edit_group_message,
        name="edit_group_message",
    ),

    path(
        "<int:group_id>/chat/<int:message_id>/delete/",
        views.delete_group_message,
        name="delete_group_message",
    ),

    # ========================================================
    # GROUP CHAT MESSAGE REACTIONS
    # ========================================================

    path(
        "<int:group_id>/chat/<int:message_id>/react/",
        views.toggle_group_message_reaction,
        name="toggle_group_message_reaction",
    ),

    # ========================================================
    # SECURE GROUP CHAT ATTACHMENT DOWNLOAD
    # ========================================================

    path(
        "<int:group_id>/chat/<int:message_id>/attachment/",
        views.download_group_attachment,
        name="download_group_attachment",
    ),

    # ========================================================
    # 9. GITHUB REPOSITORY INTEGRATION
    # ========================================================

    path(
        "<int:group_id>/repository/connect/",
        views.connect_group_repository,
        name="connect_group_repository",
    ),

    # Member requests permission to connect a repository.
    path(
        "<int:group_id>/repository/request/",
        repository_request_views.request_repository_connection,
        name="request_repository_connection",
    ),

    # Group owner approves a repository connection request.
    path(
        "<int:group_id>/repository/requests/<int:request_id>/approve/",
        repository_request_views.approve_repository_connection,
        name="approve_repository_connection",
    ),

    # Group owner rejects a repository connection request.
    path(
        "<int:group_id>/repository/requests/<int:request_id>/reject/",
        repository_request_views.reject_repository_connection,
        name="reject_repository_connection",
    ),

    path(
        "<int:group_id>/repository/files/",
        views.group_repository_files,
        name="group_repository_files",
    ),

    path(
        "<int:group_id>/repository/file-content/",
        views.group_repository_file_content,
        name="group_repository_file_content",
    ),

    # ========================================================
    # 10. PRIVATE-GROUP MEETING ROOM
    # ========================================================

    path(
        "<int:group_id>/meeting/",
        views.meeting_room,
        name="meeting_room",
    ),

]