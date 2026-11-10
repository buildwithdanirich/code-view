"""
CodeView — WebSocket URL Routing.

Connects WebSocket URLs to their Django Channels consumers.

Features:
1. Real-time group chat.
2. Real-time group discussions.
3. Owner repository request notifications.
4. Member repository approval/rejection notifications.
5. Group-wide repository synchronization.
"""

from django.urls import re_path

from .consumers import (
    GroupChatConsumer,
    GroupDiscussionConsumer,
    RepositoryNotificationConsumer,
    RepositoryMemberNotificationConsumer,
    GroupRepositoryUpdateConsumer,
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
    # 2. GROUP DISCUSSIONS
    # ========================================================

    re_path(
        r"^ws/groups/(?P<group_id>\d+)/discussions/$",
        GroupDiscussionConsumer.as_asgi(),
    ),

    # ========================================================
    # 3. OWNER REPOSITORY REQUEST NOTIFICATIONS
    # ========================================================

    re_path(
        r"^ws/groups/(?P<group_id>\d+)/repository-notifications/$",
        RepositoryNotificationConsumer.as_asgi(),
    ),

    # ========================================================
    # 4. MEMBER REPOSITORY APPROVAL/REJECTION NOTIFICATIONS
    # ========================================================

    re_path(
        r"^ws/groups/(?P<group_id>\d+)/repository-member-notifications/$",
        RepositoryMemberNotificationConsumer.as_asgi(),
    ),

    # ========================================================
    # 5. GROUP-WIDE REPOSITORY UPDATES
    # ========================================================

    re_path(
        r"^ws/groups/(?P<group_id>\d+)/repository-updates/$",
        GroupRepositoryUpdateConsumer.as_asgi(),
    ),

]