import json
import logging
import os
import shutil
import tempfile
import zipfile

from allauth.account.views import PasswordResetView
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Q, Sum
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.text import slugify
from django.views.decorators.http import require_POST
from . import accounts, covers, homepage, retrospective, tickets, trailers
from .adapters import EmailNaoEnviado
from .forms import AlbumForm, AvatarForm, CollectionForm, MediaUploadForm, ProfileForm, FriendSearchForm, TicketForm, TrailerForm, media_kind
from .models import Album, AlbumParticipant, AlbumView, Collection, CoverDesign, Favorite, FriendRequest, MediaItem, Notification, Profile, Ticket, Trailer
from .places import search_places
from .ranged import ranged_response

logger = logging.getLogger(__name__)

def ensure_profile(user):
    Profile.objects.get_or_create(user=user)

def album_access(user):
    """Única regra de acesso: o dono vê tudo; os demais precisam de acesso liberado ao álbum."""
    return Q(owner=user) | Q(
        albumparticipant__user=user, albumparticipant__has_access=True, visibility__in=[Album.SHARED, Album.GROUP]
    )

def visible_albums(user):
    return Album.objects.filter(album_access(user)).distinct().order_by("-created_at").select_related("owner__profile").prefetch_related("participants__profile")

def user_notifications(user):
    """Notificações de álbuns que o usuário ainda pode abrir."""
    return Notification.objects.filter(recipient=user, album__in=Album.objects.filter(album_access(user)).values("pk"))

def home(request):
    if not request.user.is_authenticated:
        return render(request, "roleflix/home.html")
    visible = visible_albums(request.user)
    albums = list(visible)
    today = timezone.localdate()
    retro_year = retrospective.featured_year(today)
    opened = list(visible.filter(albumview__user=request.user).order_by("-albumview__viewed_at")[:homepage.ROW_SIZE])
    return render(request, "roleflix/home.html", {
        "retro_year": retro_year if retro_year in retrospective.available_years(albums) else None,
        "retro_ready": retrospective.is_ready(today),
        "show_tutorial": not tutorial_is_hidden(request.user),
        **homepage.build_home(request.user, albums, opened, today),
    })

def tutorial_is_hidden(user):
    return Profile.objects.filter(user=user, tutorial_hidden=True).exists()

