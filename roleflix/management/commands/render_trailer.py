from django.core.management.base import BaseCommand

from roleflix import trailers
from roleflix.models import Trailer


class Command(BaseCommand):
    help = "Gera um trailer na fila. O site dispara este comando em segundo plano."

    def add_arguments(self, parser):
        parser.add_argument("trailer_id", type=int)

    def handle(self, *args, trailer_id, **options):
        # A troca de status garante que dois processos nunca gerem o mesmo trailer.
        if Trailer.objects.filter(pk=trailer_id, status=Trailer.PENDING).update(status=Trailer.PROCESSING):
            trailers.render(Trailer.objects.select_related("album__owner").get(pk=trailer_id))
