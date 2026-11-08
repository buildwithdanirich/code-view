"""Database models for CodeView groups, memberships, and collaboration."""

import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction

from .storage import PrivateGroupStorage
# ============================================================
# 1. PROJECT GROUP
# ============================================================

class ProjectGroup(models.Model):
    """Store normal chat groups and private development groups."""

    JOIN_POLICY_CHOICES = [
        ("open", "Anyone Can Join"),
        ("approval", "Admin Approval Required"),
        ("invite", "Invitation Only"),
    ]

    name = models.CharField(max_length=100)
    description = models.TextField()

    # Developer who owns the group.
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="owned_project_groups",
    )

    # Helps invalidate old owner permissions if ownership changes.
    owner_membership_generation = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
    )

    # False = normal chat group.
    # True = private development group.
    is_private = models.BooleanField(default=False)

    # Existing join policies are retained for migration compatibility.
    join_policy = models.CharField(
        max_length=10,
        choices=JOIN_POLICY_CHOICES,
        default="open",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def clean(self):
        """Prevent unrestricted joining of private groups."""
        super().clean()

        if self.is_private and self.join_policy == "open":
            raise ValidationError({
                "join_policy": (
                    "Private development groups must require "
                    "an invitation or approval."
                )
            })

    def save(self, *args, **kwargs):
        """Validate group settings before saving."""
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


# ============================================================
# 2. GROUP MEMBER
# ============================================================

class GroupMember(models.Model):
    """Store group members and their existing roles."""

    ROLE_CHOICES = [
        ("admin", "Admin"),
        ("member", "Member"),
    ]

    group = models.ForeignKey(
        ProjectGroup,
        on_delete=models.CASCADE,
        related_name="memberships",
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
    )

    role = models.CharField(
        max_length=10,
        choices=ROLE_CHOICES,
        default="member",
    )

    joined_at = models.DateTimeField(auto_now_add=True)

    # Identifies the current membership period.
    membership_generation = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["group", "user"],
                name="unique_project_group_member",
            ),
        ]

    def clean(self):
        """
        Enforce the private-group limit.

        Maximum:
            1 owner + 14 other developers = 15 people.

        Normal chat groups have no fixed membership limit.
        """
        super().clean()

        if not self.group_id:
            return

        # Normal groups have no fixed limit.
        if not self.group.is_private:
            return

        # Count members other than the owner.
        members = GroupMember.objects.filter(
            group_id=self.group_id,
        ).exclude(
            user_id=self.group.owner_id,
        )

        # Do not count the current record twice during an update.
        if self.pk:
            members = members.exclude(pk=self.pk)

        # The owner is counted separately.
        if self.user_id == self.group.owner_id:
            return

        if members.count() >= 14:
            raise ValidationError(
                "Private development groups cannot exceed "
                "15 people, including the owner."
            )

    def save(self, *args, **kwargs):
        """
        Save memberships safely.

        Lock the parent group so simultaneous membership saves
        cannot independently pass the capacity check.
        """

        database = (
            kwargs.get("using")
            or self._state.db
            or "default"
        )

        with transaction.atomic(using=database):

            if self.group_id:
                locked_group = (
                    ProjectGroup.objects.using(database)
                    .select_for_update()
                    .get(pk=self.group_id)
                )

                self.group = locked_group

            # Validate while holding the database lock.
            self.full_clean()

            # Save inside the same transaction.
            super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user} in {self.group.name}"


# ============================================================
# 3. EXISTING GROUP MEMBERSHIP REQUEST
# ============================================================