def safe_next(request, value):
    """Só aceita voltar para uma página do próprio site."""
    if value and url_has_allowed_host_and_scheme(value, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return value
    return reverse("home")

@login_required
def tutorial(request):
    return render(request, "roleflix/tutorial.html", {
        "tutorial_hidden": tutorial_is_hidden(request.user),
        "next_url": safe_next(request, request.GET.get("next")),
        "max_photo_mb": settings.ROLEFLIX_MAX_REQUEST_FILE // 1024 ** 2 if settings.ROLEFLIX_MAX_REQUEST_FILE else None,
    })

@login_required
@require_POST
def hide_tutorial(request):
    """Só este botão para de abrir o tutorial a cada login. Ele segue disponível no perfil."""
    Profile.objects.update_or_create(user=request.user, defaults={"tutorial_hidden": True})
    messages.success(request, "Pronto, o tutorial não abre mais sozinho. Ele fica sempre disponível no seu perfil.")
    return redirect(safe_next(request, request.POST.get("next")))

@login_required
def collection_detail(request, slug):
    found = next((item for item in homepage.build_collections(list(visible_albums(request.user))) if item["slug"] == slug), None)
    if found is None:
        raise Http404
    return render(request, "roleflix/collection.html", {"collection": found})

@login_required
def create_album(request):
    ensure_profile(request.user)
    form = AlbumForm(request.POST or None, request.FILES or None, friends=get_friends(request.user))
    if request.method == "POST" and form.is_valid():
        album = form.save(commit=False)
        album.owner = request.user
        album.save()
        add_participants(album, form.cleaned_data.get("people", []), request.user)
        messages.success(request, "Álbum criado! Agora adicione as memórias.")
        if form.cleaned_data.get("make_ticket") and tickets.is_upcoming(album):
            return redirect("create_ticket", pk=album.pk)
        return redirect("album_detail", pk=album.pk)
    return render(request, "roleflix/album_form.html", {"form": form})

@login_required
def edit_album(request, pk):
    album = get_object_or_404(Album, pk=pk, owner=request.user)
    form = AlbumForm(request.POST or None, request.FILES or None, instance=album)
    if request.method == "POST" and form.is_valid():
        album = form.save()
        if "cover" in form.changed_data:
            covers.forget_design(album)
        if album.visibility == Album.PRIVATE:
            # Privado corta o acesso de verdade: quem esteve no rolê segue no elenco,
            # mas só volta a ver o álbum se o dono compartilhar de novo com essa pessoa.
            album.albumparticipant_set.update(has_access=False)
            Notification.objects.filter(album=album).delete()
        messages.success(request, "Álbum atualizado!")
        return redirect("album_detail", pk=pk)
    return render(request, "roleflix/album_form.html", {"form": form, "editing": True})

@login_required
def delete_album(request, pk):
    album = get_object_or_404(Album, pk=pk, owner=request.user)
    if request.method == "POST":
        # Os arquivos não saem junto com o banco: sem isto, fotos privadas ficariam no disco.
        files = accounts.album_files(album)
        title = album.title
        album.delete()
        accounts.delete_files(files)
        messages.success(request, f"Álbum “{title}” excluído.")
        return redirect("home")
    return render(request, "roleflix/album_delete.html", {
        "album": album,
        "media_count": album.media.count(),
        "participant_count": album.participants.count(),
    })

def can_view(album, user):
    return visible_albums(user).filter(pk=album.pk).exists()

@login_required
def album_detail(request, pk):
    album = get_object_or_404(Album, pk=pk)
    if not can_view(album, request.user):
        messages.error(request, "Você não tem acesso a esse álbum.")
        return redirect("home")
    AlbumView.objects.update_or_create(user=request.user, album=album, defaults={"viewed_at": timezone.now()})
    links = album.albumparticipant_set.select_related("user__profile")
    friends = get_friends(request.user).exclude(id__in=links.filter(has_access=True).values("user_id"))
    trailers.expire_stale()
    latest = album.trailers.first()
    collections = list(request.user.collections.all())
    chosen = set(album.collections.filter(owner=request.user).values_list("pk", flat=True))
    for collection in collections:
        collection.has_album = collection.pk in chosen
    return render(request, "roleflix/album_detail.html", {
        "album": album, "friends": friends, "links": links,
        "is_favorite": Favorite.objects.filter(user=request.user, album=album).exists(),
        "tickets": album.tickets.select_related("created_by", "album"),
        "upcoming": tickets.is_upcoming(album),
        "my_collections": collections,
        "trailer": album.trailers.filter(status=Trailer.READY).first(),
        "trailer_job": latest if latest and latest.status != Trailer.READY else None,
    })

@login_required
def cover_editor(request, pk):
    album = get_object_or_404(Album, pk=pk, owner=request.user)
    design = CoverDesign.objects.filter(album=album).first()
    photos = album.media.filter(kind=MediaItem.PHOTO).order_by("created_at", "pk")
    if request.method == "POST":
        media = None
        if request.POST.get("background_media"):
            media = photos.filter(pk=request.POST["background_media"]).first() if request.POST["background_media"].isdigit() else None
            if media is None:
                return JsonResponse({"error": "Essa foto não está neste álbum."}, status=400)
        try:
            config = json.loads(request.POST.get("config", ""))
            covers.save_cover(album, request.FILES.get("final"), config, request.FILES.get("background_file"), media)
        except json.JSONDecodeError:
            return JsonResponse({"error": "Não foi possível ler as configurações da capa."}, status=400)
        except covers.CoverError as error:
            return JsonResponse({"error": str(error)}, status=400)
        messages.success(request, "Capa salva!")
        return JsonResponse({"ok": True})
    return render(request, "roleflix/cover_editor.html", {
        "album": album,
        "has_design": design is not None,
        "width": covers.WIDTH,
        "height": covers.HEIGHT,
        "editor": {
            "config": design.config if design else covers.default_config(album),
            "background": design.background.url if design else album.cover.url if album.cover else "",
            "photos": [{"id": item.pk, "url": item.file.url} for item in photos[:60]],
            "cast": [{
                "name": person.first_name or person.username,
                "avatar": person.profile.avatar.url if hasattr(person, "profile") and person.profile.avatar else "",
            } for person in album.cast],
            "fonts": covers.FONTS,
            "filters": covers.FILTERS,
            "positions": covers.POSITIONS,
            "templates": covers.TEMPLATES,
            "save_url": reverse("cover_editor", args=[album.pk]),
            "album_url": reverse("album_detail", args=[album.pk]),
        },
    })

@login_required
@require_POST
def restore_cover(request, pk):
    album = get_object_or_404(Album, pk=pk, owner=request.user)
    covers.restore_photo(album)
    messages.success(request, "A foto original voltou a ser a capa.")
    return redirect("album_detail", pk=pk)

def visible_album_or_404(pk, user):
    album = get_object_or_404(Album, pk=pk)
    if not can_view(album, user):
        raise Http404
    return album

@login_required
def create_ticket(request, pk):
    album = visible_album_or_404(pk, request.user)
    form = TicketForm(request.POST or None, initial={"tagline": tickets.default_tagline(album)})
    if request.method == "POST" and form.is_valid():
        if album.tickets.filter(created_by=request.user).count() >= tickets.MAX_PER_PERSON:
            messages.error(request, f"Você já tem {tickets.MAX_PER_PERSON} ingressos neste álbum. Exclua um para gerar outro.")
        else:
            data = form.cleaned_data
            tagline = data["tagline"].strip() or tickets.default_tagline(album)
            ticket = tickets.create_ticket(album, request.user, data["style"], data["accent"], tagline)
            messages.success(request, f"Ingresso {ticket.number} gerado!")
        return redirect(reverse("album_detail", args=[pk]) + "#ingressos")
    return render(request, "roleflix/ticket_form.html", {"album": album, "form": form, "upcoming": tickets.is_upcoming(album)})

@login_required
def ticket_preview(request, pk):
    album = visible_album_or_404(pk, request.user)
    form = TicketForm({
        "style": request.GET.get("style") or Ticket.CLASSIC,
        "tagline": request.GET.get("tagline", ""),
        "accent": request.GET.get("accent", ""),
    })
    if not form.is_valid():
        return HttpResponse(status=400)
    data = form.cleaned_data
    image = tickets.preview_bytes(album, data["style"], data["accent"], data["tagline"].strip() or tickets.default_tagline(album))
    return HttpResponse(image, content_type="image/png")

def visible_ticket_or_404(pk, user):
    ticket = get_object_or_404(Ticket.objects.select_related("album"), pk=pk)
    if not can_view(ticket.album, user):
        raise Http404
    return ticket

@login_required
def download_ticket(request, pk, kind):
    ticket = visible_ticket_or_404(pk, request.user)
    name = f"ingresso-{ticket.number.lower()}.{kind}"
    try:
        if kind == "pdf":
            response = HttpResponse(tickets.pdf_bytes(ticket), content_type="application/pdf")
            response["Content-Disposition"] = f'attachment; filename="{name}"'
            return response
        return FileResponse(ticket.image.open("rb"), as_attachment=True, filename=name)
    except FileNotFoundError:
        raise Http404

@login_required
@require_POST
def favorite_ticket(request, pk):
    """Cada pessoa tem um ingresso favorito por álbum."""
    ticket = get_object_or_404(Ticket, pk=pk, created_by=request.user)
    chosen = not ticket.is_favorite
    Ticket.objects.filter(album=ticket.album, created_by=request.user).update(is_favorite=False)
    Ticket.objects.filter(pk=pk).update(is_favorite=chosen)
    return redirect(reverse("album_detail", args=[ticket.album_id]) + "#ingressos")

@login_required
@require_POST
def delete_ticket(request, pk):
    ticket = get_object_or_404(Ticket, pk=pk, created_by=request.user)
    album_id = ticket.album_id
    tickets.delete_ticket(ticket)
    messages.success(request, "Ingresso excluído.")
    return redirect(reverse("album_detail", args=[album_id]) + "#ingressos")

@login_required
def my_tickets(request):
    visible = visible_albums(request.user).values("pk")
    mine = Ticket.objects.filter(created_by=request.user, album__in=visible).select_related("album", "created_by")
    return render(request, "roleflix/my_tickets.html", {"tickets": mine})

@login_required
@require_POST
def toggle_favorite(request, pk):
    album = get_object_or_404(Album, pk=pk)
    if not can_view(album, request.user):
        raise Http404
    favorite, created = Favorite.objects.get_or_create(user=request.user, album=album)
    if not created:
        favorite.delete()
    return redirect("album_detail", pk=pk)

@login_required
@require_POST
def album_collections(request, pk):
    """Define em quais coleções da pessoa o álbum está; pode criar uma nova no mesmo envio."""
    album = get_object_or_404(Album, pk=pk)
    if not can_view(album, request.user):
        raise Http404
    selected = set(request.POST.getlist("collections"))
    for collection in request.user.collections.all():
        if str(collection.pk) in selected:
            collection.albums.add(album)
        else:
            collection.albums.remove(album)
    title = request.POST.get("title", "").strip()
    if title:
        form = CollectionForm({"title": title})
        if form.is_valid():
            new = request.user.collections.filter(title__iexact=form.cleaned_data["title"]).first()
            if new is None:
                new = form.save(commit=False)
                new.owner = request.user
                new.save()
            new.albums.add(album)
        else:
            messages.error(request, "O nome da coleção pode ter até 60 caracteres.")
            return redirect("album_detail", pk=pk)
    messages.success(request, "Coleções atualizadas.")
    return redirect("album_detail", pk=pk)

@login_required
@require_POST
def create_collection(request):
    form = CollectionForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Dê à coleção um nome de até 60 caracteres.")
        return redirect("my_albums")
    existing = request.user.collections.filter(title__iexact=form.cleaned_data["title"]).first()
    if existing:
        return redirect("my_collection", pk=existing.pk)
    collection = form.save(commit=False)
    collection.owner = request.user
    collection.save()
    return redirect("my_collection", pk=collection.pk)

@login_required
def my_collection(request, pk):
    collection = get_object_or_404(Collection, pk=pk, owner=request.user)
    visible = visible_albums(request.user)
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "delete":
            title = collection.title
            collection.delete()
            messages.success(request, f"Coleção “{title}” excluída. Os álbuns continuam guardados.")
            return redirect("my_albums")
        if action == "rename":
            form = CollectionForm(request.POST, instance=collection)
            if form.is_valid():
                form.save()
            else:
                messages.error(request, "Dê à coleção um nome de até 60 caracteres.")
        elif action == "add":
            ids = [value for value in request.POST.getlist("albums") if value.isdigit()]
            collection.albums.add(*visible.filter(pk__in=ids))
        elif action == "remove" and request.POST.get("album", "").isdigit():
            collection.albums.remove(request.POST["album"])
        return redirect("my_collection", pk=pk)
    return render(request, "roleflix/my_collection.html", {
        "collection": collection,
        "albums": visible.filter(collections=collection),
        "available": visible.exclude(collections=collection),
    })

@login_required
def create_trailer(request, pk):
    album = get_object_or_404(Album, pk=pk, owner=request.user)
    if settings.ROLEFLIX_SERVERLESS:
        messages.info(request, "Os trailers ficam desligados neste servidor.")
        return redirect("album_detail", pk=pk)
    items = list(album.media.order_by("created_at", "pk"))
    if not items:
        messages.error(request, "Adicione fotos ou vídeos antes de criar o trailer.")
        return redirect("album_detail", pk=pk)
    trailers.expire_stale()
    form = TrailerForm(request.POST or None, request.FILES or None, album=album)
    if request.method == "POST" and form.is_valid():
        if album.trailers.filter(status__in=Trailer.ACTIVE).exists():
            messages.info(request, "Este álbum já tem um trailer sendo gerado.")
        elif Trailer.objects.filter(status__in=Trailer.ACTIVE).count() >= trailers.MAX_ACTIVE:
            messages.error(request, "Muitos trailers sendo gerados agora. Tente de novo em alguns minutos.")
        else:
            album.trailers.filter(status=Trailer.FAILED).delete()
            trailers.start_render(form.save(request.user))
            messages.success(request, "Seu trailer está sendo gerado. Pode continuar usando o site.")
        return redirect("album_detail", pk=pk)
    return render(request, "roleflix/trailer_form.html", {"album": album, "form": form, "items": items, "tracks": trailers.MUSIC})

@login_required
def trailer_status(request, pk):
    album = get_object_or_404(Album, pk=pk)
    latest = album.trailers.first()
    if not can_view(album, request.user) or latest is None:
        raise Http404
    return JsonResponse({"status": latest.status, "progress": latest.progress})

@login_required
def download_trailer(request, pk):
    album = get_object_or_404(Album, pk=pk)
    trailer = album.trailers.filter(status=Trailer.READY).first()
    if trailer is None or not can_view(album, request.user):
        raise Http404
    try:
        return FileResponse(trailer.file.open("rb"), as_attachment=True, filename=f"{slugify(album.title) or 'role'}-trailer.mp4")
    except FileNotFoundError:
        raise Http404

def media_space_is_full():
    if settings.ROLEFLIX_MAX_MEDIA_BYTES is not None:
        return (MediaItem.objects.aggregate(total=Sum("size"))["total"] or 0) >= settings.ROLEFLIX_MAX_MEDIA_BYTES
    return shutil.disk_usage(settings.DATA_DIR).free < settings.ROLEFLIX_MIN_FREE_DISK  # A pasta de mídia só nasce no primeiro envio.

def save_media(request, album):
    """Devolve a mensagem de erro, ou None se tudo foi guardado."""
    if media_space_is_full():
        return "O espaço do site está no limite. Tente novamente mais tarde."
    form = MediaUploadForm(request.POST, request.FILES)
    if not form.is_valid():
        return next(iter(form.errors.values()))[0]
    try:
        with transaction.atomic():
            for f in form.cleaned_data["files"]:
                MediaItem.objects.create(album=album, file=f, kind=media_kind(f.name), caption=form.cleaned_data["caption"], uploaded_by=request.user, size=f.size)
    except OSError:
        logger.exception("Não foi possível guardar o arquivo enviado")
        return "Não foi possível guardar o arquivo agora. Tente novamente mais tarde."
    return None

@login_required
@require_POST
def upload_media(request, pk):
    album = get_object_or_404(Album, pk=pk)
    if not can_view(album, request.user):
        return redirect("home")
    error = save_media(request, album)
    if request.headers.get("X-Requested-With") == "fetch":  # O álbum sobe um arquivo por vez na Vercel.
        return JsonResponse({"error": error}, status=400 if error else 200)
    if error:
        messages.error(request, error)
    else:
        messages.success(request, "Memórias adicionadas!")
    return redirect("album_detail", pk=pk)

@login_required
def download_media(request, pk, item_id):
    item = get_object_or_404(MediaItem, pk=item_id, album_id=pk)
    if not can_view(item.album, request.user):
        raise Http404
    try:
        return FileResponse(item.file.open("rb"), as_attachment=True, filename=os.path.basename(item.file.name))
    except FileNotFoundError:
        raise Http404

@login_required
def download_album(request, pk):
    album = get_object_or_404(Album, pk=pk)
    if not can_view(album, request.user):
        raise Http404
    items = album.media.all()
    if not items:
        messages.error(request, "Este álbum ainda não tem fotos ou vídeos.")
        return redirect("album_detail", pk=pk)
    limit = settings.ROLEFLIX_MAX_REQUEST_FILE
    if limit and items.aggregate(total=Sum("size"))["total"] > limit:
        messages.error(request, "Este álbum é grande demais para baixar de uma vez aqui. Baixe as fotos uma a uma.")
        return redirect("album_detail", pk=pk)
    # Vai para o disco, não para a memória: um álbum pode ter vários vídeos grandes.
    archive = tempfile.TemporaryFile()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_STORED) as bundle:
        for item in items:
            try:
                source = item.file.open("rb")
            except FileNotFoundError:
                continue
            with source, bundle.open(os.path.basename(item.file.name), "w", force_zip64=True) as target:
                shutil.copyfileobj(source, target)
    archive.seek(0)
    return FileResponse(archive, as_attachment=True, filename=f"{slugify(album.title) or 'album'}.zip")

