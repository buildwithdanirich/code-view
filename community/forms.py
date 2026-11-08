"""
Forms for CodeView groups, discussions, comments, chat, and GitHub.

Group rules:
    1. Normal chat groups are public and open to registered developers.
    2. Private development groups require owner-sent invitations.
    3. Private groups allow at most 15 members including the owner.

This file does not create memberships or send invitations.
Those actions are handled by the views and invitation service.
"""

import re

from urllib.parse import urlparse, unquote

from django import forms

from .models import (
    ProjectGroup,
    GroupDiscussion,
    GroupDiscussionComment,
    GroupChatMessage,
)


# ============================================================
# 1. CREATE GROUP FORM
# ============================================================

class ProjectGroupForm(forms.ModelForm):
    """
    Collect information when creating a CodeView group.

    Developers choose:
        - Group name
        - Group description
        - Whether the group is private

    Joining rules are assigned automatically:
        Public group  -> open
        Private group -> invite
    """

    class Meta:
        model = ProjectGroup

        # The owner is assigned in views.py.
        # The joining policy is assigned automatically.
        fields = [
            "name",
            "description",
            "is_private",
        ]

        widgets = {

            "name": forms.TextInput(
                attrs={
                    "class": "group-input",
                    "placeholder": "Enter your group name",
                }
            ),

            "description": forms.Textarea(
                attrs={
                    "class": "group-textarea",
                    "placeholder": (
                        "Describe your community or development project"
                    ),
                    "rows": 4,
                }
            ),

            "is_private": forms.CheckboxInput(
                attrs={
                    "class": "group-checkbox",
                }
            ),
        }

        labels = {
            "name": "Group Name",
            "description": "Group Description",
            "is_private": "Private Development Group",
        }

        help_texts = {
            "is_private": (
                "Leave unchecked to create a normal chat group "
                "that registered developers can join freely. "
                "Check to create a private development group "
                "where the owner invites developers."
            ),
        }

    def clean_name(self):
        """
        Remove extra spaces from the group name.

        Reject names containing only whitespace.
        """

        name = self.cleaned_data["name"].strip()

        if not name:
            raise forms.ValidationError(
                "Please enter a group name."
            )

        return name

    def clean(self):
        """
        Set the joining policy from the selected group type.

        The developer cannot submit a different joining policy
        through the browser.
        """

        cleaned_data = super().clean()

        is_private = cleaned_data.get("is_private", False)

        if is_private:

            # Private development groups require invitations.
            joining_policy = "invite"

        else:

            # Normal chat groups allow direct joining.
            joining_policy = "open"

        # The field is not shown in the form, but the model
        # still needs its value for validation and saving.
        self.instance.join_policy = joining_policy

        return cleaned_data

    def save(self, commit=True):
        """
        Save the group with the correct joining policy.

        This also works when views.py uses:
            form.save(commit=False)
        """

        group = super().save(commit=False)

        if group.is_private:
            group.join_policy = "invite"
        else:
            group.join_policy = "open"

        if commit:
            group.save()
            self.save_m2m()

        return group


# ============================================================
# 2. GROUP DISCUSSION FORM
# ============================================================

class GroupDiscussionForm(forms.ModelForm):
    """
    Collect the title and content of a group discussion.

    Only authorized group members can create discussions.
    The view checks membership before saving.
    """

    class Meta:
        model = GroupDiscussion

        fields = [
            "title",
            "content",
        ]

        widgets = {

            "title": forms.TextInput(
                attrs={
                    "class": "group-input",
                    "placeholder": "Enter discussion title",
                }
            ),

            "content": forms.Textarea(
                attrs={
                    "class": "group-textarea",
                    "placeholder": "What would you like to discuss?",
                    "rows": 5,
                }
            ),
        }

    def clean_title(self):
        """Reject empty discussion titles."""

        title = self.cleaned_data["title"].strip()

        if not title:
            raise forms.ValidationError(
                "Please enter a discussion title."
            )

        return title

    def clean_content(self):
        """Reject empty discussion messages."""

        content = self.cleaned_data["content"].strip()

        if not content:
            raise forms.ValidationError(
                "Please enter a discussion message."
            )

        return content


