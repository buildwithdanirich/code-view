from django.conf import settings
from django.core.files.storage import FileSystemStorage


class PrivateGroupStorage(FileSystemStorage):
    """
    Store group chat attachments outside the public media folder.

    Files are accessed through authorized Django views,
    not through public media URLs.
    """

    def __init__(self, *args, **kwargs):

        # Store attachments in our private directory.
        kwargs.setdefault(
            "location",
            settings.PRIVATE_MEDIA_ROOT,
        )

        # Do not provide a public media URL.
        kwargs.setdefault(
            "base_url",
            None,
        )

        # Initialize Django's FileSystemStorage.
        super().__init__(*args, **kwargs)

    def url(self, name):
        """
        Prevent direct public URL generation.
        """
        raise ValueError(
            "Private group attachments do not have public URLs."
        )