@login_required
def search(request):
    query = request.GET.get("q", "").strip()
    albums = []
    if query:
        albums = visible_albums(request.user).filter(
            Q(title__icontains=query)
            | Q(owner__username__icontains=query) | Q(owner__first_name__icontains=query)
            | Q(participants__username__icontains=query) | Q(participants__first_name__icontains=query)
        )
    return render(request, "roleflix/search.html", {"query": query, "albums": albums})

@login_required
def my_albums(request):
    visible = visible_albums(request.user)
    return render(request, "roleflix/my_albums.html", {
        "mine": visible.filter(owner=request.user),
        "shared": visible.exclude(owner=request.user),
        "favorites": homepage.favorite_albums(request.user, list(visible)),
        "collections": homepage.personal_collections(request.user, list(visible)),
    })

@login_required
def retrospective_latest(request):
    today = timezone.localdate()
    years = retrospective.available_years(visible_albums(request.user))
    wanted = retrospective.featured_year(today)
    year = wanted if wanted in years or not years else years[0]
    return redirect("retrospective", year=year)

@login_required
def retrospective_year(request, year):
    today = timezone.localdate()
    albums = visible_albums(request.user)
    return render(request, "roleflix/retrospective.html", {
        "year": year,
        "years": retrospective.available_years(albums),
        "partial": retrospective.is_partial(year, today),
        "retro": retrospective.build_retrospective(albums, request.user, year),
    })

