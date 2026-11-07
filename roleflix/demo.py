"""Modo demonstração da Vercel: o disco é temporário, então o banco nasce de novo a cada reinício."""
import io
from datetime import date

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import User
from django.contrib.staticfiles import finders
from django.core.files.base import ContentFile
from django.core.management import call_command
from PIL import Image

from .models import Album, AlbumParticipant, MediaItem, Notification, Profile

DEMO_USERNAME = "demo"
# Cada instância da Vercel cria o próprio banco, e a sessão de uma precisa valer na outra.
# Por isso conta e arquivos são iguais em todas, e a senha usa um sal fixo: o resultado é sempre o mesmo.
DEMO_EMAIL = "demo@roleflix.invalid"
DEMO_PASSWORD = "roleflix-teste"
ALBUMS = [
    ("Guaratuba 2026", "Sol, mar e muita risada.", date(2026, 1, 10), "Guaratuba, Paraná", -25.88, -48.57, (0.05, 0.1)),
    ("Carnaval em Ouro Preto", "Quatro dias sem dormir.", date(2026, 2, 14), "Ouro Preto, Minas Gerais", -20.38, -43.5, (0.3, 0.2)),
    ("Festa da Bia", "30 anos em grande estilo.", date(2026, 8, 20), "", None, None, (0.15, 0.35)),
    ("Mochilão no Chile", "Atacama, frio e estrelas.", date(2025, 11, 12), "San Pedro de Atacama, Chile", -22.91, -68.2, (0.4, 0.05)),
    ("Lisboa com a turma", "Pastel de nata no café da manhã.", date(2024, 6, 3), "Lisboa, Portugal", 38.72, -9.14, (0.2, 0.0)),
]


def cover(position, name):
    """Recorta a paisagem do site: assim a demonstração não depende de nenhuma foto de verdade."""
    path = finders.find("img/hero-landscape.jpg")
    if path is None:  # A imagem pode não entrar no pacote do servidor: um fundo liso não pode impedir a demonstração.
        return solid_cover(position, name)
    with Image.open(path) as source:
        image = source.convert("RGB")
    width, height = image.size
    left, top = int(width * position[0]), int(height * position[1])
    crop = image.crop((left, top, left + int(width * 0.55), top + int(height * 0.6))).resize((1000, 620))
    buffer = io.BytesIO()
    crop.save(buffer, "JPEG", quality=80)
    return ContentFile(buffer.getvalue(), name=name)


def solid_cover(position, name):
    image = Image.new("RGB", (1000, 620), (70 + int(position[0] * 300), 40, 50 + int(position[1] * 300)))
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=80)
    return ContentFile(buffer.getvalue(), name=name)


def seed():
    """Cria a conta e os álbuns de exemplo. Pode rodar de novo sem duplicar nada."""
    if Album.objects.filter(owner__username=DEMO_USERNAME).exists():
        return User.objects.get(username=DEMO_USERNAME)
    user, _ = User.objects.get_or_create(username=DEMO_USERNAME, defaults={"first_name": "Visitante", "email": DEMO_EMAIL, "password": make_password(DEMO_PASSWORD, salt="roleflixdemo")})
    Profile.objects.get_or_create(user=user)
    friends = [User.objects.get_or_create(username=name, defaults={"first_name": first})[0] for name, first in (("beatriz", "Beatriz"), ("leo", "Léo"))]
    albums = {}
    for index, (title, synopsis, day, location, latitude, longitude, position) in enumerate(ALBUMS):
        owner = friends[0] if index == 2 else user
        album = Album.objects.create(owner=owner, title=title, synopsis=synopsis, event_date=day, location=location,
                                     latitude=latitude, longitude=longitude, visibility=Album.SHARED, cover=cover(position, f"demo-capa-{index}.jpg"))
        for person in (user, *friends):
            if person != owner:
                AlbumParticipant.objects.get_or_create(album=album, user=person)
        MediaItem.objects.create(album=album, kind=MediaItem.PHOTO, uploaded_by=owner, file=cover((position[1], position[0]), f"demo-foto-{index}.jpg"))
        albums[title] = album
    Notification.objects.create(recipient=user, actor=friends[0], album=albums["Festa da Bia"])
    return user


def prepare():
    if settings.ROLEFLIX_DEMO:
        call_command("migrate", verbosity=0, interactive=False)
        seed()
