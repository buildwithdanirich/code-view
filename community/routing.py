"""
CodeView — WebSocket URL Routing.

Connect WebSocket URLs to Django Channels consumers.

Handles:
1. Real-time group chat.
2. Real-time group discussions.
3. Owner-only repository connection notifications.
"""

from django.urls import re_path

from . import consumers


# ============================================================
# WEBSOCKET ROUTES
# ============================================================

websocket_urlpatterns = [

    # ========================================================
    # 1. REAL-TIME GROUP CHAT
    # ========================================================

    re_path(
        r"^ws/groups/(?P<group_id>\d+)/chat/$",
        consumers.GroupChatConsumer.as_asgi(),
    ),

    # ========================================================
    # 2. REAL-TIME GROUP DISCUSSIONS
    # ========================================================

    re_path(
        r"^ws/groups/(?P<group_id>\d+)/discussions/$",
        consumers.GroupDiscussionConsumer.as_asgi(),
    ),

    # ========================================================
    # 3. OWNER-ONLY REPOSITORY NOTIFICATIONS
    # ========================================================

    # Only the current group owner can establish this
    # WebSocket connection.
    #
    # The consumer verifies authentication, group ownership,
    # and ownership generation before accepting connections.

    re_path(
        r"^ws/groups/(?P<group_id>\d+)/repository-notifications/$",
        consumers.RepositoryNotificationConsumer.as_asgi(),
    ),

]