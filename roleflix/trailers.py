"""Monta o trailer de um álbum com FFmpeg, num processo separado do site.

Cada foto ou vídeo vira um trecho curto; depois os trechos são unidos com transições
que caem nas batidas da música. Aberturas e fotos passam antes pelo Pillow.
"""
import logging
import math
import os
import re
import subprocess
import sys
import tempfile
from array import array
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

import imageio_ffmpeg
from django.conf import settings
from django.contrib.staticfiles import finders
from django.core.files import File
from django.utils import timezone
from django.utils.text import slugify
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from .models import MediaItem, Trailer

logger = logging.getLogger(__name__)

WIDTH, HEIGHT = 1280, 720
FPS = 30
INTRO, OUTRO = 3.0, 4.0
MAX_SHOT = 6.0
MAX_ACTIVE = 2  # Trailers gerados ao mesmo tempo em todo o site.
STALE_AFTER = timedelta(minutes=30)
STEP_TIMEOUT = 600

# Arquivos enviados podem fingir ser vídeo: uma playlist com extensão .mp4 faria o FFmpeg
# ler arquivos do servidor. Só estes leitores, e só arquivos locais, são aceitos.
SAFE_INPUT = ("-protocol_whitelist", "file", "-format_whitelist", "mov,mp4,m4a,3gp,3g2,mj2,matroska,webm,mp3,aac,wav,ogg,flac")


@dataclass(frozen=True)
class Style:
    shot: float  # Segundos desejados por foto ou vídeo.
    transition: float
    transitions: tuple
    zoom: float
    grade: str


STYLES = {
    Trailer.CINEMATIC: Style(3.2, 0.6, ("fade",), 0.0006, "eq=contrast=1.08:saturation=0.9,colorbalance=rs=-0.03:bs=0.04:rh=0.04:bh=-0.03,drawbox=y=0:w=iw:h=54:color=black:t=fill,drawbox=y=ih-54:w=iw:h=54:color=black:t=fill"),
    Trailer.FUN: Style(2.0, 0.35, ("slideleft", "circleopen", "wipeup", "slideright"), 0.0012, "eq=contrast=1.05:saturation=1.3"),
    Trailer.NOSTALGIC: Style(3.6, 0.9, ("dissolve", "fade"), 0.0005, "eq=saturation=0.72:contrast=0.97,colorbalance=rm=0.08:gm=0.02:bm=-0.09,vignette=PI/4.5"),
}


@dataclass(frozen=True)
class Track:
    label: str
    bpm: int


MUSIC = {
    "aurora": Track("Aurora, épica e lenta", 76),
    "festa": Track("Festa, animada", 124),
    "estrada": Track("Estrada, suave", 92),
}
STYLE_MUSIC = {Trailer.CINEMATIC: "aurora", Trailer.FUN: "festa", Trailer.NOSTALGIC: "estrada"}


class TrailerError(Exception):
    """Falha com mensagem que pode ser mostrada a quem pediu o trailer."""


def ffmpeg(*args):
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        done = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-y", "-nostdin", *map(str, args)],
                              capture_output=True, timeout=STEP_TIMEOUT, creationflags=flags)
    except subprocess.TimeoutExpired:
        raise TrailerError("A geração demorou demais. Tente com menos fotos e vídeos.")
    if done.returncode:
        logger.error("FFmpeg falhou: %s", done.stderr.decode("utf-8", "replace")[-1500:])
        raise TrailerError("Não foi possível montar o vídeo.")
    return done


