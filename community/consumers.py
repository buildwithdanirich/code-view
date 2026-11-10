"""
CodeView — WebSocket Consumers.

Handles:
1. Real-time group chat.
2. Real-time group discussions.
3. Owner-only repository connection notifications.
4. Member-only repository decision notifications.
5. Group-wide repository update notifications.
"""

# Run asynchronous background tasks.
import asyncio

# Django Channels WebSocket consumer.
from channels.generic.websocket import AsyncJsonWebsocketConsumer

# Run synchronous Django database operations safely.
from channels.db import database_sync_to_async

# CodeView group models.
from .models import ProjectGroup, GroupMember


class MembershipRevocationMixin:
    """Listen for revocation of this user's specific group membership."""

    async def subscribe_to_revocations(self):
        # User identity comes from the authenticated WebSocket scope.
        self.revocation_group_name = (
            f"group_membership_access_{self.group_id}_{self.user.pk}"
        )
        await self.channel_layer.group_add(
            self.revocation_group_name,
            self.channel_name,
        )
        self.joined_revocation_group = True

    async def unsubscribe_from_revocations(self):
        if getattr(self, "joined_revocation_group", False):
            await self.channel_layer.group_discard(
                self.revocation_group_name,
                self.channel_name,
            )
            self.joined_revocation_group = False

    async def membership_revoked(self, event):
        """Close only sockets created under the revoked membership generation."""
        if str(event.get("group_id")) != str(self.group_id):
            return
        if str(event.get("user_id")) != str(self.user.pk):
            return

        # Owners have an ownership generation, not a member generation.
        identity = getattr(self, "access_identity", None)
        if identity is not None:
            generation = identity[1] if identity[0] == "member" else None
        else:
            generation = getattr(self, "membership_generation", None)

        if generation is not None and str(generation) == str(
            event.get("membership_generation")
        ):
            await self.close(code=4403)


# ============================================================
# 1. GROUP CHAT CONSUMER
# ============================================================

class GroupChatConsumer(MembershipRevocationMixin, AsyncJsonWebsocketConsumer):
    """Manage real-time WebSocket connections for group chat."""

    async def connect(self):
        """Connect only developers with current group access."""
        self.user = self.scope["user"]
        self.group_id = self.scope["url_route"]["kwargs"]["group_id"]
        self.room_group_name = f"group_chat_{self.group_id}"
        self.joined_group = False

        if not self.user.is_authenticated:
            await self.close(code=4401)
            return

        # Remember the exact ownership or membership period.
        self.access_identity = await self.get_access_identity()
        if self.access_identity is None:
            await self.close(code=4403)
            return

        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name,
        )
        self.joined_group = True

        await self.subscribe_to_revocations()

        # Membership may change while the socket is connecting.
        if not await self.has_current_access():
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name,
            )
            self.joined_group = False
            await self.unsubscribe_from_revocations()
            await self.close(code=4403)
            return

        await self.accept()

    async def disconnect(self, close_code):
        await self.unsubscribe_from_revocations()
        """Unsubscribe a connection that joined the broadcast group."""
        if getattr(self, "joined_group", False):
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name,
            )
            self.joined_group = False

    async def chat_message(self, event):
        """Deliver messages only while the original access is valid."""
        if not await self.has_current_access():
            await self.close(code=4403)
            return
        await self.send_json(event["data"])

    async def chat_reaction(self, event):
        """Deliver reactions only while the original access is valid."""
        if not await self.has_current_access():
            await self.close(code=4403)
            return
        await self.send_json(event["data"])

    @database_sync_to_async
    def get_access_identity(self):
        """Get the current owner/member generation for this group."""
        group = ProjectGroup.objects.filter(id=self.group_id).first()
        if group is None:
            return None

        if group.owner_id == self.user.pk:
            return ("owner", group.owner_membership_generation)

        membership = GroupMember.objects.filter(
            group_id=self.group_id,
            user_id=self.user.pk,
        ).first()
        if membership is None:
            return None
        return ("member", membership.membership_generation)

    async def has_current_access(self):
        """Prevent removed or rejoined members using stale sockets."""
        current_identity = await self.get_access_identity()
        return (
            current_identity is not None
            and current_identity == self.access_identity
        )


# ============================================================
# 2. GROUP DISCUSSION CONSUMER
# ============================================================