@login_required
def place_search(request):
    return JsonResponse({"results": search_places(request.GET.get("q", ""))})

@login_required
def album_map(request):
    """Agrupa por lugar: vários rolês na mesma cidade viram um só pino."""
    albums = visible_albums(request.user)
    pinned = albums.exclude(latitude=None).exclude(longitude=None)
    places = {}
    for album in pinned:
        key = (round(album.latitude, 3), round(album.longitude, 3))
        place = places.setdefault(key, {"lat": album.latitude, "lon": album.longitude, "label": album.location, "albums": []})
        place["albums"].append({
            "id": album.pk,
            "title": album.title,
            "url": reverse("album_detail", args=[album.pk]),
            "cover": album.cover.url if album.cover else "",
            "date": date_format(album.event_date, "d/m/Y") if album.event_date else "",
        })
    return render(request, "roleflix/album_map.html", {
        "places": list(places.values()),
        "without_pin": albums.count() - pinned.count(),
    })

@login_required
def protected_media(request, path):
    """Entrega os arquivos enviados conferindo a permissão do álbum a que pertencem."""
    item = MediaItem.objects.filter(file=path).select_related("album").first()
    trailer = None if item else Trailer.objects.filter(file=path).select_related("album").first()
    design = None if item or trailer else CoverDesign.objects.filter(background=path).select_related("album").first()
    ticket = None if item or trailer or design else Ticket.objects.filter(image=path).select_related("album").first()
    album = item.album if item else trailer.album if trailer else design.album if design else ticket.album if ticket else Album.objects.filter(cover=path).first()
    if item:
        field = item.file
    elif trailer:
        field = trailer.file
    elif design:
        field = design.background
    elif ticket:
        field = ticket.image
    elif album:
        field = album.cover
    else:
        owner_profile = Profile.objects.filter(avatar=path).first()
        if not owner_profile:
            raise Http404
        field = owner_profile.avatar
    if album and not can_view(album, request.user):
        raise Http404
    try:
        response = ranged_response(request, field)
    except FileNotFoundError:
        raise Http404
    except OSError:
        logger.exception("Não foi possível ler %s", path)
        return HttpResponse(status=503)
    if settings.ROLEFLIX_SERVERLESS:  # Só no navegador de quem pode ver: economiza a cota de transferência.
        response["Cache-Control"] = "private, max-age=86400"
    return response