# ============================================================
# 3. GROUP DISCUSSION COMMENT FORM
# ============================================================

class GroupDiscussionCommentForm(forms.ModelForm):
    """
    Collect comments and replies underneath discussions.

    Supports:
        - Normal comments
        - Replies to comments
        - Replies to other replies

    The view assigns the author, discussion, and parent.
    """

    class Meta:
        model = GroupDiscussionComment

        fields = [
            "content",
        ]

        widgets = {

            "content": forms.Textarea(
                attrs={
                    "class": "group-textarea",
                    "placeholder": "Write your comment or reply...",
                    "rows": 3,
                    "maxlength": 2000,
                }
            ),
        }

    def clean_content(self):
        """Reject empty comments and replies."""

        content = self.cleaned_data["content"].strip()

        if not content:
            raise forms.ValidationError(
                "Please enter a comment or reply."
            )

        return content


# ============================================================
# 4. GROUP CHAT MESSAGE FORM
# ============================================================

class GroupChatMessageForm(forms.ModelForm):
    """
    Collect messages sent inside CodeView group chats.

    Supports:
        1. Text messages
        2. Programming code snippets
        3. Voice notes
        4. File attachments

    The view assigns:
        - Sender
        - Group
        - Reply target

    This prevents developers from choosing another sender
    or another group through submitted form data.
    """

    class Meta:
        model = GroupChatMessage

        fields = [
            "message_type",
            "content",
            "code_language",
            "attachment",
        ]

        widgets = {

            "message_type": forms.Select(
                attrs={
                    "class": "group-input",
                }
            ),

            "content": forms.Textarea(
                attrs={
                    "class": "group-textarea",
                    "placeholder": "Type your message...",
                    "rows": 3,
                }
            ),

            "code_language": forms.TextInput(
                attrs={
                    "class": "group-input",
                    "placeholder": "e.g. python, javascript, go",
                    "maxlength": 30,
                }
            ),

            "attachment": forms.ClearableFileInput(
                attrs={
                    "class": "group-input",
                }
            ),
        }

        labels = {
            "message_type": "Message Type",
            "content": "Message",
            "code_language": "Programming Language",
            "attachment": "Voice Note or File",
        }

    def clean_content(self):
        """
        Remove unnecessary whitespace from messages.
        """

        content = self.cleaned_data.get("content") or ""

        return content.strip()

    def clean_code_language(self):
        """
        Normalize programming language names.

        Example:
            "Python" -> "python"
            "GO"     -> "go"
        """

        language = self.cleaned_data.get("code_language") or ""

        return language.strip().lower()

    def clean_attachment(self):
        """
        Validate files uploaded to CodeView group chats.

        Rules:
        1. Maximum file size is 20 MB.
        2. Only supported file extensions are allowed.
        3. Voice notes must use supported audio formats.

        Note:
            File extensions alone do not prove a file is safe.
            Additional security checks are required before production.
        """

        # Get the uploaded file.
        attachment = self.cleaned_data.get("attachment")

        # No attachment was provided.
        if not attachment:
            return attachment

        # Maximum upload size: 20 MB.
        maximum_size = 20 * 1024 * 1024

        if attachment.size > maximum_size:
            raise forms.ValidationError(
                "Files cannot exceed 20 MB."
            )

        # File types supported by CodeView.
        allowed_extensions = {
            # Programming files.
            ".py",
            ".go",
            ".js",
            ".ts",
            ".jsx",
            ".tsx",
            ".html",
            ".css",
            ".json",
            ".sql",
            ".java",
            ".c",
            ".cpp",
            ".h",
            ".rs",
            ".php",
            ".sh",

            # Documents.
            ".pdf",
            ".txt",
            ".md",
            ".docx",
            ".csv",

            # Images.
            ".png",
            ".jpg",
            ".jpeg",
            ".gif",
            ".webp",

            # Voice notes.
            ".mp3",
            ".wav",
            ".ogg",
            ".webm",
            ".m4a",
        }

        # Extract the file extension.
        filename = attachment.name.lower()

        extension = "." + filename.rsplit(".", 1)[-1]

        # Reject unsupported file extensions.
        if extension not in allowed_extensions:
            raise forms.ValidationError(
                "This file type is not supported."
            )

        # Voice messages must contain audio files.
        message_type = self.data.get("message_type")

        if message_type == "voice":

            allowed_audio_extensions = {
                ".mp3",
                ".wav",
                ".ogg",
                ".webm",
                ".m4a",
            }

            if extension not in allowed_audio_extensions:
                raise forms.ValidationError(
                    "Voice notes must contain an audio file."
                )

        return attachment

    def clean(self):
        """
        Validate message content according to its type.

        Text/code:
            Must contain written content.

        Voice/file:
            Must contain an uploaded attachment.
        """

        cleaned_data = super().clean()

        message_type = cleaned_data.get("message_type")

        content = cleaned_data.get("content") or ""

        attachment = cleaned_data.get("attachment")

        # Text and code messages require written content.
        if message_type in ("text", "code"):

            if not content:
                self.add_error(
                    "content",
                    "Please enter a message.",
                )

        # Voice notes and file messages require attachments.
        elif message_type in ("voice", "file"):

            if not attachment:
                self.add_error(
                    "attachment",
                    "Please attach a file or voice note.",
                )

        return cleaned_data


