"""Monta o catálogo da página inicial a partir dos álbuns que a pessoa pode ver."""
from django.db.models import Count
from django.urls import reverse
from django.utils.formats import date_format
from django.utils.text import slugify

from .models import Collection, Favorite, MediaItem, Trailer
from .retrospective import album_date

ROW_SIZE = 12
MIN_COLLECTION = 2  # Coleção de um álbum só pareceria vazia.
MAX_SUMMERS = 2
BEST_MOMENTS = 6
MAX_MEMORIES = 6
MEMORY_WINDOW = 15  # Dias em torno do aniversário do rolê.
FEW_ALBUMS = 4
PARTY_WORDS = {
    "aniversario", "aniver", "niver", "balada", "bar", "barzinho", "casamento", "churras", "churrasco", "encontro", "encontros",
    "festa", "festas", "formatura", "resenha", "reuniao", "show", "shows",
}


def summer_year(date):
    """O verão brasileiro atravessa o ano: dezembro já conta para o verão seguinte."""
    if date.month == 12:
        return date.year + 1
    return date.year if date.month <= 3 else None


def is_party(album):
    words = slugify(f"{album.title} {album.synopsis} {album.description}").split("-")
    return not PARTY_WORDS.isdisjoint(words)


def collection(slug, title, albums):
    return card(reverse("collection_detail", args=[slug]), title, albums) | {"slug": slug}


def card(url, title, albums):
    return {"url": url, "title": title, "albums": albums, "covers": [a.cover for a in albums if a.cover][:4]}


def personal_collections(user, albums):
    """Coleções feitas à mão, só com os álbuns que a pessoa ainda pode abrir."""
    by_id = {album.pk: album for album in albums}
    found = []
    for item in Collection.objects.filter(owner=user).prefetch_related("albums"):
        inside = [by_id[album.pk] for album in item.albums.all() if album.pk in by_id]
        found.append(card(reverse("my_collection", args=[item.pk]), item.title, inside))
    return found


def favorite_albums(user, albums):
    by_id = {album.pk: album for album in albums}
    return [by_id[pk] for pk in Favorite.objects.filter(user=user).values_list("album_id", flat=True) if pk in by_id]


def build_collections(albums):
    """Coleções automáticas: ninguém precisa classificar os álbuns para elas existirem."""
    summers = {}
    for album in albums:
        year = summer_year(album_date(album))
        if year:
            summers.setdefault(year, []).append(album)
    found = [collection(f"verao-{year}", f"Verão {year}", summers[year]) for year in sorted(summers, reverse=True)
             if len(summers[year]) >= MIN_COLLECTION][:MAX_SUMMERS]
    parties = [a for a in albums if is_party(a)]
    found.append(collection("viagens", "Viagens", [a for a in albums if a.location and a not in parties]))
    found.append(collection("festas-e-encontros", "Festas e encontros", parties))
    counts = dict(MediaItem.objects.filter(album__in=albums).values_list("album").annotate(total=Count("pk")))
    with_media = [a for a in albums if counts.get(a.pk)]
    best = sorted(with_media, key=lambda a: counts[a.pk] + len(a.cast), reverse=True)[:BEST_MOMENTS]
    found.append(collection("melhores-momentos", "Melhores momentos", best))
    return [item for item in found if len(item["albums"]) >= MIN_COLLECTION]


def memory_phrase(album, today, years):
    subject = "você estava" if len(album.cast) == 1 else "vocês estavam"
    distance = "um ano" if years == 1 else f"{years} anos"
    return f"Há {distance} {subject} aqui"


def build_memories(albums, today):
    """Rolês de outros anos, primeiro os que fazem aniversário nestes dias."""
    near, others = [], []
    for album in albums:
        date = album.event_date  # A data de criação diz quando o álbum foi feito, não quando o rolê aconteceu.
        if date is None or (today - date).days < 335:
            continue
        years = max(1, round((today - date).days / 365.25))
        try:
            anniversary = date.replace(year=date.year + years)
        except ValueError:  # 29 de fevereiro.
            anniversary = date.replace(year=date.year + years, day=28)
        distance = abs((anniversary - today).days)
        if distance <= MEMORY_WINDOW:
            near.append((distance, {"album": album, "phrase": memory_phrase(album, today, years)}))
        else:
            others.append((date, {"album": album, "phrase": f"Em {date_format(date, 'F').lower()} de {date.year}"}))
    near.sort(key=lambda pair: pair[0])
    others.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _, item in near + others][:MAX_MEMORIES]


def build_destinations(albums):
    places = {}
    for album in albums:
        if album.latitude is not None and album.longitude is not None:
            key = (round(album.latitude, 3), round(album.longitude, 3))
            places.setdefault(key, {"lat": album.latitude, "lon": album.longitude, "label": album.location})
    return list(places.values())


def build_home(user, albums, opened, today):
    """`albums` já vem em ordem do mais novo. Cada fileira evita repetir o que está logo acima dela."""
    featured = next((a for a in albums if a.cover), albums[0] if albums else None)
    others = [a for a in albums if a != featured]
    mine = [a for a in others if a.owner_id == user.pk]
    shared = [a for a in others if a.owner_id != user.pk]
    favorites = favorite_albums(user, albums)
    shown = {a.pk for a in [*opened, *favorites[:ROW_SIZE], *mine[:ROW_SIZE], *shared[:ROW_SIZE]]}
    destinations = build_destinations(albums)
    return {
        "featured": featured,
        "trailer": featured.trailers.filter(status=Trailer.READY).first() if featured else None,
        "continue_exploring": opened,
        "favorites": favorites[:ROW_SIZE],
        "mine": mine[:ROW_SIZE],
        "more_mine": len(mine) > ROW_SIZE,
        "shared": shared[:ROW_SIZE],
        "more_shared": len(shared) > ROW_SIZE,
        "has_shared": any(a.owner_id != user.pk for a in albums),
        "collections": [item for item in personal_collections(user, albums) if item["albums"]] + build_collections(albums),
        "memories": build_memories(albums, today),
        "destinations": destinations,
        "destination_labels": sorted({place["label"] for place in destinations})[:6],
        "latest": [a for a in others if a.pk not in shown][:ROW_SIZE],
        "few_albums": len(albums) < FEW_ALBUMS,
    }