def get_friends(user):
    accepted = FriendRequest.objects.filter(status=FriendRequest.ACCEPTED).filter(Q(sender=user) | Q(receiver=user))
    ids = []
    for item in accepted:
        ids.append(item.receiver_id if item.sender_id == user.id else item.sender_id)
    return User.objects.filter(id__in=ids).distinct()

@login_required
def friends(request):
    form = FriendSearchForm(request.GET or None)
    results = []
    if form.is_valid():
        term = form.cleaned_data["username"].strip()
        if term:
            results = User.objects.filter(
                Q(username__icontains=term) | Q(first_name__icontains=term) | Q(email__iexact=term)
            ).exclude(id=request.user.id)[:15]
    incoming = FriendRequest.objects.filter(receiver=request.user, status=FriendRequest.PENDING)
    outgoing = FriendRequest.objects.filter(sender=request.user, status=FriendRequest.PENDING)
    return render(request, "roleflix/friends.html", {"form": form, "results": results, "incoming": incoming, "outgoing": outgoing, "friends": get_friends(request.user)})

@login_required
@require_POST
def send_friend_request(request, user_id):
    target = get_object_or_404(User, pk=user_id)
    if target == request.user:
        return redirect("friends")
    existing = FriendRequest.objects.filter(
        Q(sender=request.user, receiver=target) | Q(sender=target, receiver=request.user)
    ).first()
    if existing is None:
        FriendRequest.objects.create(sender=request.user, receiver=target)
    elif existing.status == FriendRequest.REJECTED:
        existing.sender, existing.receiver = request.user, target
        existing.status = FriendRequest.PENDING
        existing.save()
    elif existing.status == FriendRequest.PENDING and existing.receiver_id == request.user.id:
        # Os dois querem a amizade: o pedido cruzado vale como aceite.
        existing.status = FriendRequest.ACCEPTED
        existing.save()
    return redirect("friends")

