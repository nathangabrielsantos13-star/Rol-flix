"""Roda na publicação da Vercel: prepara o banco do Neon. Sem ele, o site segue como demonstração e não há o que fazer."""
import os

import django
from django.core.management import call_command

from config.conexoes import reconhecer


def main():
    reconhecer(os.environ)
    if not os.getenv("DATABASE_URL"):
        print("Sem DATABASE_URL: nada a preparar.")
        return
    # Migrações precisam de uma conexão direta: o pool do Neon troca de sessão entre os comandos.
    os.environ["DATABASE_URL"] = os.getenv("DATABASE_URL_UNPOOLED") or os.environ["DATABASE_URL"]
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    django.setup()
    call_command("migrate", interactive=False)
    call_command("createcachetable")
    domain = os.getenv("VERCEL_PROJECT_PRODUCTION_URL")
    if domain:
        from django.conf import settings
        from django.contrib.sites.models import Site
        Site.objects.update_or_create(pk=settings.SITE_ID, defaults={"domain": domain, "name": "Rolêflix"})


if __name__ == "__main__":
    main()