class GroupDiscussionConsumer(MembershipRevocationMixin, AsyncJsonWebsocketConsumer):
    """Send real-time discussion updates to authorized group members."""

    async def connect(self):
        """Connect only developers with current group access."""
        self.user = self.scope["user"]
        self.group_id = self.scope["url_route"]["kwargs"]["group_id"]
        self.room_group_name = f"group_discussions_{self.group_id}"
        self.joined_group = False

        if not self.user.is_authenticated:
            await self.close(code=4401)
            return

        self.access_identity = await self.get_access_identity()
        if self.access_identity is None:
            await self.close(code=4403)
            return

        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name,
        )
        self.joined_group = True

        await self.subscribe_to_revocations()

        # Recheck after subscribing to avoid a membership race.
        if not await self.has_current_access():
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name,
            )
            self.joined_group = False
            await self.unsubscribe_from_revocations()
            await self.close(code=4403)
            return

        await self.accept()

    async def disconnect(self, close_code):
        await self.unsubscribe_from_revocations()
        """Unsubscribe a connection that joined the broadcast group."""
        if getattr(self, "joined_group", False):
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name,
            )
            self.joined_group = False

    async def discussion_like(self, event):
        """Deliver likes only while the original access is valid."""
        if not await self.has_current_access():
            await self.close(code=4403)
            return
        await self.send_json(event["data"])

    async def discussion_comment(self, event):
        """Deliver comments only while the original access is valid."""
        if not await self.has_current_access():
            await self.close(code=4403)
            return
        await self.send_json(event["data"])

    @database_sync_to_async
    def get_access_identity(self):
        """Get the current owner/member generation for this group."""
        group = ProjectGroup.objects.filter(id=self.group_id).first()
        if group is None:
            return None

        if group.owner_id == self.user.pk:
            return ("owner", group.owner_membership_generation)

        membership = GroupMember.objects.filter(
            group_id=self.group_id,
            user_id=self.user.pk,
        ).first()
        if membership is None:
            return None
        return ("member", membership.membership_generation)

    async def has_current_access(self):
        """Prevent removed or rejoined members using stale sockets."""
        current_identity = await self.get_access_identity()
        return (
            current_identity is not None
            and current_identity == self.access_identity
        )


# ============================================================
# 3. OWNER-ONLY REPOSITORY NOTIFICATION CONSUMER
# ============================================================

class RepositoryNotificationConsumer(MembershipRevocationMixin, AsyncJsonWebsocketConsumer):
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
        await self.unsubscribe_from_revocations()
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

class RepositoryMemberNotificationConsumer(MembershipRevocationMixin, AsyncJsonWebsocketConsumer):
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

        await self.subscribe_to_revocations()

        # Recheck membership in case it changed while connecting.
        if not await self.is_current_member():
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name,
            )

            self.joined_notification_group = False

            await self.unsubscribe_from_revocations()
            await self.close(code=4403)
            return

        await self.accept()

    async def disconnect(self, close_code):
        await self.unsubscribe_from_revocations()
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

# ============================================================
# 5. GROUP-WIDE REPOSITORY UPDATE CONSUMER
# ============================================================

