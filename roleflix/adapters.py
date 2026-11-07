import logging
import smtplib

from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.conf import settings

logger = logging.getLogger(__name__)


class ResilientAccountAdapter(DefaultAccountAdapter):
    """Uma falha do serviço de e-mail não pode dar erro depois de a conta já ter sido criada."""

    def send_mail(self, template_prefix, email, context):
        try:
            super().send_mail(template_prefix, email, context)
        except (smtplib.SMTPException, OSError):
            logger.exception("Não foi possível enviar o e-mail %s", template_prefix)


class InviteOnlySocialAdapter(DefaultSocialAccountAdapter):
    """Com convite ativo, o Google só entra em contas que já existem: senão ele furaria o código."""

    def is_open_for_signup(self, request, sociallogin):
        return not settings.ROLEFLIX_INVITE_CODE
