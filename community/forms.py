"""Forms for CodeView groups, discussions, comments, and chat."""

from django import forms

from .models import (
    ProjectGroup,
    GroupDiscussion,
    GroupDiscussionComment,
    GroupChatMessage,
    GroupRepository,  
)


# ============================================================
# 1. CREATE PROJECT GROUP
# ============================================================

class ProjectGroupForm(forms.ModelForm):
    """Collect group details and validate membership settings."""

    class Meta:
        model = ProjectGroup

        fields = [
            "name",
            "description",
            "is_private",
            "join_policy",
        ]

        widgets = {
            "name": forms.TextInput(
                attrs={
                    "placeholder": "Enter your group name",
                    "class": "group-input",
                }
            ),

            "description": forms.Textarea(
                attrs={
                    "placeholder": (
                        "Describe your community or development project"
                    ),
                    "class": "group-textarea",
                    "rows": 4,
                }
            ),

            "is_private": forms.CheckboxInput(
                attrs={
                    "class": "group-checkbox",
                }
            ),

            "join_policy": forms.Select(
                attrs={
                    "class": "group-input",
                }
            ),
        }

        labels = {
            "name": "Group Name",
            "description": "Group Description",
            "is_private": "Private Development Group",
            "join_policy": "Who Can Join?",
        }

        help_texts = {
            "is_private": (
                "Leave unchecked for a public community. "
                "Check for a private development group."
            ),

            "join_policy": (
                "Choose whether developers can join immediately, "
                "request administrator approval, or require an invitation."
            ),
        }

    def clean_name(self):
        """Remove unnecessary spaces from the group name."""

        name = self.cleaned_data["name"].strip()

        if not name:
            raise forms.ValidationError(
                "Please enter a group name."
            )

        return name

    def clean(self):
        """Validate the group type and joining policy together."""

        cleaned_data = super().clean()

        is_private = cleaned_data.get("is_private")
        join_policy = cleaned_data.get("join_policy")

        # Private development groups cannot allow open joining.
        if is_private and join_policy == "open":
            self.add_error(
                "join_policy",
                (
                    "Private development groups must require "
                    "administrator approval or an invitation."
                ),
            )

        return cleaned_data


# ============================================================
# 2. GROUP DISCUSSION
# ============================================================