@login_required
@require_POST
def respond_friend_request(request, request_id, action):
    fr = get_object_or_404(FriendRequest, pk=request_id, receiver=request.user, status=FriendRequest.PENDING)
    if action == "accept":
        fr.status = FriendRequest.ACCEPTED
        fr.save()
    elif action == "reject":
        fr.status = FriendRequest.REJECTED
        fr.save()
    return redirect("friends")

@login_required
def share_album(request, pk):
    album = get_object_or_404(Album, pk=pk, owner=request.user)
    if request.method == "POST":
        ids = [value for value in request.POST.getlist("participants") if value.isdigit()]
        allowed = get_friends(request.user).filter(id__in=ids)
        if not allowed:
            messages.error(request, "Selecione pelo menos um amigo.")
            return redirect("album_detail", pk=pk)
        add_participants(album, allowed, request.user)
        messages.success(request, "Álbum compartilhado com os amigos selecionados.")
    return redirect("album_detail", pk=pk)

def add_participants(album, friends, actor):
    """Dá acesso aos amigos e avisa cada um; um álbum privado passa a ser compartilhado."""
    if not friends:
        return
    for friend in friends:
        link, created = AlbumParticipant.objects.get_or_create(album=album, user=friend)
        if created or not link.has_access:
            link.has_access = True
            link.save()
            Notification.objects.create(recipient=friend, actor=actor, album=album)
    if album.visibility == Album.PRIVATE:
        album.visibility = Album.SHARED
        album.save()