class GroupMembershipRequest(models.Model):
    """
    Legacy membership-request model.

    Keep this temporarily because existing views and migrations
    may still reference it.

    We will remove the old approval workflow after updating
    the remaining CodeView files.
    """

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
    ]

    group = models.ForeignKey(
        ProjectGroup,
        on_delete=models.CASCADE,
        related_name="membership_requests",
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="group_join_requests",
    )

    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default="pending",
    )

    message = models.TextField(
        max_length=1000,
        blank=True,
    )

    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_group_requests",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    reviewed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["-created_at"]

        constraints = [
            models.UniqueConstraint(
                fields=["group", "user"],
                name="unique_group_membership_request",
            ),
        ]

        indexes = [
            models.Index(
                fields=["group", "status", "created_at"],
                name="group_request_status_idx",
            ),
        ]

    def clean(self):
        """Validate legacy membership requests."""
        super().clean()

        if not self.group_id or not self.user_id:
            return

        already_member = GroupMember.objects.filter(
            group_id=self.group_id,
            user_id=self.user_id,
        ).exists()

        if already_member:
            raise ValidationError(
                "This developer is already a member of the group."
            )

        if self.group.join_policy == "invite":
            raise ValidationError(
                "This group can only be joined through an invitation."
            )

    def save(self, *args, **kwargs):
        """Validate before saving."""
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return (
            f"{self.user} requested to join "
            f"{self.group.name}: {self.status}"
        )


# ============================================================
# 4. NEW GROUP INVITATION
# ============================================================

class GroupInvitation(models.Model):
    """
    Store invitations sent by private development group owners.

    Workflow:
        1. Owner invites a developer.
        2. Invitation starts as pending.
        3. Developer accepts or declines.
        4. Accepted invitations lead to group membership.

    The acceptance workflow will be implemented separately.
    """

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("accepted", "Accepted"),
        ("declined", "Declined"),
    ]

    # Private development group sending the invitation.
    group = models.ForeignKey(
        ProjectGroup,
        on_delete=models.CASCADE,
        related_name="invitations",
    )

    # Developer who sent the invitation.
    # This must be the group owner.
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="sent_group_invitations",
    )

    # Developer receiving the invitation.
    invited_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="received_group_invitations",
    )

    # pending, accepted, or declined.
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default="pending",
    )

    # When the invitation was created.
    created_at = models.DateTimeField(auto_now_add=True)

    # When the developer accepted or declined.
    responded_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["-created_at"]

        constraints = [
            # Prevent duplicate invitation records for one
            # developer in the same group.
            models.UniqueConstraint(
                fields=["group", "invited_user"],
                name="unique_private_group_invitation",
            ),
        ]

        indexes = [
            # Make finding pending invitations faster.
            models.Index(
                fields=["invited_user", "status"],
                name="group_invitee_status_idx",
            ),
        ]

    def clean(self):
        """Validate the invitation before saving it."""

        super().clean()

        # Make sure the required relationships exist.
        if (
            not self.group_id
            or not self.invited_by_id
            or not self.invited_user_id
        ):
            return

        # Only private groups can send invitations.
        if not self.group.is_private:
            raise ValidationError(
                "Only private development groups use invitations."
            )

        # Only the group owner can send invitations.
        if self.invited_by_id != self.group.owner_id:
            raise ValidationError(
                "Only the group owner can send invitations."
            )

        # The owner cannot invite themselves.
        if self.invited_user_id == self.group.owner_id:
            raise ValidationError(
                "The group owner cannot invite themselves."
            )

        # Prevent inviting an existing member.
        if self.status == "pending":

            already_member = GroupMember.objects.filter(
                group_id=self.group_id,
                user_id=self.invited_user_id,
            ).exists()

            if already_member:
                raise ValidationError(
                    "This developer is already a member of the group."
                )

    def save(self, *args, **kwargs):
        """Validate invitation data before saving."""
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return (
            f"Invitation for {self.invited_user} "
            f"to {self.group.name}: {self.status}"
        )


# ============================================================
# 5. GROUP DISCUSSION
# ============================================================

class GroupDiscussion(models.Model):
    """Store discussion posts inside groups."""

    group = models.ForeignKey(
        ProjectGroup,
        on_delete=models.CASCADE,
        related_name="discussions",
    )

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="group_discussions",
    )

    title = models.CharField(max_length=200)

    content = models.TextField()

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


