"""Guarda os arquivos no Vercel Blob. A loja é privada: tudo continua passando pela checagem de protected_media."""
import io
import mimetypes
import os

from django.conf import settings
from django.core.files.base import File
from django.core.files.storage import Storage
from django.utils.crypto import get_random_string
from django.utils.deconstruct import deconstructible
from django.utils.encoding import filepath_to_uri
from vercel.blob import sync as blob


@deconstructible
class BlobStorage(Storage):
    def _open(self, name, mode="rb"):
        try:
            return File(io.BytesIO(blob.get_blob(name, access="private").body), name)
        except blob.BlobNotFoundError:
            raise
        except blob.BlobError as error:  # Como um erro de disco: inclui a loja bloqueada por passar do plano grátis.
            raise OSError(str(error)) from error

    def _save(self, name, content):
        content.seek(0)
        try:
            blob.put_blob(name, content.read(), access="private",
                          content_type=mimetypes.guess_type(name)[0] or "application/octet-stream")
        except blob.BlobError as error:
            raise OSError(str(error)) from error
        return name

    def get_available_name(self, name, max_length=None):
        # Um sufixo aleatório dispensa perguntar à loja se o nome existe, o que gastaria a cota de operações.
        root, extension = os.path.splitext(name.replace("\\", "/"))
        suffix = f"_{get_random_string(12)}{extension}"
        return root[:max_length - len(suffix)] + suffix if max_length else root + suffix

    def delete(self, name):
        blob.delete_blob(name)

    def exists(self, name):
        try:
            blob.head_blob(name)
        except blob.BlobNotFoundError:
            return False
        return True

    def size(self, name):
        return blob.head_blob(name).size

    def url(self, name):
        return f"{settings.MEDIA_URL}{filepath_to_uri(name)}"
