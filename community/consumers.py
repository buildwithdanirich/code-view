"""
CodeView — WebSocket Consumers.

Handles:
1. Real-time group chat.
2. Real-time group discussions.
3. Owner-only repository connection notifications.
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


# ============================================================
# 3. OWNER-ONLY REPOSITORY NOTIFICATION CONSUMER
# ============================================================

class RepositoryNotificationConsumer(AsyncJsonWebsocketConsumer):
    """
    Send repository connection request notifications
    exclusively to the current group owner.
    """

    async def connect(self):
        """Authenticate and authorize the group owner."""

        # Identify the developer from Django's authenticated session.
        self.user = self.scope["user"]

        # Identify the requested group.
        self.group_id = self.scope["url_route"]["kwargs"]["group_id"]

        # Track whether this connection joined the notification group.
        self.joined_notification_group = False

        # Reject unauthenticated users.
        if not self.user.is_authenticated:
            await self.close(code=4401)
            return

        # Verify current ownership and capture its generation.
        owner_generation = await self.get_owner_generation()

        if owner_generation is None:
            await self.close(code=4403)
            return

        # Remember the ownership period for this connection.
        self.owner_generation = owner_generation

        # Create a private notification channel for this group.
        self.room_group_name = (
            f"group_repository_owner_{self.group_id}"
        )

        # Subscribe this WebSocket connection.
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name,
        )

        self.joined_notification_group = True

        # Recheck ownership after joining to reduce the risk
        # of an ownership change during connection setup.
        if not await self.is_current_owner():
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name,
            )

            self.joined_notification_group = False

            await self.close(code=4403)
            return

        # Accept only the authorized owner's connection.
        await self.accept()

    async def disconnect(self, close_code):
        """Remove the owner's WebSocket subscription."""

        if getattr(self, "joined_notification_group", False):
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name,
            )

            self.joined_notification_group = False

    async def repository_notification(self, event):
        """
        Deliver a repository request notification.

        Django Channels maps the event type
        'repository.notification' to this method.
        """

        # Check ownership again before sending the event.
        # This prevents an old owner from receiving new
        # notifications after an ownership change.
        if not await self.is_current_owner():
            await self.close(code=4403)
            return

        # Send only the notification payload to the browser.
        await self.send_json(event["data"])

    @database_sync_to_async
    def get_owner_generation(self):
        """
        Return the current ownership generation only when
        the connected developer owns this private group.
        """

        return (
            ProjectGroup.objects
            .filter(
                id=self.group_id,
                is_private=True,
                owner_id=self.user.pk,
            )
            .values_list(
                "owner_membership_generation",
                flat=True,
            )
            .first()
        )

    async def is_current_owner(self):
        """
        Confirm that the developer still owns the group
        and belongs to the same ownership generation.
        """

        current_generation = await self.get_owner_generation()

        return (
            current_generation is not None
            and current_generation == self.owner_generation
        )

# ============================================================
# 4. MEMBER-ONLY REPOSITORY DECISION NOTIFICATIONS
# ============================================================

class RepositoryMemberNotificationConsumer(AsyncJsonWebsocketConsumer):
    """
    Notify an individual group member when the owner
    approves or rejects their repository connection request.

    Each connection belongs to one user and one group.
    """

    async def connect(self):
        """Verify membership before accepting the connection."""

        # Get the logged-in user from Django's session.
        self.user = self.scope["user"]

        # Get the group ID from the WebSocket URL.
        self.group_id = self.scope["url_route"]["kwargs"]["group_id"]

        self.joined_notification_group = False

        # Only authenticated developers can connect.
        if not self.user.is_authenticated:
            await self.close(code=4401)
            return

        # Capture the current membership generation.
        membership_generation = await self.get_membership_generation()

        if membership_generation is None:
            await self.close(code=4403)
            return

        self.membership_generation = membership_generation

        # Give each member their own notification channel.
        # Other members cannot subscribe to this channel
        # because the user ID comes from the authenticated session.
        self.room_group_name = (
            f"group_repository_member_{self.group_id}_{self.user.pk}"
        )

        # Subscribe this connection.
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name,
        )

        self.joined_notification_group = True

        # Recheck membership in case it changed while connecting.
        if not await self.is_current_member():
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name,
            )

            self.joined_notification_group = False

            await self.close(code=4403)
            return

        await self.accept()

    async def disconnect(self, close_code):
        """Remove this member's notification subscription."""

        if getattr(self, "joined_notification_group", False):
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name,
            )

            self.joined_notification_group = False

    async def repository_decision(self, event):
        """
        Handle a repository approval or rejection event.

        Channels maps 'repository.decision' to this method.
        """

        # Prevent old membership sessions from receiving
        # notifications after a member leaves and rejoins.
        if not await self.is_current_member():
            await self.close(code=4403)
            return

        data = event.get("data", {})

        # Only forward supported decision events.
        if data.get("type") not in (
            "repository_request_approved",
            "repository_request_rejected",
        ):
            return

        # Ensure the notification belongs to this exact
        # membership period.
        if (
            event.get("membership_generation")
            != self.membership_generation
        ):
            return

        # Send the event to the member's browser.
        await self.send_json(data)

    @database_sync_to_async
    def get_membership_generation(self):
        """Retrieve the member's current membership generation."""

        # The group must still be private.
        if not ProjectGroup.objects.filter(
            id=self.group_id,
            is_private=True,
        ).exists():
            return None

        # Return the current membership generation.
        return (
            GroupMember.objects
            .filter(
                group_id=self.group_id,
                user_id=self.user.pk,
            )
            .values_list(
                "membership_generation",
                flat=True,
            )
            .first()
        )

    async def is_current_member(self):
        """Verify that this connection still belongs to the member."""

        current_generation = await self.get_membership_generation()

        return (
            current_generation is not None
            and current_generation == self.membership_generation
        )