# ============================================================
# 6. GROUP DISCUSSION COMMENT
# ============================================================

class GroupDiscussionComment(models.Model):
    """Store comments and nested replies under discussions."""

    discussion = models.ForeignKey(
        GroupDiscussion,
        on_delete=models.CASCADE,
        related_name="comments",
    )

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
    )

    content = models.TextField(max_length=2000)

    # A comment can reply to another comment.
    # None means it is a top-level comment.
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="replies",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def clean(self):
        """Prevent invalid comment relationships."""
        super().clean()

        # A normal comment has no parent.
        if not self.parent_id:
            return

        # A comment cannot reply to itself.
        if self.pk and self.parent_id == self.pk:
            raise ValidationError(
                "A comment cannot reply to itself."
            )

        # Replies must stay in the same discussion.
        if self.parent.discussion_id != self.discussion_id:
            raise ValidationError(
                "Replies must belong to the same discussion."
            )

        # Prevent circular reply relationships.
        seen = {self.pk} if self.pk else set()

        ancestor = self.parent

        while ancestor is not None:

            if ancestor.pk in seen:
                raise ValidationError(
                    "Comment replies cannot form a cycle."
                )

            seen.add(ancestor.pk)

            ancestor = ancestor.parent

    def save(self, *args, **kwargs):
        """Validate comments before saving."""
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Comment by {self.author.username}"


# ============================================================
# 7. GROUP DISCUSSION LIKE
# ============================================================

class GroupDiscussionLike(models.Model):
    """Track which developers liked a discussion."""

    discussion = models.ForeignKey(
        GroupDiscussion,
        on_delete=models.CASCADE,
        related_name="likes",
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["discussion", "user"],
                name="unique_discussion_like",
            ),
        ]

    def __str__(self):
        return f"{self.user} liked {self.discussion.title}"


# ============================================================
# 8. HIDDEN DISCUSSION
# ============================================================

class HiddenDiscussion(models.Model):
    """Remember discussions hidden by individual developers."""

    discussion = models.ForeignKey(
        GroupDiscussion,
        on_delete=models.CASCADE,
        related_name="hidden_by",
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
    )

    hidden_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["discussion", "user"],
                name="unique_hidden_discussion",
            ),
        ]

    def __str__(self):
        return f"{self.user} hid {self.discussion.title}"


# ============================================================
# 9. GROUP REPOSITORY
# ============================================================

class GroupRepository(models.Model):
    """Store GitHub repository details for private groups."""

    group = models.OneToOneField(
        ProjectGroup,
        on_delete=models.CASCADE,
        related_name="repository",
    )

    github_owner = models.CharField(max_length=100)

    repository_name = models.CharField(max_length=100)

    default_branch = models.CharField(
        max_length=100,
        default="main",
    )

    connected_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        """Allow repositories only in private development groups."""
        super().clean()

        if self.group_id and not self.group.is_private:
            raise ValidationError(
                "Only private development groups can connect repositories."
            )

    def save(self, *args, **kwargs):
        """Validate repository information before saving."""
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.github_owner}/{self.repository_name}"


# ============================================================
# 10. GROUP CHAT MESSAGE
# ============================================================