@login_required
@require_POST
def remove_participant(request, pk, user_id):
    album = get_object_or_404(Album, pk=pk, owner=request.user)
    AlbumParticipant.objects.filter(album=album, user_id=user_id).delete()
    Notification.objects.filter(album=album, recipient_id=user_id).delete()
    messages.success(request, "Participante removido do álbum.")
    return redirect("album_detail", pk=pk)

@login_required
def notifications(request):
    items = list(user_notifications(request.user).select_related("actor__profile", "album"))
    user_notifications(request.user).filter(read=False).update(read=True)
    return render(request, "roleflix/notifications.html", {"items": items})

@login_required
def profile(request, username):
    person = get_object_or_404(User, username=username)
    ensure_profile(person)
    visible = visible_albums(request.user)
    own = visible.filter(owner=person)
    shared = visible.filter(albumparticipant__user=person, albumparticipant__has_access=True).exclude(owner=person)
    return render(request, "roleflix/profile.html", {"person": person, "own": own, "shared": shared})

@login_required
def delete_account(request):
    if request.method == "POST":
        if request.POST.get("confirm", "").strip() == "EXCLUIR":
            user = request.user
            logout(request)
            accounts.delete_account(user)
            messages.success(request, "Sua conta foi excluída.")
            return redirect("home")
        messages.error(request, "Digite EXCLUIR para confirmar.")
    return render(request, "roleflix/delete_account.html", {
        "album_count": Album.objects.filter(owner=request.user).count(),
        "media_count": MediaItem.objects.filter(uploaded_by=request.user).exclude(album__owner=request.user).count(),
    })

