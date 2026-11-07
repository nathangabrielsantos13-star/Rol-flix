"""Regras do editor de capas. O navegador desenha o pôster; aqui ele é validado e guardado.

A foto limpa fica separada do pôster: reabrir o editor parte dela, sem texto gravado por cima.
"""
import io
import os
import re

from django.core.files.base import ContentFile
from django.db import transaction
from PIL import Image

from .forms import check_image_upload
from .models import CoverDesign

WIDTH, HEIGHT = 1600, 1000  # Mesma proporção dos cartões do site.
MAX_FINAL_SIZE = 8 * 1024 * 1024
MAX_TITLE, MAX_SYNOPSIS = 80, 240
MIN_TITLE_SIZE, MAX_TITLE_SIZE = 60, 260
COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")

FONTS = ["Bebas Neue", "Anton", "Bangers", "Playfair Display", "Inter"]
FILTERS = {
    "none": "Sem filtro",
    "dark": "Escurecer",
    "light": "Clarear",
    "cinematic": "Cinematográfico",
    "ocean": "Azul do mar",
    "warm": "Pôr do sol",
    "vibrant": "Vibrante",
    "vintage": "Nostálgico",
    "mono": "Preto e branco",
}
POSITIONS = {
    "bottom-left": {"label": "Inferior esquerdo", "x": 0.06, "y": 0.93, "align": "left", "valign": "bottom"},
    "bottom-center": {"label": "Inferior central", "x": 0.5, "y": 0.93, "align": "center", "valign": "bottom"},
    "bottom-right": {"label": "Inferior direito", "x": 0.94, "y": 0.93, "align": "right", "valign": "bottom"},
    "center": {"label": "Centro", "x": 0.5, "y": 0.5, "align": "center", "valign": "middle"},
    "top-left": {"label": "Superior esquerdo", "x": 0.06, "y": 0.08, "align": "left", "valign": "top"},
    "top-center": {"label": "Superior central", "x": 0.5, "y": 0.08, "align": "center", "valign": "top"},
}
TEMPLATES = {
    "cinematic": {"label": "Cinematográfico", "font": "Bebas Neue", "title_size": 180, "color": "#ffffff", "accent": "#e50914", "filter": "cinematic", "position": "bottom-left"},
    "beach": {"label": "Praia", "font": "Playfair Display", "title_size": 130, "color": "#ffffff", "accent": "#7fd6ff", "filter": "ocean", "position": "center"},
    "adventure": {"label": "Aventura", "font": "Anton", "title_size": 150, "color": "#ffe9c7", "accent": "#ff9d2e", "filter": "warm", "position": "bottom-left"},
    "comedy": {"label": "Comédia", "font": "Bangers", "title_size": 170, "color": "#ffe600", "accent": "#ff3d81", "filter": "vibrant", "position": "top-center"},
}


class CoverError(Exception):
    """Problema que pode ser mostrado a quem está editando a capa."""


def default_config(album):
    template = {key: value for key, value in TEMPLATES["cinematic"].items() if key != "label"}
    position = {key: value for key, value in POSITIONS[template["position"]].items() if key != "label"}
    return {**template, **position, "template": "cinematic", "title": album.title, "synopsis": album.synopsis[:MAX_SYNOPSIS], "show_cast": True}


def clean_config(raw):
    """Aceita só os campos conhecidos, para o JSON guardado nunca ter conteúdo arbitrário."""
    if not isinstance(raw, dict):
        raise CoverError("Não foi possível ler as configurações da capa.")
    try:
        config = {
            "template": raw.get("template") if raw.get("template") in TEMPLATES else "",
            "position": raw.get("position") if raw.get("position") in POSITIONS else "",
            "title": str(raw["title"]).strip()[:MAX_TITLE],
            "synopsis": str(raw.get("synopsis", "")).strip()[:MAX_SYNOPSIS],
            "font": raw["font"],
            "title_size": int(raw["title_size"]),
            "color": raw["color"],
            "accent": raw["accent"],
            "filter": raw["filter"],
            "x": float(raw["x"]),
            "y": float(raw["y"]),
            "align": raw["align"],
            "valign": raw["valign"],
            "show_cast": raw.get("show_cast") is True,
        }
    except (KeyError, TypeError, ValueError):
        raise CoverError("Não foi possível ler as configurações da capa.")
    valid = (
        config["title"]
        and config["font"] in FONTS
        and config["filter"] in FILTERS
        and config["align"] in ("left", "center", "right")
        and config["valign"] in ("top", "middle", "bottom")
        and MIN_TITLE_SIZE <= config["title_size"] <= MAX_TITLE_SIZE
        and 0 <= config["x"] <= 1
        and 0 <= config["y"] <= 1
        and isinstance(config["color"], str) and COLOR.match(config["color"])
        and isinstance(config["accent"], str) and COLOR.match(config["accent"])
    )
    if not valid:
        raise CoverError("Confira o título e as opções da capa.")
    return config