class GroupChatMessage(models.Model):
    """
    Store messages sent inside normal and private groups.

    Supports:
        - Text messages
        - Code snippets
        - Voice notes
        - File attachments
        - Replies
        - Message editing
        - Soft deletion
    """

    MESSAGE_TYPES = [
        ("text", "Text"),
        ("code", "Code Snippet"),
        ("voice", "Voice Note"),
        ("file", "Attachment"),
    ]

    # Group receiving the message.
    group = models.ForeignKey(
        ProjectGroup,
        on_delete=models.CASCADE,
        related_name="chat_messages",
    )

    # Keep chat history when the sender account is deleted.
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="group_chat_messages",
    )

    # Identify the message type.
    message_type = models.CharField(
        max_length=10,
        choices=MESSAGE_TYPES,
        default="text",
    )

    # Ordinary text or programming code.
    content = models.TextField(
        blank=True,
    )

    # Programming language for code snippets.
    code_language = models.CharField(
        max_length=30,
        blank=True,
    )
    # Store chat attachments privately.
    # Access is controlled by download_group_attachment().
    attachment = models.FileField(
        upload_to="group_chat/attachments/%Y/%m/",
        storage=PrivateGroupStorage(),
        blank=True,
    )

    # A message can reply to another message.
    reply_to = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="chat_replies",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    # Time of the most recent edit.
    edited_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    # Soft deletion preserves message references.
    deleted_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["created_at", "id"]

        indexes = [
            models.Index(
                fields=["group", "created_at", "id"],
            ),
        ]

    def clean(self):
        """Validate messages and their reply relationships."""
        super().clean()

        if self.reply_to_id:

            # A message cannot reply to itself.
            if self.pk and self.reply_to_id == self.pk:
                raise ValidationError(
                    "A message cannot reply to itself."
                )

            # Replies cannot cross group boundaries.
            if self.reply_to.group_id != self.group_id:
                raise ValidationError(
                    "Replies must stay within the same group."
                )

        # Deleted messages remain stored.
        if self.deleted_at:
            return

        # Text and code messages require content.
        if self.message_type in ("text", "code"):

            if not self.content.strip():
                raise ValidationError(
                    "Text and code messages require content."
                )

        # Voice notes and file messages require attachments.
        if self.message_type in ("voice", "file"):

            if not self.attachment:
                raise ValidationError(
                    "Voice and file messages require an attachment."
                )

    def save(self, *args, **kwargs):
        """Validate messages before saving."""
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):

        sender = (
            self.sender.username
            if self.sender
            else "Deleted user"
        )

        return (
            f"{sender} in {self.group.name} "
            f"({self.message_type})"
        )


        # ============================================================
# 11. GROUP MESSAGE REACTION
# ============================================================

class GroupMessageReaction(models.Model):
    """
    Store emoji reactions to group chat messages.

    Rules:
        - Each developer can have one reaction per message.
        - Developers can change their reaction.
        - Developers can remove their reaction.
        - Reactions belong to a specific message.
    """

    # Supported emoji reactions.
    REACTION_CHOICES = [
        ("👍", "Like"),
        ("❤️", "Love"),
        ("😂", "Laugh"),
        ("🔥", "Fire"),
        ("😮", "Surprised"),
        ("😢", "Sad"),
    ]

    # Message receiving the reaction.
    message = models.ForeignKey(
        GroupChatMessage,
        on_delete=models.CASCADE,
        related_name="reactions",
    )

    # Developer who reacted.
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="group_message_reactions",
    )

    # Emoji selected by the developer.
    emoji = models.CharField(
        max_length=10,
        choices=REACTION_CHOICES,
    )

    # When the reaction was created.
    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:

        # Prevent one developer from creating
        # multiple reactions on the same message.
        constraints = [
            models.UniqueConstraint(
                fields=["message", "user"],
                name="unique_group_message_reaction",
            ),
        ]

    def clean(self):
        """Validate the reaction before saving."""

        super().clean()

        if not self.message_id or not self.user_id:
            return

        # Deleted messages cannot receive reactions.
        if self.message.deleted_at:
            raise ValidationError(
                "Cannot react to a deleted message."
            )

        # Only group members or the owner can react.
        is_owner = (
            self.message.group.owner_id == self.user_id
        )

        is_member = GroupMember.objects.filter(
            group_id=self.message.group_id,
            user_id=self.user_id,
        ).exists()

        if not is_owner and not is_member:
            raise ValidationError(
                "Only group members can react to messages."
            )

    def save(self, *args, **kwargs):
        """Validate the reaction before saving."""

        self.full_clean()

        super().save(*args, **kwargs)

    def __str__(self):

        return (
            f"{self.user} reacted {self.emoji} "
            f"to message {self.message_id}"
        )