class GroupDiscussionForm(forms.ModelForm):
    """Collect the title and content of a group discussion."""

    class Meta:
        model = GroupDiscussion

        fields = [
            "title",
            "content",
        ]

        widgets = {
            "title": forms.TextInput(
                attrs={
                    "placeholder": "Enter discussion title",
                    "class": "group-input",
                }
            ),

            "content": forms.Textarea(
                attrs={
                    "placeholder": "What would you like to discuss?",
                    "class": "group-textarea",
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
# 3. GROUP DISCUSSION COMMENT
# ============================================================

class GroupDiscussionCommentForm(forms.ModelForm):
    """
    Collect comments and replies underneath discussions.

    The same form handles:
    - Normal comments
    - Replies to comments
    - Replies to other replies

    The parent comment is assigned securely in views.py.
    """

    class Meta:
        model = GroupDiscussionComment

        fields = [
            "content",
        ]

        widgets = {
            "content": forms.Textarea(
                attrs={
                    "placeholder": "Write your comment or reply...",
                    "class": "group-textarea",
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
# 4. GROUP CHAT MESSAGE (NEW)
# ============================================================

class GroupChatMessageForm(forms.ModelForm):
    """
    Collect messages sent inside group chats.

    Supports:
    - Text messages
    - Programming code snippets
    - Voice notes
    - File attachments

    The sender, group, and reply target are assigned
    securely in views.py rather than trusted from the browser.
    """

    class Meta:
        model = GroupChatMessage

        # Developers can only submit these fields.
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
                    "placeholder": "Type your message...",
                    "class": "group-textarea",
                    "rows": 3,
                }
            ),

            "code_language": forms.TextInput(
                attrs={
                    "placeholder": "e.g. python, javascript, go",
                    "class": "group-input",
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
        """Remove unnecessary whitespace from messages."""

        content = self.cleaned_data.get("content", "")

        return content.strip()

    def clean_code_language(self):
        """Normalize the programming language name."""

        language = self.cleaned_data.get(
            "code_language",
            "",
        )

        return language.strip().lower()

    def clean_attachment(self):
        """
        Check the uploaded file size.

        This is an initial upload limit.
        We'll add file-type verification and secure
        file-serving rules when implementing uploads.
        """

        attachment = self.cleaned_data.get("attachment")

        if attachment:

            # Maximum upload size: 20 MB.
            maximum_size = 20 * 1024 * 1024

            if attachment.size > maximum_size:
                raise forms.ValidationError(
                    "Files cannot exceed 20 MB."
                )

        return attachment

    def clean(self):
        """Validate the selected message type and its content."""

        cleaned_data = super().clean()

        message_type = cleaned_data.get("message_type")
        content = cleaned_data.get("content", "")
        attachment = cleaned_data.get("attachment")

        # Text and code messages must contain text.
        if message_type in ("text", "code"):

            if not content:
                self.add_error(
                    "content",
                    "Please enter a message.",
                )

        # Voice notes and file messages require uploads.
        if message_type in ("voice", "file"):

            if not attachment:
                self.add_error(
                    "attachment",
                    "Please attach a file or voice note.",
                )

        return cleaned_data


# ============================================================
# 5. ADD GROUP MEMBER
# ============================================================

class AddGroupMemberForm(forms.Form):
    """Allow administrators to select a registered developer."""

    # Store the username entered by the administrator.
    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(
            attrs={
                "class": "group-input",
                "placeholder": "Enter developer username",
            }
        ),
    )

    def clean_username(self):
        """Remove unnecessary spaces from the username."""

        username = self.cleaned_data["username"].strip()

        if not username:
            raise forms.ValidationError(
                "Please enter a developer username."
            )

        return username


        # ============================================================
# GITHUB REPOSITORY CONNECTION FORM
# ============================================================

class GroupRepositoryForm(forms.Form):
    """Collect and validate a public GitHub repository URL."""

    # Ask the developer to provide a GitHub repository URL.
    repository_url = forms.URLField(
        label="GitHub Repository URL",
        max_length=500,
        widget=forms.URLInput(
            attrs={
                "class": "group-input",
                "placeholder": "https://github.com/owner/repository",
            }
        ),
    )

    def clean_repository_url(self):
        """Check that the URL points to a GitHub repository."""

        from urllib.parse import urlparse, unquote

        # Get the URL after Django performs basic URL validation.
        url = self.cleaned_data["repository_url"].strip()

        # Split the URL into its components.
        parsed = urlparse(url)

        # Require HTTPS and the official GitHub domain.
        if parsed.scheme != "https" or parsed.hostname != "github.com":
            raise forms.ValidationError(
                "Enter a valid HTTPS GitHub repository URL."
            )

        # Reject unexpected ports, credentials, queries, and fragments.
        try:
            port = parsed.port
        except ValueError:
            raise forms.ValidationError("Invalid repository URL.")

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

        # Extract the repository owner and name.
        parts = parsed.path.strip("/").split("/")

        # A repository URL must contain exactly owner/repository.
        if len(parts) != 2:
            raise forms.ValidationError(
                "Use this format: https://github.com/owner/repository"
            )

              # Extract the repository owner and name.
        owner, repository = parts

        # Allow GitHub URLs ending with .git.
        if repository.endswith(".git"):
            repository = repository[:-4]

        # Reject an empty repository name.
        if not repository:
            raise forms.ValidationError(
                "Enter a valid GitHub repository name."
            )
        # Reject encoded characters and invalid repository names.
        import re

        if (
            unquote(owner) != owner
            or unquote(repository) != repository
            or not re.fullmatch(r"[A-Za-z0-9-]{1,39}", owner)
            or owner.startswith("-")
            or owner.endswith("-")
            or not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", repository)
        ):
            raise forms.ValidationError(
                "Invalid GitHub repository owner or name."
            )

        # Store the extracted values for use in the view.
        self.cleaned_data["github_owner"] = owner
        self.cleaned_data["repository_name"] = repository

        return url