def clean_final(upload):
    """Regrava o JPG recebido: o arquivo salvo nunca é o que o navegador enviou."""
    if upload is None or upload.size > MAX_FINAL_SIZE:
        raise CoverError("A imagem da capa não pôde ser recebida.")
    try:
        with Image.open(upload) as image:
            if image.format != "JPEG" or image.size != (WIDTH, HEIGHT):
                raise CoverError("A imagem da capa não pôde ser recebida.")
            buffer = io.BytesIO()
            image.convert("RGB").save(buffer, "JPEG", quality=90, optimize=True)
    except (OSError, ValueError, SyntaxError):
        raise CoverError("A imagem da capa não pôde ser recebida.")
    return ContentFile(buffer.getvalue())


def read_field(field):
    with field.open("rb") as source:
        return ContentFile(source.read())


def new_background(album, design, upload, media):
    """Decide de onde vem a foto limpa. Devolve (conteúdo, nome) ou None para manter a atual."""
    if upload is not None:
        from django import forms
        try:
            check_image_upload(upload)
        except forms.ValidationError as error:
            raise CoverError(error.messages[0])
        return upload, os.path.basename(upload.name)
    if media is not None:
        return read_field(media.file), os.path.basename(media.file.name)
    if design is not None:
        return None
    if album.cover:
        return read_field(album.cover), os.path.basename(album.cover.name)
    raise CoverError("Escolha uma imagem de fundo.")


def save_cover(album, final, config, upload=None, media=None):
    poster = clean_final(final)
    config = clean_config(config)
    design = CoverDesign.objects.filter(album=album).first()
    background = new_background(album, design, upload, media)
    # Nomes, não os campos: ao salvar, o Django troca o arquivo dentro do mesmo objeto.
    stale = [album.cover.name] if album.cover else []
    with transaction.atomic():
        if design is None:
            design = CoverDesign(album=album)
        elif background is not None:
            stale.append(design.background.name)
        if background is not None:
            design.background.save(background[1], background[0], save=False)
        design.config = config
        design.save()
        # Nome novo a cada versão: uma cópia antiga no navegador nunca aparece no lugar da nova.
        album.cover.save(f"capa-{album.pk}.jpg", poster, save=False)
        album.has_poster = True
        album.save(update_fields=["cover", "has_poster"])
    delete_files(album.cover.storage, stale, keep=album.cover.name)
    return design


def delete_files(storage, names, keep=""):
    for name in names:
        if name != keep:
            storage.delete(name)


def restore_photo(album):
    """Volta à foto limpa e descarta o pôster e as configurações."""
    design = CoverDesign.objects.filter(album=album).first()
    if design is None:
        return
    stale = [album.cover.name, design.background.name]
    album.cover.save(os.path.basename(design.background.name), read_field(design.background), save=False)
    album.has_poster = False
    album.save(update_fields=["cover", "has_poster"])
    design.delete()
    delete_files(album.cover.storage, stale, keep=album.cover.name)


def forget_design(album):
    """A capa foi trocada pelo formulário do álbum: o desenho antigo deixou de valer."""
    design = CoverDesign.objects.filter(album=album).first()
    if design is not None:
        background = design.background
        design.delete()
        background.storage.delete(background.name)
    if album.has_poster:
        album.has_poster = False
        album.save(update_fields=["has_poster"])
