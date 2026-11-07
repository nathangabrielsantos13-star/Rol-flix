import logging
import threading

from django.conf import settings
from django.http import HttpResponse

from . import demo

logger = logging.getLogger(__name__)


class DemoSetupMiddleware:
    """Prepara o banco temporário na primeira visita: funciona como quer que a Vercel carregue o site."""

    ready = False
    lock = threading.Lock()

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if settings.ROLEFLIX_DEMO and not DemoSetupMiddleware.ready:
            with DemoSetupMiddleware.lock:
                if not DemoSetupMiddleware.ready:
                    try:
                        demo.prepare()
                    except Exception as error:
                        # Só existe na demonstração: mostra a causa, em vez de um erro 500 sem pista.
                        logger.exception("A demonstração não iniciou")
                        message = f"A demonstração não iniciou: {type(error).__name__}: {error}"[:300]
                        return HttpResponse(message, status=503, content_type="text/plain; charset=utf-8")
                    DemoSetupMiddleware.ready = True
        return self.get_response(request)
