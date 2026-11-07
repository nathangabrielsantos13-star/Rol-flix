"""Monta a retrospectiva anual a partir dos álbuns que a pessoa pode ver."""
from collections import Counter

from django.utils import timezone
from django.utils.formats import date_format

from .models import MediaItem

TOP_PEOPLE = 5
TOP_COVERS = 6
MAX_MOMENTS = 24
MONTHS_READY = (12, 1)


def album_date(album):
    """O ano do rolê vale pela data da viagem; sem ela, pela data em que foi criado."""
    return album.event_date or timezone.localtime(album.created_at).date()


def available_years(albums):
    return sorted({album_date(album).year for album in albums}, reverse=True)


def featured_year(today):
    """Em janeiro a retrospectiva em destaque ainda é a do ano que acabou."""
    return today.year - 1 if today.month == 1 else today.year


def is_ready(today):
    return today.month in MONTHS_READY


def is_partial(year, today):
    return year == today.year and today.month < 12


def plural(count, singular, plural_form):
    return f"{count} {singular if count == 1 else plural_form}"


def pick_moments(albums, photos_by_album):
    """Reveza entre os álbuns para a montagem não virar um rolê só, e mantém a ordem do ano."""
    queues = {}
    for album in albums:
        files = [album.cover.url] if album.cover else []
        files += [item.file.url for item in photos_by_album.get(album.pk, [])]
        queues[album.pk] = files
    chosen = Counter()
    remaining = MAX_MOMENTS
    while remaining and any(chosen[pk] < len(files) for pk, files in queues.items()):
        for pk, files in queues.items():
            if remaining and chosen[pk] < len(files):
                chosen[pk] += 1
                remaining -= 1
    moments = []
    for album in albums:
        date = album_date(album)
        for url in queues[album.pk][:chosen[album.pk]]:
            moments.append({
                "url": url,
                "title": album.title,
                "place": album.location,
                "date": date_format(date, "F \\d\\e Y"),
            })
    return moments


def build_retrospective(albums, user, year):
    albums = sorted((a for a in albums if album_date(a).year == year), key=album_date)
    photos_by_album = {}
    media_count = Counter()
    videos = 0
    for item in MediaItem.objects.filter(album__in=albums).order_by("created_at", "pk"):
        media_count[item.album_id] += 1
        if item.kind == MediaItem.VIDEO:
            videos += 1
        else:
            photos_by_album.setdefault(item.album_id, []).append(item)
    photos = sum(len(items) for items in photos_by_album.values())

    people = Counter()
    for album in albums:
        people.update(person for person in album.cast if person.pk != user.pk)
    ranking = sorted(people.items(), key=lambda pair: (-pair[1], (pair[0].first_name or pair[0].username).casefold()))

    def memories(album):
        return media_count[album.pk] + len(album.cast)

    covers = sorted((a for a in albums if a.cover), key=memories, reverse=True)
    places = sorted({a.location for a in albums if a.location})
    return {
        "albums": albums,
        "album_count": len(albums),
        "places": places,
        "photos": photos,
        "videos": videos,
        "people": [{"person": person, "count": count} for person, count in ranking[:TOP_PEOPLE]],
        "covers": covers[:TOP_COVERS],
        "moments": pick_moments(albums, photos_by_album),
        "summary": " • ".join([
            plural(len(albums), "rolê", "rolês"),
            plural(len(places), "lugar", "lugares"),
            plural(photos + videos, "memória", "memórias"),
        ]),
    }
