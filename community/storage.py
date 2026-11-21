"""Private group attachment storage: local in DEBUG, Supabase in production."""
from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible

from .supabase_storage import SupabasePrivateStorage


@deconstructible
class PrivateGroupStorage(FileSystemStorage):
    """Stable migration-compatible storage wrapper with private access."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("location", settings.PRIVATE_MEDIA_ROOT)
        kwargs.setdefault("base_url", None)
        super().__init__(*args, **kwargs)
        self._remote = None if settings.DEBUG else SupabasePrivateStorage()

    def _open(self, name, mode="rb"):
        return self._remote._open(name, mode) if self._remote else super()._open(name, mode)

    def _save(self, name, content):
        return self._remote._save(name, content) if self._remote else super()._save(name, content)

    def exists(self, name):
        return self._remote.exists(name) if self._remote else super().exists(name)

    def delete(self, name):
        return self._remote.delete(name) if self._remote else super().delete(name)

    def size(self, name):
        return self._remote.size(name) if self._remote else super().size(name)

    def url(self, name):
        raise ValueError("Private group attachments do not have public URLs.")
