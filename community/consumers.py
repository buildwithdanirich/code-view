"""
CodeView — WebSocket Consumers.

Handles:
1. Real-time group chat.
2. Real-time group discussions.
"""

# Run asynchronous background tasks.
import asyncio

# Django Channels WebSocket consumer.
from channels.generic.websocket import AsyncJsonWebsocketConsumer

# Run synchronous Django database operations safely.
from channels.db import database_sync_to_async

# CodeView group models.
from .models import ProjectGroup, GroupMember


# ============================================================
# 1. GROUP CHAT CONSUMER
# ============================================================

class GroupChatConsumer(AsyncJsonWebsocketConsumer):
    """Manage real-time WebSocket connections for group chat."""

    async def connect(self):
        """Connect a developer to their group's chat."""

        # Get the logged-in developer.
        self.user = self.scope["user"]

        # Get the group ID from the WebSocket URL.
        self.group_id = self.scope["url_route"]["kwargs"]["group_id"]

        # Create a unique channel-layer group name.
        self.room_group_name = f"group_chat_{self.group_id}"

        # Reject developers who are not logged in.
        if not self.user.is_authenticated:
            await self.close(code=4401)
            return

        # Check whether the developer belongs to this group.
        is_member = await self.check_group_membership()

        if not is_member:
            await self.close(code=4403)
            return

        # Add this connection to the group's broadcast channel.
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name,
        )
        
        # Accept the authenticated group chat connection.
        await self.accept()

    async def disconnect(self, close_code):
        """Remove the developer from the group's channel."""

        # Only remove connections that joined the channel.
        if hasattr(self, "room_group_name"):
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name,
            )

    async def chat_message(self, event):
        """Send a message event to the developer's browser."""

        await self.send_json(event["data"])

    # ============================================================
    # REAL-TIME MESSAGE REACTIONS
    # ============================================================

    async def chat_reaction(self, event):
        """
        Send message reaction updates to connected developers.

        Example:
            Developer A reacts ❤️ to a message.
            The backend broadcasts the updated reactions.
            Every connected developer sees the change.
        """

        # Forward the reaction update to the browser.
        await self.send_json(event["data"])
        
    @database_sync_to_async
    def check_group_membership(self):
        """Check group membership using Django's database."""

        # Find the requested group.
        group = ProjectGroup.objects.filter(
            id=self.group_id
        ).first()

        # Reject groups that do not exist.
        if group is None:
            return False

        # Use CodeView's existing membership helper.
        from .views import is_group_member

        return is_group_member(group, self.user)


# ============================================================
# 2. GROUP DISCUSSION CONSUMER
# ============================================================

class GroupDiscussionConsumer(AsyncJsonWebsocketConsumer):
    """Send real-time discussion updates to group members."""

    async def connect(self):
        """Connect a developer to discussion updates."""

        # Get the logged-in developer.
        self.user = self.scope["user"]

        # Get the group ID from the WebSocket URL.
        self.group_id = self.scope["url_route"]["kwargs"]["group_id"]

        # Create a separate channel group for discussions.
        self.room_group_name = f"group_discussions_{self.group_id}"

        # Reject developers who are not logged in.
        if not self.user.is_authenticated:
            await self.close(code=4401)
            return

        # Check whether the developer belongs to the group.
        is_member = await self.check_group_membership()

        if not is_member:
            await self.close(code=4403)
            return

        # Join the discussion broadcast group.
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name,
        )

        # Accept the WebSocket connection.
        await self.accept()

    async def disconnect(self, close_code):
        """Disconnect from discussion updates."""

        # Remove the connection from the discussion group.
        if hasattr(self, "room_group_name"):
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name,
            )

    async def discussion_like(self, event):
        """Send the updated discussion like count."""

        await self.send_json(event["data"])

    async def discussion_comment(self, event):
        """Send new comments to connected group members."""

        await self.send_json(event["data"])

    @database_sync_to_async
    def check_group_membership(self):
        """Check whether the developer belongs to the group."""

        # Check approved membership.
        is_member = GroupMember.objects.filter(
            group_id=self.group_id,
            user=self.user,
        ).exists()

        # Allow approved members.
        if is_member:
            return True

        # Also allow the group owner.
        return ProjectGroup.objects.filter(
            id=self.group_id,
            owner_id=self.user.pk,
        ).exists()