# ============================================================
# 5. GITHUB REPOSITORY CONNECTION FORM
# ============================================================

class GroupRepositoryForm(forms.Form):
    """
    Collect and validate a public GitHub repository URL.

    Example:
        https://github.com/owner/repository

    This form validates the URL format.

    The view must separately verify that the repository
    exists and is accessible.
    """

    repository_url = forms.URLField(
        label="GitHub Repository URL",
        max_length=500,

        widget=forms.URLInput(
            attrs={
                "class": "group-input",
                "placeholder": (
                    "https://github.com/owner/repository"
                ),
            }
        ),
    )

    def clean_repository_url(self):
        """
        Validate a GitHub repository URL.

        Security rules:
            - HTTPS only.
            - Official github.com domain only.
            - No credentials.
            - No custom ports.
            - No query strings.
            - No URL fragments.
            - Exactly owner/repository.
        """

        # Django already checks basic URL validity.
        url = self.cleaned_data["repository_url"].strip()

        # Separate the URL into its components.
        parsed = urlparse(url)

        # Only accept the official GitHub domain.
        if (
            parsed.scheme != "https"
            or parsed.hostname != "github.com"
        ):
            raise forms.ValidationError(
                "Enter a valid HTTPS GitHub repository URL."
            )

        # Reading a malformed port can raise ValueError.
        try:
            port = parsed.port

        except ValueError:
            raise forms.ValidationError(
                "Invalid repository URL."
            )

        # Reject unexpected URL components.
        if (
            parsed.username
            or parsed.password
            or port is not None
            or parsed.query
            or parsed.fragment
        ):
            raise forms.ValidationError(
                "Enter a standard GitHub repository URL."
            )

        # Split the path into owner and repository.
        parts = parsed.path.strip("/").split("/")

        if len(parts) != 2:
            raise forms.ValidationError(
                "Use this format: "
                "https://github.com/owner/repository"
            )

        owner, repository = parts

        # Accept the common .git suffix.
        if repository.endswith(".git"):
            repository = repository[:-4]

        # Reject empty repository names.
        if not repository:
            raise forms.ValidationError(
                "Enter a valid GitHub repository name."
            )

        # Reject encoded characters.
        if (
            unquote(owner) != owner
            or unquote(repository) != repository
        ):
            raise forms.ValidationError(
                "Encoded repository names are not allowed."
            )

        # GitHub owner names may contain letters,
        # numbers, and hyphens.
        valid_owner = re.fullmatch(
            r"[A-Za-z0-9-]{1,39}",
            owner,
        )

        if (
            not valid_owner
            or owner.startswith("-")
            or owner.endswith("-")
        ):
            raise forms.ValidationError(
                "Invalid GitHub repository owner."
            )

        # Validate the repository name.
        valid_repository = re.fullmatch(
            r"[A-Za-z0-9_.-]{1,100}",
            repository,
        )

        if not valid_repository:
            raise forms.ValidationError(
                "Invalid GitHub repository name."
            )

        # Make the extracted values available to views.py.
        self.cleaned_data["github_owner"] = owner

        self.cleaned_data["repository_name"] = repository

        return url