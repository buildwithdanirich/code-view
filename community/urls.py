"""URL routes for CodeView groups, discussions, and chat."""

from django.urls import path

from . import views


urlpatterns = [

    # ========================================================
    # 1. GROUPS DASHBOARD
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
    # 3. JOIN GROUP OR REQUEST MEMBERSHIP
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
    # 5. MEMBERSHIP REQUESTS (ADMINISTRATORS)
    # ========================================================

    # Display pending membership requests.
    path(
        "<int:group_id>/requests/",
        views.membership_requests,
        name="membership_requests",
    ),
    # ========================================================
    # ADD GROUP MEMBER (ADMINISTRATORS)
    # ========================================================

    path(
        "<int:group_id>/members/add/",
        views.add_group_member,
        name="add_group_member",
    ),

    # Approve a developer's membership request.
    path(
        "<int:group_id>/requests/<int:request_id>/approve/",
        views.approve_membership,
        name="approve_membership",
    ),

    # Reject a developer's membership request.
    path(
        "<int:group_id>/requests/<int:request_id>/reject/",
        views.reject_membership,
        name="reject_membership",
    ),

    # ========================================================
    # 6. GROUP MEETING ROOM
    # ========================================================

    path(
        "<int:group_id>/meeting/",
        views.meeting_room,
        name="meeting_room",
    ),

    # ========================================================
    # 8. CREATE GROUP DISCUSSION
    # ========================================================

    # Members can create discussion posts inside their groups.
    path(
        "<int:group_id>/discussions/create/",
        views.create_discussion,
        name="create_discussion",
    ),

    # ========================================================
    # 9. VIEW DISCUSSION AND COMMENTS
    # ========================================================

    # Display a discussion with its comments and replies.
    path(
        "<int:group_id>/discussions/<int:discussion_id>/",
        views.discussion_detail,
        name="discussion_detail",
    ),

    # ========================================================
    # 10. COMMENT OR REPLY TO A COMMENT
    # ========================================================

    # One route handles normal comments and nested replies.
    #
    # For a normal comment:
    #   parent_id is empty.
    #
    # For a reply:
    #   parent_id contains the ID of another comment.
    path(
        "<int:group_id>/discussions/<int:discussion_id>/comment/",
        views.add_discussion_comment,
        name="add_discussion_comment",
    ),

    # ========================================================
    # 11. LIKE OR UNLIKE DISCUSSION
    # ========================================================

    # Clicking Like again removes the developer's existing like.
    path(
        "<int:group_id>/discussions/<int:discussion_id>/like/",
        views.toggle_discussion_like,
        name="toggle_discussion_like",
    ),

    # ========================================================
    # 12. HIDE DISCUSSION
    # ========================================================

    # Hiding a discussion affects only the current developer.
    path(
        "<int:group_id>/discussions/<int:discussion_id>/hide/",
        views.hide_discussion,
        name="hide_discussion",
    ),

    # ========================================================
    # 13. GROUP CHAT ROOM
    # ========================================================

    # Display the group's recent chat messages.
    path(
        "<int:group_id>/chat/",
        views.group_chat,
        name="group_chat",
    ),

    # ========================================================
    # 14. SEND GROUP CHAT MESSAGE
    # ========================================================

    # Accept text, code, voice notes, and file messages.
    #
    # The view validates group membership before saving.
    path(
        "<int:group_id>/chat/send/",
        views.send_group_message,
        name="send_group_message",
    ),

    # ========================================================
    # 15. EDIT GROUP CHAT MESSAGE
    # ========================================================

    # Developers can edit their own text and code messages.
    path(
        "<int:group_id>/chat/<int:message_id>/edit/",
        views.edit_group_message,
        name="edit_group_message",
    ),

    # ========================================================
    # 16. DELETE GROUP CHAT MESSAGE
    # ========================================================

    # Soft-delete a message while preserving conversation replies.
    path(
        "<int:group_id>/chat/<int:message_id>/delete/",
        views.delete_group_message,
        name="delete_group_message",
    ),
    # Search registered developers while typing.
    path(
        "<int:group_id>/members/search/",
        views.search_group_developers,
        name="search_group_developers",
    ),

    # ========================================================
# GROUP MEMBERSHIP MANAGEMENT
# ========================================================

    # Remove a developer from a group.
    path(
        "<int:group_id>/members/<int:member_id>/remove/",
        views.remove_group_member,
        name="remove_group_member",
    ),

    # Promote or demote a group administrator.
    path(
        "<int:group_id>/members/<int:member_id>/role/",
        views.change_group_member_role,
        name="change_group_member_role",
    ),

    # Allow a developer to leave a group.
    path(
        "<int:group_id>/members/leave/",
        views.leave_group,
        name="leave_group",
    ),
    # ============================================================
# GITHUB REPOSITORY CONNECTION
# ============================================================

    path(
        "<int:group_id>/repository/connect/",
        views.connect_group_repository,
        name="connect_group_repository",
    ),
        # Retrieve the connected GitHub repository's file tree.
    path(
        "<int:group_id>/repository/files/",
        views.group_repository_files,
        name="group_repository_files",
    ),
        # Retrieve the source code of a selected GitHub file.
    path(
        "<int:group_id>/repository/file-content/",
        views.group_repository_file_content,
        name="group_repository_file_content",
    ),

]