def video_duration(path):
    """Lê a duração; devolve None quando o arquivo não é um vídeo legível."""
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        done = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-nostdin", *SAFE_INPUT, "-i", str(path)],
                              capture_output=True, timeout=60, creationflags=flags)
    except subprocess.TimeoutExpired:
        return None
    info = done.stderr.decode("utf-8", "replace")
    found = re.search(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", info)
    if not found or "Video:" not in info:
        return None
    hours, minutes, seconds = found.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def evenly_pick(items, limit):
    """Reduz a lista mantendo o começo, o meio e o fim do rolê."""
    if len(items) <= limit:
        return list(items)
    return [items[i * len(items) // limit] for i in range(limit)]


def plan_cuts(count, target, style, period, phase=0.0):
    """Instantes das trocas de cena, sempre em batidas: abertura, cada item e encerramento."""
    content = max(period, target - INTRO - OUTRO - period)
    shot = min(content / count, MAX_SHOT)
    step = max(1, int(shot / period)) * period
    first = phase + math.ceil((INTRO - phase) / period) * period
    return [0.0, *(first + i * step for i in range(count + 1))]


def beat_grid(energy, seconds_per_window):
    """Acha o intervalo e a posição das batidas a partir da energia do áudio em janelas curtas."""
    flux = [max(0.0, b - a) for a, b in zip(energy, energy[1:])]
    lags = range(max(1, int(0.35 / seconds_per_window)), int(0.86 / seconds_per_window) + 1)  # 70 a 170 BPM.
    if len(flux) < lags[-1] * 4 or not any(flux):
        return 0.5, 0.0
    match = lambda n: sum(a * b for a, b in zip(flux, flux[n:])) / (len(flux) - n)
    lag = max(lags, key=match)
    # Medir oito batidas de uma vez divide o erro por oito: sem isso, os cortes saem do ritmo com o tempo.
    long_lag = max(range(lag * 8 - 8, lag * 8 + 9), key=match) if len(flux) > lag * 16 else lag * 8
    period = long_lag / 8 * seconds_per_window
    phase = max(range(lag), key=lambda start: sum(flux[start::lag]))
    return period, (phase + 1) * seconds_per_window


def analyse_music(path):
    """Estima as batidas de uma música enviada, lendo só o primeiro minuto."""
    with tempfile.TemporaryDirectory(prefix="roleflix-audio-") as folder:
        raw = Path(folder) / "audio.raw"
        try:
            ffmpeg(*SAFE_INPUT, "-t", 60, "-i", path, "-vn", "-ac", 1, "-ar", 8000, "-f", "s16le", raw)
        except TrailerError:
            raise TrailerError("Não consegui ler a música enviada. Tente outro arquivo.")
        samples = array("h")
        samples.frombytes(raw.read_bytes()[: raw.stat().st_size // 2 * 2])
    if not samples:
        raise TrailerError("Não consegui ler a música enviada. Tente outro arquivo.")
    if sys.byteorder == "big":
        samples.byteswap()
    size = 256
    energy = [sum(abs(s) for s in samples[i:i + size]) / size for i in range(0, len(samples) - size, size)]
    return beat_grid(energy, size / 8000)


def load_font(size):
    return ImageFont.truetype(finders.find("fonts/ttf/Inter-Bold.ttf"), size)  # Fonte do projeto: o servidor pode não ter nenhuma.


def wrap_text(draw, text, font, width):
    lines, current = [], ""
    for word in text.split():
        attempt = f"{current} {word}".strip()
        if current and draw.textlength(attempt, font=font) > width:
            lines.append(current)
            current = word
        else:
            current = attempt
    return [*lines, current] if current else lines


def fit_title(draw, text, width):
    """Diminui a letra até o título caber em no máximo três linhas."""
    for size in (92, 76, 62, 50, 40):
        font = load_font(size)
        lines = wrap_text(draw, text, font, width)
        if len(lines) <= 3 and all(draw.textlength(line, font=font) <= width for line in lines):
            return font, lines
    return font, lines[:3]


def centered(draw, y, text, font, fill):
    draw.text(((WIDTH - draw.textlength(text, font=font)) / 2, y), text, font=font, fill=fill)


def cover_background(album):
    canvas = Image.new("RGB", (WIDTH, HEIGHT), (9, 9, 9))
    if album.cover:
        try:
            with album.cover.open("rb") as source, Image.open(source) as image:
                blurred = ImageOps.fit(ImageOps.exif_transpose(image).convert("RGB"), (WIDTH, HEIGHT)).filter(ImageFilter.GaussianBlur(14))
            canvas = Image.blend(canvas, blurred, 0.35)
        except (OSError, ValueError):
            pass  # Sem capa legível, a abertura fica em fundo preto.
    return canvas


def opening_card(album, path):
    canvas = cover_background(album)
    draw = ImageDraw.Draw(canvas)
    font, lines = fit_title(draw, album.title, WIDTH - 200)
    line_height = int(font.size * 1.15)
    y = (HEIGHT - line_height * len(lines)) // 2
    centered(draw, y - 56, "UM FILME ORIGINAL ROLÊFLIX", load_font(24), (229, 9, 20))
    for line in lines:
        centered(draw, y, line, font, (255, 255, 255))
        y += line_height
    details = " • ".join(filter(None, [album.event_date.strftime("%d/%m/%Y") if album.event_date else "", album.location]))
    if details:
        centered(draw, y + 22, details[:90], load_font(26), (200, 200, 200))
    canvas.save(path)


def closing_card(album, path):
    canvas = Image.new("RGB", (WIDTH, HEIGHT), (9, 9, 9))
    draw = ImageDraw.Draw(canvas)
    logo = load_font(84)
    left = (WIDTH - draw.textlength("ROLÊFLIX", font=logo)) / 2
    draw.text((left, 210), "ROLÊ", font=logo, fill=(255, 255, 255))
    draw.text((left + draw.textlength("ROLÊ", font=logo), 210), "FLIX", font=logo, fill=(229, 9, 20))
    names = [person.first_name or person.username for person in album.cast]
    credits = ", ".join(names[:8]) + (f" e mais {len(names) - 8}" if len(names) > 8 else "")
    y = 340
    centered(draw, y, "ESTRELANDO", load_font(22), (229, 9, 20))
    for line in wrap_text(draw, credits, load_font(32), WIDTH - 240)[:2]:
        y += 44
        centered(draw, y, line, load_font(32), (255, 255, 255))
    centered(draw, y + 76, "Suas histórias merecem virar filme.", load_font(24), (170, 170, 170))
    canvas.save(path)


def photo_frame(source, path):
    """Prepara a foto em dobro do tamanho, para o movimento sair suave; a sobra vira fundo desfocado."""
    size = (WIDTH * 2, HEIGHT * 2)
    with source.open("rb") as stream, Image.open(stream) as image:
        picture = ImageOps.exif_transpose(image).convert("RGB")
    canvas = ImageOps.fit(picture, size).filter(ImageFilter.GaussianBlur(40))
    scale = min(size[0] / picture.width, size[1] / picture.height)
    picture = picture.resize((round(picture.width * scale), round(picture.height * scale)))
    canvas.paste(picture, ((size[0] - picture.width) // 2, (size[1] - picture.height) // 2))
    canvas.save(path, quality=92)


def photo_segment(frame, target, seconds, index, style):
    frames = round(seconds * FPS)
    center = "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
    moves = (
        f"z='1+{style.zoom}*on':{center}",
        f"z='{1 + style.zoom * frames}-{style.zoom}*on':{center}",
        f"z=1.12:x='(iw-iw/zoom)*on/{frames}':y='ih/2-(ih/zoom/2)'",
    )
    ffmpeg("-i", frame, "-vf", f"zoompan={moves[index % 3]}:d={frames}:s={WIDTH}x{HEIGHT}:fps={FPS},{style.grade},format=yuv420p,setsar=1",
           "-frames:v", frames, *ENCODE, target)


def video_segment(source, duration, target, seconds, style):
    start = duration * 0.1 if duration > seconds * 1.5 else 0
    graph = (f"[0:v]split=2[a][b];[a]scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,crop={WIDTH}:{HEIGHT},boxblur=20:2[bg];"
             f"[b]scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,fps={FPS},"
             f"tpad=stop_mode=clone:stop_duration={seconds:.3f},{style.grade},format=yuv420p,setsar=1[v]")
    ffmpeg(*SAFE_INPUT, "-ss", f"{start:.3f}", "-t", f"{seconds:.3f}", "-i", source, "-filter_complex", graph, "-map", "[v]",
           "-an", "-frames:v", round(seconds * FPS), *ENCODE, target)


def card_segment(image, target, seconds, fade):
    frames = round(seconds * FPS)
    ffmpeg("-loop", 1, "-i", image, "-vf", f"fps={FPS},{fade.format(last=frames - 20)},format=yuv420p,setsar=1", "-frames:v", frames, *ENCODE, target)


# Trechos intermediários: rápidos e com pouca perda, pois serão recodificados na união.
ENCODE = ("-c:v", "libx264", "-preset", "veryfast", "-crf", 18, "-video_track_timescale", 30000)


def join_segments(segments, cuts, total, style, music, music_is_upload, target):
    graph, label = [], "0:v"
    for i in range(1, len(segments)):
        name = style.transitions[i % len(style.transitions)]
        next_label = f"v{i}"
        graph.append(f"[{label}][{i}:v]xfade=transition={name}:duration={style.transition}:offset={cuts[i]:.3f}[{next_label}]")
        label = next_label
    inputs = [arg for segment in segments for arg in ("-i", segment)]
    music_input = [*(SAFE_INPUT if music_is_upload else ()), "-stream_loop", -1, "-i", music]
    ffmpeg(*inputs, *music_input, "-filter_complex", ";".join(graph), "-map", f"[{label}]", "-map", f"{len(segments)}:a:0",
           "-af", f"afade=t=in:d=0.4,afade=t=out:st={total - 2.5:.3f}:d=2.5", "-t", f"{total:.3f}",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", 23, "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", target)


def usable_items(trailer):
    """Itens na ordem escolhida, sem os que sumiram ou não abrem."""
    found = MediaItem.objects.filter(album=trailer.album, pk__in=trailer.media_ids).in_bulk()
    usable = []
    for pk in trailer.media_ids:
        item = found.get(pk)
        if item is None or not item.file.storage.exists(item.file.name):
            continue
        duration = None
        if item.kind == MediaItem.VIDEO:
            duration = video_duration(item.file.path)
            if not duration:
                continue
        elif not photo_is_readable(item.file):
            continue
        usable.append((item, duration))
    return usable


def photo_is_readable(source):
    try:
        with source.open("rb") as stream, Image.open(stream) as image:
            image.load()
        return True
    except (OSError, ValueError, SyntaxError):
        return False


def choose_music(trailer):
    """Devolve o arquivo, se foi enviado pelo usuário, e a grade de batidas."""
    if trailer.music_file:
        return trailer.music_file.path, True, analyse_music(trailer.music_file.path)
    key = trailer.music if trailer.music in MUSIC else STYLE_MUSIC[trailer.style]
    return finders.find(f"music/{key}.m4a"), False, (60 / MUSIC[key].bpm, 0.0)


def build(trailer, folder):
    style = STYLES[trailer.style]
    music, is_upload, (period, phase) = choose_music(trailer)
    items = usable_items(trailer)
    if not items:
        raise TrailerError("Nenhuma das fotos ou vídeos escolhidos pôde ser aberto.")
    room = max(1, int((trailer.duration - INTRO - OUTRO - period) / style.shot))
    items = evenly_pick(items, room)
    cuts = plan_cuts(len(items), trailer.duration, style, period, phase)
    total = cuts[-1] + OUTRO
    steps = len(items) + 3
    done = [0]

    def advance():
        done[0] += 1
        Trailer.objects.filter(pk=trailer.pk).update(progress=done[0] * 100 // steps)

    opening, closing = folder / "abertura.png", folder / "encerramento.png"
    opening_card(trailer.album, opening)
    closing_card(trailer.album, closing)
    segments = [folder / "s000.mp4"]
    card_segment(opening, segments[0], cuts[1] - cuts[0] + style.transition, "fade=t=in:st=0:d=0.6")
    advance()
    for index, (item, duration) in enumerate(items, start=1):
        seconds = cuts[index + 1] - cuts[index] + style.transition
        segment = folder / f"s{index:03}.mp4"
        if item.kind == MediaItem.VIDEO:
            video_segment(item.file.path, duration, segment, seconds, style)
        else:
            frame = folder / f"f{index:03}.jpg"
            photo_frame(item.file, frame)
            photo_segment(frame, segment, seconds, index, style)
        segments.append(segment)
        advance()
    last = folder / "s999.mp4"
    card_segment(closing, last, OUTRO, "fade=t=out:s={last}:n=20")
    segments.append(last)
    advance()
    output = folder / "trailer.mp4"
    join_segments(segments, cuts, total, style, music, is_upload, output)
    return output, total


def render(trailer):
    """Gera o vídeo e publica; qualquer erro vira mensagem no álbum."""
    try:
        with tempfile.TemporaryDirectory(prefix="roleflix-trailer-") as folder:
            output, total = build(trailer, Path(folder))
            with output.open("rb") as stream:
                name = f"{slugify(trailer.album.title) or 'rolê'}-trailer.mp4"
                trailer.file.save(name, File(stream), save=False)
        updated = Trailer.objects.filter(pk=trailer.pk).update(status=Trailer.READY, progress=100, file=trailer.file.name, length=total, music_file="")
        if not updated:  # O álbum foi excluído enquanto o trailer era gerado.
            trailer.file.storage.delete(trailer.file.name)
            return
        for old in Trailer.objects.filter(album_id=trailer.album_id).exclude(pk=trailer.pk):
            delete_trailer(old)
    except TrailerError as error:
        fail(trailer, str(error))
    except Exception:
        logger.exception("Erro inesperado no trailer %s", trailer.pk)
        fail(trailer, "Algo deu errado ao gerar o trailer. Tente novamente.")
    finally:
        if trailer.music_file:
            trailer.music_file.storage.delete(trailer.music_file.name)


def fail(trailer, message):
    Trailer.objects.filter(pk=trailer.pk).update(status=Trailer.FAILED, error=message[:200], music_file="")


def trailer_files(trailer):
    return [field for field in (trailer.file, trailer.music_file) if field]


def delete_trailer(trailer):
    files = trailer_files(trailer)
    trailer.delete()
    for field in files:
        field.storage.delete(field.name)


def expire_stale():
    """Um processo que morreu no meio não pode travar o álbum para sempre."""
    limit = timezone.now() - STALE_AFTER
    Trailer.objects.filter(status__in=Trailer.ACTIVE, created_at__lt=limit).update(status=Trailer.FAILED, error="A geração foi interrompida. Tente novamente.")


def start_render(trailer):
    """Roda fora do processo do site, para sobreviver a reinícios e não prender a requisição."""
    options = {}
    if os.name == "nt":
        options["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.BELOW_NORMAL_PRIORITY_CLASS
    else:
        options["start_new_session"] = True
    try:
        subprocess.Popen([sys.executable, str(settings.BASE_DIR / "manage.py"), "render_trailer", str(trailer.pk)], cwd=settings.BASE_DIR,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **options)
    except OSError:
        logger.exception("Não foi possível iniciar o trailer %s", trailer.pk)
        fail(trailer, "Não foi possível iniciar a geração. Tente novamente.")
