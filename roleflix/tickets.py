"""Desenha o Ingresso do Rolê com Pillow. É uma lembrança: não tem QR, código de barras nem valor de entrada."""
import io
from dataclasses import dataclass

from django.contrib.staticfiles import finders
from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from django.db.models import Max
from django.utils import timezone
from PIL import Image, ImageColor, ImageDraw, ImageFilter, ImageFont, ImageOps

from .models import Ticket
from .retrospective import album_date

WIDTH, HEIGHT = 1600, 620
CARD = (24, 20, WIDTH - 24, HEIGHT - 20)
ART_RIGHT = 548
STUB_LEFT = 1236
PREVIEW_WIDTH = 1000
MAX_PER_PERSON = 12  # Por álbum: evita encher o disco com variações.
MAX_CAST = 6


@dataclass(frozen=True)
class Style:
    paper: str
    ink: str
    muted: str
    accent: str
    title_font: str
    tint: tuple  # Cor e força aplicadas sobre a capa.
    grayscale: bool = False


STYLES = {
    Ticket.CLASSIC: Style("#111111", "#ffffff", "#a8a8a8", "#e50914", "BebasNeue", ("#000000", 0.1)),
    Ticket.VINTAGE: Style("#efe3c8", "#3a2a1c", "#7a6650", "#a5482a", "PlayfairDisplay-Bold", ("#b5843f", 0.35), True),
    Ticket.PREMIUM: Style("#0f1115", "#f4efe3", "#a59f91", "#c9a24b", "PlayfairDisplay-Bold", ("#0f1115", 0.25)),
    Ticket.RETRO: Style("#ffcf3f", "#2a1a4a", "#5d4a7a", "#e5394a", "Bangers", ("#ff7a59", 0.22)),
}
TITLE_SIZES = (92, 78, 66, 56, 46)


def is_upcoming(album, today=None):
    return bool(album.event_date and album.event_date > (today or timezone.localdate()))


def default_tagline(album):
    if is_upcoming(album):
        return "Contagem regressiva para o próximo rolê."
    return album.synopsis[:Ticket.MAX_TAGLINE] or "Uma aventura para guardar na memória."


def font(name, size):
    return ImageFont.truetype(finders.find(f"fonts/ttf/{name}.ttf"), size)


def wrap(draw, text, type_font, width):
    lines, current = [], ""
    for word in text.split():
        attempt = f"{current} {word}".strip()
        if current and draw.textlength(attempt, font=type_font) > width:
            lines.append(current)
            current = word
        else:
            current = attempt
    return [*lines, current] if current else lines


def shorten(draw, text, type_font, width):
    if draw.textlength(text, font=type_font) <= width:
        return text
    while text and draw.textlength(f"{text}…", font=type_font) > width:
        text = text[:-1]
    return f"{text.rstrip()}…"


def fit_title(draw, title, style, width):
    """Diminui a letra até o título caber em duas linhas; se não der, corta com reticências."""
    for size in TITLE_SIZES:
        type_font = font(style.title_font, size)
        lines = wrap(draw, title, type_font, width)
        if len(lines) <= 2 and all(draw.textlength(line, font=type_font) <= width for line in lines):
            return type_font, lines
    return type_font, [lines[0], shorten(draw, " ".join(lines[1:]), type_font, width)]


