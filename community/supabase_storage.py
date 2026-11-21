"""Supabase Storage backends for public avatars and private files."""

from functools import cached_property

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import Storage
from django.utils.deconstruct import deconstructible


class _SupabaseStorage(Storage):
    """Base class for Supabase Storage."""

    bucket_setting = None

    @cached_property
    def bucket(self):
        """Connect to the configured Supabase bucket."""

        from supabase import create_client

        if not settings.SUPABASE_URL or not settings.SUPABASE_SECRET_KEY:
            raise RuntimeError(
                "Supabase Storage credentials are missing."
            )

        client = create_client(
            settings.SUPABASE_URL,
            settings.SUPABASE_SECRET_KEY,
        )

        return client.storage.from_(
            getattr(settings, self.bucket_setting)
        )

    def _save(self, name, content):
        """Upload a file to Supabase."""

        content.seek(0)
        payload = content.read()

        mime = (
            getattr(content, "content_type", None)
            or "application/octet-stream"
        )

        self.bucket.upload(
            path=name,
            file=payload,
            file_options={
                "content-type": mime,
                "upsert": "false",
            },
        )

        return name

    def _open(self, name, mode="rb"):
        """Download a stored file."""

        if mode not in ("rb", "r"):
            raise ValueError(
                "Supabase Storage supports reading files only."
            )

        return ContentFile(
            self.bucket.download(name),
            name=name,
        )

    def delete(self, name):
        """Delete a file from Supabase."""

        if name:
            self.bucket.remove([name])

    def exists(self, name):
        """Check whether a file exists in Supabase Storage."""

        from storage3.exceptions import StorageApiError

        try:
            # Attempt to download the file.
            self.bucket.download(name)

            # The file exists.
            return True

        except StorageApiError as exc:
            # Supabase reports missing files using this message.
            error_message = str(
                getattr(exc, "message", "")
            ).strip().lower()

            # A missing file is normal before uploading.
            if error_message == "object not found":
                return False

            # Raise unexpected storage errors.
            raise

    def size(self, name):
        """Return the size of a stored file."""

        return len(self.bucket.download(name))


@deconstructible
class SupabasePublicStorage(_SupabaseStorage):
    """Storage for public profile pictures."""

    bucket_setting = "SUPABASE_PUBLIC_BUCKET"

    def url(self, name):
        """Return the public URL."""

        return self.bucket.get_public_url(name)


@deconstructible
class SupabasePrivateStorage(_SupabaseStorage):
    """Storage for private group attachments."""

    bucket_setting = "SUPABASE_PRIVATE_BUCKET"

    def url(self, name):
        """Prevent public access to private attachments."""

        raise ValueError(
            "Private group attachments do not have public URLs."
        )