"""
ColabVerse WebSocket Security Tests.

Tests:
1. Anonymous users cannot connect.
2. Outsiders cannot connect.
3. Group owners can connect to authorized endpoints.
4. Accepted members can connect to authorized endpoints.
5. Owner-only notifications reject ordinary members.
6. Removed members lose access to existing connections.
7. Public communities cannot access private development group WebSockets.
"""

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from channels.db import database_sync_to_async

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import TransactionTestCase, override_settings

from community.models import ProjectGroup, GroupMember
from config.asgi import application


User = get_user_model()


# Use an isolated channel layer for these tests.
TEST_CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer",
    }
}


@override_settings(CHANNEL_LAYERS=TEST_CHANNEL_LAYERS)
class WebSocketSecurityTests(TransactionTestCase):
    """Verify authentication and authorization for WebSocket consumers."""

    def setUp(self):
        """Create test developers and a private development group."""

        self.owner = User.objects.create_user(
            username="ws_owner",
            password="TestPassword123!",
        )

        self.member = User.objects.create_user(
            username="ws_member",
            password="TestPassword123!",
        )

        self.outsider = User.objects.create_user(
            username="ws_outsider",
            password="TestPassword123!",
        )

        self.group = ProjectGroup.objects.create(
            name="WebSocket Security Test Group",
            description="Testing private WebSocket permissions.",
            owner=self.owner,
            is_private=True,
            join_policy="invite",
        )

        self.membership = GroupMember.objects.create(
            group=self.group,
            user=self.member,
            role="member",
        )

    def websocket_path(self, endpoint, group_id=None):
        """Build a WebSocket URL for a group."""

        if group_id is None:
            group_id = self.group.pk

        return f"/ws/groups/{group_id}/{endpoint}/"

    async def connect_as(self, user, endpoint, group_id=None):
        """Attempt a WebSocket connection as a specific user."""

        communicator = WebsocketCommunicator(
            application,
            self.websocket_path(endpoint, group_id),
        )

        # Supply the authenticated user to the ASGI scope.
        communicator.scope["user"] = user

        # Supply an allowed Origin header.
        communicator.scope["headers"] = [
            (b"origin", b"http://localhost"),
        ]

        connected, _ = await communicator.connect()

        return communicator, connected

    async def check_connection(
        self,
        user,
        endpoint,
        expected,
        group_id=None,
    ):
        """Verify whether a connection should be accepted."""

        communicator, connected = await self.connect_as(
            user,
            endpoint,
            group_id,
        )

        try:
            self.assertEqual(connected, expected)
        finally:
            await communicator.disconnect()

    def test_anonymous_users_rejected(self):
        """Anonymous visitors cannot access private group sockets."""

        async def run_test():
            endpoints = [
                "chat",
                "repository-notifications",
                "repository-member-notifications",
                "repository-updates",
                "meetings/notifications",
            ]

            for endpoint in endpoints:
                await self.check_connection(
                    AnonymousUser(),
                    endpoint,
                    False,
                )

        async_to_sync(run_test)()

    def test_outsiders_rejected(self):
        """Authenticated outsiders cannot access group sockets."""

        async def run_test():
            endpoints = [
                "chat",
                "repository-notifications",
                "repository-member-notifications",
                "repository-updates",
                "meetings/notifications",
            ]

            for endpoint in endpoints:
                await self.check_connection(
                    self.outsider,
                    endpoint,
                    False,
                )

        async_to_sync(run_test)()

    def test_owner_can_connect(self):
        """The group owner can access owner-authorized sockets."""

        async def run_test():
            endpoints = [
                "chat",
                "repository-notifications",
                "repository-updates",
                "meetings/notifications",
            ]

            for endpoint in endpoints:
                await self.check_connection(
                    self.owner,
                    endpoint,
                    True,
                )

        async_to_sync(run_test)()

    def test_member_can_connect(self):
        """Accepted members can access member-authorized sockets."""

        async def run_test():
            endpoints = [
                "chat",
                "repository-member-notifications",
                "repository-updates",
                "meetings/notifications",
            ]

            for endpoint in endpoints:
                await self.check_connection(
                    self.member,
                    endpoint,
                    True,
                )

        async_to_sync(run_test)()

    def test_member_cannot_access_owner_notifications(self):
        """Ordinary members cannot receive owner-only notifications."""

        async_to_sync(self.check_connection)(
            self.member,
            "repository-notifications",
            False,
        )

    def test_removed_member_loses_chat_access(self):
        """Removing membership invalidates an existing chat socket."""

        async def run_test():

            communicator, connected = await self.connect_as(
                self.member,
                "chat",
            )

            self.assertTrue(connected)

            # Delete the membership through Django's async-safe ORM.
            await database_sync_to_async(
                GroupMember.objects.filter(
                    pk=self.membership.pk,
                ).delete
            )()

            # Trigger a chat event to verify authorization again.
            channel_layer = get_channel_layer()

            await channel_layer.group_send(
                f"group_chat_{self.group.pk}",
                {
                    "type": "chat.message",
                    "data": {
                        "type": "test_message",
                    },
                },
            )

            # The consumer should close instead of delivering the message.
            response = await communicator.receive_output(timeout=5)

            self.assertEqual(
                response["type"],
                "websocket.close",
            )

            self.assertEqual(
                response["code"],
                4403,
            )

            await communicator.disconnect()

        async_to_sync(run_test)()

    def test_public_community_cannot_access_private_group_websockets(self):
        """
        Public communities must not use private development group sockets.

        Even the public community owner should be rejected.
        """

        public_group = ProjectGroup.objects.create(
            name="Public WebSocket Security Test",
            description="Testing public community restrictions.",
            owner=self.owner,
            is_private=False,
            join_policy="open",
        )

        async def run_test():
            endpoints = [
                "chat",
                "repository-notifications",
                "repository-member-notifications",
                "repository-updates",
                "meetings/notifications",
            ]

            for endpoint in endpoints:
                await self.check_connection(
                    self.owner,
                    endpoint,
                    False,
                    group_id=public_group.pk,
                )

        async_to_sync(run_test)()