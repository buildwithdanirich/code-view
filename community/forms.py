"""
Forms for ColabVerse private development groups, chat, and GitHub.

Group rules:
    1. Development groups are private and invitation-only.
    2. Only group owners can send membership invitations.
    3. Private groups allow at most 10 members, including the owner.

This file does not create memberships or send invitations.
Those actions are handled by the views and invitation service.
"""

import re

from urllib.parse import urlparse, unquote

from django import forms

from .models import (
    ProjectGroup,
    GroupChatMessage,
)


# ============================================================
# 1. CREATE PRIVATE DEVELOPMENT GROUP FORM
# ============================================================

class ProjectGroupForm(forms.ModelForm):
    """
    Collect information for a ColabVerse private development group.

    Rules:
        1. Developers provide a name and description.
        2. Every newly created group is private.
        3. Membership is invitation-only.
        4. The view assigns the authenticated group owner.
        5. The invitation service enforces the 10-member limit.
    """

    class Meta:
        model = ProjectGroup

        # Developers cannot select the privacy or joining policy.
        # These settings are enforced by the form.
        fields = [
            "name",
            "description",
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
                        "Describe your development project or team"
                    ),
                    "rows": 4,
                }
            ),
        }

        labels = {
            "name": "Group Name",
            "description": "Group Description",
        }

    def clean_name(self):
        """
        Remove surrounding whitespace from the group name.

        Reject empty names.
        """

        name = self.cleaned_data["name"].strip()

        if not name:
            raise forms.ValidationError(
                "Please enter a group name."
            )

        return name

    def clean(self):
        """
        Enforce private-group settings during form validation.

        These values do not come from browser-submitted fields.
        """

        cleaned_data = super().clean()

        # Every new ColabVerse development group is private.
        self.instance.is_private = True

        # Developers must receive an invitation to join.
        self.instance.join_policy = "invite"

        return cleaned_data

    def save(self, commit=True):
        """
        Save a private, invitation-only development group.

        Also works when views.py calls:
            form.save(commit=False)
        """

        # Create the model instance without saving it yet.
        group = super().save(commit=False)

        # Enforce the rules again immediately before saving.
        group.is_private = True
        group.join_policy = "invite"

        if commit:
            group.save()
            self.save_m2m()

        return group


# ============================================================
# 2. GROUP CHAT MESSAGE FORM
# ============================================================

class GroupChatMessageForm(forms.ModelForm):
    """
    Collect messages sent inside ColabVerse group chats.

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
        Validate files uploaded to ColabVerse group chats.

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

        # File types supported by ColabVerse.
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
# 3. GITHUB REPOSITORY CONNECTION FORM
# ============================================================

class GroupRepositoryForm(forms.Form):
    """
    Collect and validate a GitHub repository URL.

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