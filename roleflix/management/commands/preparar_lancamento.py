from django.conf import settings
from django.contrib.sites.models import Site
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Grava o domínio do site e mostra o que ainda impede o lançamento."

    def handle(self, *args, **options):
        hosts = [host for host in settings.ALLOWED_HOSTS if host not in ("127.0.0.1", "localhost")]
        if hosts:
            # Os e-mails de confirmação usam este domínio. O padrão do Django é example.com.
            Site.objects.update_or_create(pk=settings.SITE_ID, defaults={"domain": hosts[0], "name": "Rolêflix"})
        problems = []
        if settings.DEBUG:
            problems.append("DJANGO_DEBUG precisa ser 0.")
        if not hosts:
            problems.append("Defina DJANGO_ALLOWED_HOSTS com o domínio.")
        if not settings.SECURE_SSL_REDIRECT:
            problems.append("Defina DJANGO_HTTPS=1.")
        if not getattr(settings, "EMAIL_HOST_USER", ""):
            problems.append("Sem EMAIL_HOST_USER, ninguém recebe o e-mail de confirmação do cadastro.")
        if not settings.ROLEFLIX_CONTACT_EMAIL:
            problems.append("Defina ROLEFLIX_CONTACT_EMAIL: ele aparece na política de privacidade.")
        for problem in problems:
            self.stdout.write(self.style.ERROR(f"PENDENTE: {problem}"))
        if not settings.ROLEFLIX_INVITE_CODE:
            self.stdout.write(self.style.WARNING("Aviso: cadastro aberto a qualquer pessoa (ROLEFLIX_INVITE_CODE vazio)."))
        if not problems:
            self.stdout.write(self.style.SUCCESS("Tudo pronto para o lançamento."))