def card_mask():
    """Recorta os cantos e os semicírculos da serrilha, com bordas suaves."""
    scale = 2
    mask = Image.new("L", (WIDTH * scale, HEIGHT * scale), 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle([value * scale for value in CARD], 30 * scale, fill=255)
    for y in (CARD[1], CARD[3]):
        draw.ellipse([(STUB_LEFT - 22) * scale, (y - 22) * scale, (STUB_LEFT + 22) * scale, (y + 22) * scale], fill=0)
    return mask.resize((WIDTH, HEIGHT), Image.LANCZOS)


def cover_art(album, style):
    size = (ART_RIGHT - CARD[0], CARD[3] - CARD[1])
    art = None
    if album.cover:
        try:
            with album.backdrop.open("rb") as stream, Image.open(stream) as image:
                art = ImageOps.fit(ImageOps.exif_transpose(image).convert("RGB"), size)
        except (OSError, ValueError, SyntaxError):
            art = None
    if art is None:
        art = Image.linear_gradient("L").resize(size).convert("RGB")
        art = ImageOps.colorize(art.convert("L"), "#101010", style.accent)
    if style.grayscale:
        art = ImageOps.grayscale(art).convert("RGB")
    color, strength = style.tint
    return Image.blend(art, Image.new("RGB", size, color), strength)


def avatar(person, size, color):
    circle = Image.new("RGB", (size, size), color)
    profile = getattr(person, "profile", None)
    if profile is not None and profile.avatar:
        try:
            with profile.avatar.open("rb") as stream, Image.open(stream) as image:
                circle = ImageOps.fit(ImageOps.exif_transpose(image).convert("RGB"), (size, size))
        except (OSError, ValueError, SyntaxError):
            profile = None
    if profile is None or not profile.avatar:
        draw = ImageDraw.Draw(circle)
        name = person.first_name or person.username
        draw.text((size / 2, size / 2), name[0].upper(), font=font("Inter-Bold", size // 2), fill="#ffffff", anchor="mm")
    mask = Image.new("L", (size * 2, size * 2), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size * 2, size * 2), fill=255)
    return circle, mask.resize((size, size), Image.LANCZOS)


def cast_names(people):
    names = [person.first_name or person.username for person in people]
    if len(names) == 1:
        return names[0]
    if len(names) <= 3:
        return ", ".join(names[:-1]) + f" e {names[-1]}"
    return f"{', '.join(names[:3])} e mais {len(names) - 3}"


def field(draw, x, y, label, value, style, accent, width):
    draw.text((x, y), label, font=font("Inter-Bold", 18), fill=accent)
    draw.text((x, y + 26), shorten(draw, value, font("Inter-Bold", 28), width), font=font("Inter-Bold", 28), fill=style.ink)


def render(album, style_key, accent, tagline, number, upcoming):
    """Devolve a imagem RGBA do ingresso."""
    style = STYLES[style_key]
    accent = accent or style.accent
    ticket = Image.new("RGBA", (WIDTH, HEIGHT), style.paper)
    ticket.paste(cover_art(album, style), (CARD[0], CARD[1]))
    draw = ImageDraw.Draw(ticket)
    left, right = ART_RIGHT + 42, STUB_LEFT - 34
    width = right - left

    logo = font("Inter-Bold", 34)
    draw.text((left, 46), "ROLÊ", font=logo, fill=style.ink)
    draw.text((left + draw.textlength("ROLÊ", font=logo), 46), "FLIX", font=logo, fill=accent)
    label = "PRÉ-ESTREIA" if upcoming else "INGRESSO ESPECIAL"
    draw.text((right, 54), label, font=font("Inter-Bold", 20), fill=accent, anchor="ra")

    title_font, lines = fit_title(draw, album.title, style, width)
    y = 112
    for line in lines:
        draw.text((left, y), line, font=title_font, fill=style.ink)
        y += int(title_font.size * 1.08)
    y += 14
    # A frase ocupa só o que o título deixou livre, para nunca encostar nos campos abaixo.
    tagline_font = font("Inter-Medium", 25)
    tagline_lines = wrap(draw, tagline, tagline_font, width)
    room = max(1, (360 - y) // 33)
    if len(tagline_lines) > room:
        tagline_lines = [*tagline_lines[:room - 1], shorten(draw, " ".join(tagline_lines[room - 1:]), tagline_font, width)]
    for line in tagline_lines:
        draw.text((left, y), line, font=tagline_font, fill=style.muted)
        y += 33

    date = album.event_date.strftime("%d/%m/%Y") if album.event_date else "Sem data"
    field(draw, left, 374, "DATA", date, style, accent, 190)
    field(draw, left + 230, 374, "LOCAL", album.location or "A definir", style, accent, width - 230)

    people = album.cast
    draw.text((left, 462), "ELENCO", font=font("Inter-Bold", 18), fill=accent)
    x = left
    for person in people[:MAX_CAST]:
        circle, mask = avatar(person, 58, accent)
        ring = Image.new("L", (64, 64), 0)
        ImageDraw.Draw(ring).ellipse((0, 0, 63, 63), fill=255)
        ticket.paste(style.paper, (x - 3, 487), ring)
        ticket.paste(circle, (x, 490), mask)
        x += 44
    draw.text((x + 34, 519), shorten(draw, cast_names(people), font("Inter-Medium", 24), right - x - 34), font=font("Inter-Medium", 24), fill=style.ink, anchor="lm")

    for y in range(CARD[1] + 30, CARD[3] - 30, 22):
        draw.line((STUB_LEFT, y, STUB_LEFT, y + 11), fill=style.muted, width=3)
    center = (STUB_LEFT + CARD[2]) // 2
    draw.text((center, 62), "INGRESSO", font=font("Inter-Bold", 22), fill=accent, anchor="ma")
    draw.text((center, 100), number, font=font("Inter-Bold", 36), fill=style.ink, anchor="ma")
    year = str(album_date(album).year)
    draw.text((center, 226), year, font=font(style.title_font, 118), fill=accent, anchor="mm")
    for index, line in enumerate(("UMA MEMÓRIA,", "PARA SEMPRE.")):
        draw.text((center, 390 + index * 34), line, font=font("Inter-Bold", 26), fill=style.ink, anchor="ma")
    for index, line in enumerate(("Lembrança digital.", "Não vale como entrada.")):
        draw.text((center, 508 + index * 26), line, font=font("Inter-Medium", 19), fill=style.muted, anchor="ma")

    ticket.putalpha(card_mask())
    return ticket


def png_bytes(image):
    buffer = io.BytesIO()
    image.save(buffer, "PNG", optimize=True)
    return buffer.getvalue()


def preview_bytes(album, style_key, accent, tagline):
    image = render(album, style_key, accent, tagline, "RF-0000-000", is_upcoming(album))
    return png_bytes(image.resize((PREVIEW_WIDTH, round(HEIGHT * PREVIEW_WIDTH / WIDTH)), Image.LANCZOS))


def pdf_bytes(ticket):
    """PDF em fundo branco, com largura de folha A4 deitada."""
    with ticket.image.open("rb") as stream, Image.open(stream) as image:
        page = Image.new("RGB", image.size, "#ffffff")
        rgba = image.convert("RGBA")
        page.paste(rgba, mask=rgba.getchannel("A"))
    buffer = io.BytesIO()
    page.save(buffer, "PDF", resolution=135)
    return buffer.getvalue()


def create_ticket(album, user, style_key, accent, tagline):
    """A numeração é sequencial por ano; se duas pessoas colidirem, tenta o próximo número."""
    year = album_date(album).year
    upcoming = is_upcoming(album)
    for _ in range(5):
        sequence = (Ticket.objects.filter(year=year).aggregate(last=Max("sequence"))["last"] or 0) + 1
        number = f"RF-{year}-{sequence:03}"
        content = png_bytes(render(album, style_key, accent, tagline, number, upcoming))
        ticket = Ticket(album=album, created_by=user, style=style_key, accent=accent, tagline=tagline, year=year, sequence=sequence, upcoming=upcoming)
        ticket.image.save(f"{number.lower()}.png", ContentFile(content), save=False)
        try:
            with transaction.atomic():
                ticket.save()
            return ticket
        except IntegrityError:
            ticket.image.storage.delete(ticket.image.name)
    raise IntegrityError("Não foi possível numerar o ingresso.")


def delete_ticket(ticket):
    storage, name = ticket.image.storage, ticket.image.name
    ticket.delete()
    storage.delete(name)
