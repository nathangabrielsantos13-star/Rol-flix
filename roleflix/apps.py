import mimetypes

from django.apps import AppConfig

class RoleflixConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "roleflix"

    def ready(self):
        # O tipo de arquivo dependeria do sistema: no Windows e em alguns servidores estes faltam.
        for content_type, extension in [
            ("image/webp", ".webp"), ("video/mp4", ".mp4"), ("video/mp4", ".m4v"),
            ("video/webm", ".webm"), ("video/quicktime", ".mov"),
        ]:
            mimetypes.add_type(content_type, extension)
