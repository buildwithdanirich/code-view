"""
CodeView — WebSocket URL Routing.

Connect WebSocket URLs to Django Channels consumers.
"""

from django.urls import re_path

from . import consumers


# ============================================================
# WEBSOCKET ROUTES
# ============================================================

websocket_urlpatterns = [

    # Real-time group chat.
    re_path(
        r"^ws/groups/(?P<group_id>\d+)/chat/$",
        consumers.GroupChatConsumer.as_asgi(),
    ),

    # Real-time discussion likes, comments, and replies.
    re_path(
        r"^ws/groups/(?P<group_id>\d+)/discussions/$",
        consumers.GroupDiscussionConsumer.as_asgi(),
    ),

]