class GroupRepositoryUpdateConsumer(MembershipRevocationMixin, AsyncJsonWebsocketConsumer):
    """
    Notify authorized private-group developers when the
    connected GitHub repository changes.

    This consumer does not send GitHub credentials or
    repository contents to the browser.
    """

    async def connect(self):
        """Authenticate the developer and verify group access."""

        # Identify the logged-in developer.
        self.user = self.scope["user"]

        # Identify the group from the WebSocket URL.
        self.group_id = self.scope["url_route"]["kwargs"]["group_id"]

        # Track whether this connection joined the channel.
        self.joined_repository_group = False

        # Reject anonymous connections.
        if not self.user.is_authenticated:
            await self.close(code=4401)
            return

        # Capture the developer's current access identity.
        access_identity = await self.get_access_identity()

        if access_identity is None:
            await self.close(code=4403)
            return

        self.access_identity = access_identity

        # Create a separate broadcast group for repository updates.
        self.room_group_name = (
            f"group_repository_updates_{self.group_id}"
        )

        # Subscribe the developer to repository-change events.
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name,
        )

        self.joined_repository_group = True

        await self.subscribe_to_revocations()

        # Recheck access after joining to reduce the chance
        # of accepting a connection after membership changes.
        if not await self.has_current_access():

            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name,
            )

            self.joined_repository_group = False

            await self.close(code=4403)
            return

        # Accept the authorized connection.
        await self.accept()

    async def disconnect(self, close_code):
        await self.unsubscribe_from_revocations()
        """Remove the developer from the repository update channel."""

        if getattr(self, "joined_repository_group", False):

            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name,
            )

            self.joined_repository_group = False

    async def repository_updated(self, event):
        """
        Handle a repository.updated event.

        Django Channels maps:
            repository.updated

        to:
            repository_updated()
        """

        # Verify access again before delivering the event.
        if not await self.has_current_access():

            await self.close(code=4403)
            return

        data = event.get("data", {})

        # Only forward the supported event.
        if data.get("type") != "repository_updated":
            return

        # Ensure the event belongs to this group.
        if str(data.get("group_id")) != str(self.group_id):
            return

        # Send only a minimal notification.
        await self.send_json({
            "type": "repository_updated",
            "group_id": self.group_id,
        })

    @database_sync_to_async
    def get_access_identity(self):
        """
        Identify the developer's current authorization period.

        Owners use the ownership generation.
        Members use the membership generation.

        This prevents an old connection from becoming valid
        again after a developer leaves and rejoins.
        """

        # Only private development groups are supported.
        group = ProjectGroup.objects.filter(
            id=self.group_id,
            is_private=True,
        ).first()

        if group is None:
            return None

        # The group owner is authorized.
        if group.owner_id == self.user.pk:

            return (
                "owner",
                group.owner_membership_generation,
            )

        # Other developers must have an active membership.
        membership = GroupMember.objects.filter(
            group_id=self.group_id,
            user_id=self.user.pk,
        ).first()

        if membership is None:
            return None

        return (
            "member",
            membership.membership_generation,
        )

    async def has_current_access(self):
        """
        Check whether the developer still has access
        under the same ownership or membership generation.
        """

        current_identity = await self.get_access_identity()

        return (
            current_identity is not None
            and current_identity == self.access_identity
        )

# ============================================================
# 6. PRIVATE GROUP MEETING NOTIFICATION CONSUMER
# ============================================================

class GroupMeetingNotificationConsumer(
    MembershipRevocationMixin,
    AsyncJsonWebsocketConsumer,
):
    """Deliver meeting lifecycle events to current private-group members."""

    async def connect(self):
        self.user = self.scope["user"]
        self.group_id = self.scope["url_route"]["kwargs"]["group_id"]
        self.room_group_name = f"group_meeting_notifications_{self.group_id}"
        self.joined_group = False
        self.joined_revocation_group = False

        if not self.user.is_authenticated:
            await self.close(code=4401)
            return

        # Capture the exact ownership/membership generation at connection time.
        self.access_identity = await self.get_access_identity()
        if self.access_identity is None:
            await self.close(code=4403)
            return

        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name,
        )
        self.joined_group = True
        await self.subscribe_to_revocations()

        # Recheck after subscribing to close the connection-time race window.
        if not await self.has_current_access():
            await self.disconnect(4403)
            await self.close(code=4403)
            return

        await self.accept()

    async def disconnect(self, close_code):
        await self.unsubscribe_from_revocations()
        if getattr(self, "joined_group", False):
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name,
            )
            self.joined_group = False

    async def meeting_notification(self, event):
        """Forward only valid meeting events after checking current access."""
        if not await self.has_current_access():
            await self.close(code=4403)
            return

        data = event.get("data", {})
        if not isinstance(data, dict):
            return
        if data.get("type") not in ("meeting_started", "meeting_ended"):
            return
        if str(data.get("group_id")) != str(self.group_id):
            return

        # Never forward a LiveKit access token or API credentials.
        safe_data = {
            "type": data["type"],
            "group_id": self.group_id,
            "meeting_id": data.get("meeting_id"),
        }
        if data["type"] == "meeting_started":
            safe_data["started_by"] = data.get("started_by")
            safe_data["meeting_url"] = data.get("meeting_url")

        await self.send_json(safe_data)

    @database_sync_to_async
    def get_access_identity(self):
        """Authorize only current members of private development groups."""
        group = ProjectGroup.objects.filter(
            pk=self.group_id,
            is_private=True,
        ).first()
        if group is None:
            return None
        if group.owner_id == self.user.pk:
            return ("owner", group.owner_membership_generation)

        membership = GroupMember.objects.filter(
            group_id=self.group_id,
            user_id=self.user.pk,
        ).first()
        if membership is None:
            return None
        return ("member", membership.membership_generation)

    async def has_current_access(self):
        return (
            self.access_identity is not None
            and await self.get_access_identity() == self.access_identity
        )