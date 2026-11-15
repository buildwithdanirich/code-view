"""
ColabVerse — WebSocket URL Routing.

Connects WebSocket URLs to their Django Channels consumers.

Features:
1. Real-time group chat.
2. Owner repository request notifications.
3. Member repository approval/rejection notifications.
4. Group-wide repository synchronization.
5. Private-group voice/video meeting notifications.
"""

from django.urls import re_path

from .consumers import (
    GroupChatConsumer,
    RepositoryNotificationConsumer,
    RepositoryMemberNotificationConsumer,
    GroupRepositoryUpdateConsumer,
    GroupMeetingNotificationConsumer,
)


websocket_urlpatterns = [

    # ========================================================
    # 1. GROUP CHAT
    # ========================================================

    re_path(
        r"^ws/groups/(?P<group_id>\d+)/chat/$",
        GroupChatConsumer.as_asgi(),
    ),

    # ========================================================
    # 2. OWNER REPOSITORY REQUEST NOTIFICATIONS
    # ========================================================

    re_path(
        r"^ws/groups/(?P<group_id>\d+)/repository-notifications/$",
        RepositoryNotificationConsumer.as_asgi(),
    ),

    # ========================================================
    # 3. MEMBER REPOSITORY APPROVAL/REJECTION NOTIFICATIONS
    # ========================================================

    re_path(
        r"^ws/groups/(?P<group_id>\d+)/repository-member-notifications/$",
        RepositoryMemberNotificationConsumer.as_asgi(),
    ),

    # ========================================================
    # 4. GROUP-WIDE REPOSITORY UPDATES
    # ========================================================

    re_path(
        r"^ws/groups/(?P<group_id>\d+)/repository-updates/$",
        GroupRepositoryUpdateConsumer.as_asgi(),
    ),

    # ========================================================
    # 5. PRIVATE-GROUP MEETING NOTIFICATIONS
    # ========================================================

    # Only authenticated, authorized private-group members
    # can establish a meeting notification connection.
    #
    # The consumer checks membership before accepting.
    re_path(
        r"^ws/groups/(?P<group_id>\d+)/meetings/notifications/$",
        GroupMeetingNotificationConsumer.as_asgi(),
    ),

]