def privacy(request):
    return render(request, "roleflix/privacy.html", {"contact_email": settings.ROLEFLIX_CONTACT_EMAIL})

def terms(request):
    return render(request, "roleflix/terms.html", {"contact_email": settings.ROLEFLIX_CONTACT_EMAIL})

@login_required
@require_POST
def change_avatar(request):
    profile, _ = Profile.objects.get_or_create(user=request.user)
    form = AvatarForm(request.POST, request.FILES, instance=profile)
    old = profile.avatar.name if profile.avatar else ""
    if form.is_valid() and form.cleaned_data.get("avatar"):
        saved = form.save()
        if old and old != saved.avatar.name:
            saved.avatar.storage.delete(old)
        messages.success(request, "Foto de perfil atualizada!")
    else:
        message = next(iter(form.errors.values()))[0] if form.errors else "Escolha uma foto."
        messages.error(request, message)
    return redirect("profile", username=request.user.username)

@login_required
def edit_profile(request):
    profile, _ = Profile.objects.get_or_create(user=request.user)
    form = ProfileForm(request.POST or None, request.FILES or None, instance=profile)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Perfil atualizado!")
        return redirect("profile", username=request.user.username)
    return render(request, "roleflix/profile_form.html", {"form": form})


class RecuperarSenhaView(PasswordResetView):
    def form_valid(self, form):
        try:
            return super().form_valid(form)
        except EmailNaoEnviado:
            form.add_error(None, "Não conseguimos enviar o e-mail agora. Tente de novo em alguns minutos.")
            return self.form_invalid(form)
