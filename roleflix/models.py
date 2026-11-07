from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

class Profile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    avatar = models.ImageField(upload_to="avatars/", blank=True, null=True, db_index=True)
    bio = models.CharField(max_length=180, blank=True)
    tutorial_hidden = models.BooleanField(default=False)
    def __str__(self):
        return self.user.username

class FriendRequest(models.Model):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    STATUS = [(PENDING, "Pendente"), (ACCEPTED, "Aceito"), (REJECTED, "Recusado")]
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="sent_friend_requests", on_delete=models.CASCADE)
    receiver = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="received_friend_requests", on_delete=models.CASCADE)
    status = models.CharField(max_length=12, choices=STATUS, default=PENDING)
    created_at = models.DateTimeField(default=timezone.now)
    class Meta:
        unique_together = ("sender", "receiver")

class Album(models.Model):
    PRIVATE = "private"
    SHARED = "shared"
    GROUP = "group"
    VISIBILITY = [(PRIVATE, "Privado"), (SHARED, "Compartilhado"), (GROUP, "Grupo")]
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="owned_albums", on_delete=models.CASCADE)
    title = models.CharField(max_length=100)
    synopsis = models.CharField(max_length=240, blank=True)
    description = models.TextField(blank=True)
    event_date = models.DateField(blank=True, null=True)
    location = models.CharField(max_length=160, blank=True)
    latitude = models.FloatField(blank=True, null=True, validators=[MinValueValidator(-90), MaxValueValidator(90)])
    longitude = models.FloatField(blank=True, null=True, validators=[MinValueValidator(-180), MaxValueValidator(180)])
    cover = models.ImageField(upload_to="album_covers/", blank=True, null=True, db_index=True)
    has_poster = models.BooleanField(default=False)  # A capa saiu do editor e já traz o título na imagem.
    visibility = models.CharField(max_length=10, choices=VISIBILITY, default=PRIVATE)
    created_at = models.DateTimeField(default=timezone.now)
    participants = models.ManyToManyField(settings.AUTH_USER_MODEL, through="AlbumParticipant", related_name="shared_albums", blank=True)
    def __str__(self):
        return self.title
    @property
    def cast(self):
        """Quem esteve no rolê: o criador primeiro, depois os participantes."""
        return [self.owner, *(p for p in self.participants.all() if p.id != self.owner_id)]
    @property
    def backdrop(self):
        """Imagem para usar atrás de textos da página: o pôster repetiria o título."""
        return self.cover_design.background if self.has_poster else self.cover

class AlbumParticipant(models.Model):
    """Quem esteve no rolê. Estar no elenco e poder abrir o álbum são coisas separadas."""
    album = models.ForeignKey(Album, on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    has_access = models.BooleanField(default=True)
    added_at = models.DateTimeField(default=timezone.now)
    class Meta:
        unique_together = ("album", "user")

class AlbumView(models.Model):
    """Último acesso de cada pessoa a um álbum, para o "Continuar explorando"."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    album = models.ForeignKey(Album, on_delete=models.CASCADE)
    viewed_at = models.DateTimeField(default=timezone.now)
    class Meta:
        unique_together = ("user", "album")

class Notification(models.Model):
    """Avisa que alguém compartilhou um álbum com o destinatário."""
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="notifications", on_delete=models.CASCADE)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="+", on_delete=models.CASCADE)
    album = models.ForeignKey(Album, on_delete=models.CASCADE)
    read = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)
    class Meta:
        ordering = ["-created_at"]

class MediaItem(models.Model):
    PHOTO = "photo"
    VIDEO = "video"
    KIND = [(PHOTO, "Foto"), (VIDEO, "Vídeo")]
    album = models.ForeignKey(Album, related_name="media", on_delete=models.CASCADE)
    file = models.FileField(upload_to="album_media/", db_index=True)
    kind = models.CharField(max_length=8, choices=KIND)
    caption = models.CharField(max_length=180, blank=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    created_at = models.DateTimeField(default=timezone.now)
    size = models.PositiveBigIntegerField(default=0)  # Em bytes: mede o espaço usado sem consultar a loja de arquivos.

class Trailer(models.Model):
    """Vídeo gerado a partir do álbum. O anterior só sai quando o novo fica pronto."""
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"
    STATUS = [(PENDING, "Na fila"), (PROCESSING, "Gerando"), (READY, "Pronto"), (FAILED, "Falhou")]
    ACTIVE = (PENDING, PROCESSING)
    CINEMATIC = "cinematic"
    FUN = "fun"
    NOSTALGIC = "nostalgic"
    STYLE = [(CINEMATIC, "Cinematográfico"), (FUN, "Divertido"), (NOSTALGIC, "Nostálgico")]
    DURATION = [(30, "30 segundos"), (60, "1 minuto"), (120, "2 minutos")]
    album = models.ForeignKey(Album, related_name="trailers", on_delete=models.CASCADE)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    status = models.CharField(max_length=12, choices=STATUS, default=PENDING)
    progress = models.PositiveSmallIntegerField(default=0)
    style = models.CharField(max_length=12, choices=STYLE, default=CINEMATIC)
    duration = models.PositiveSmallIntegerField(choices=DURATION, default=30)
    music = models.CharField(max_length=20, blank=True)
    music_file = models.FileField(upload_to="trailer_music/", blank=True)  # Apagado ao terminar.
    media_ids = models.JSONField(default=list)  # Na ordem escolhida.
    file = models.FileField(upload_to="album_trailers/", blank=True, db_index=True)
    length = models.FloatField(blank=True, null=True)
    error = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    class Meta:
        ordering = ["-created_at", "-pk"]

class Favorite(models.Model):
    """Marcação pessoal: ninguém mais vê nem há contagem por álbum."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="favorites", on_delete=models.CASCADE)
    album = models.ForeignKey(Album, related_name="favorited_by", on_delete=models.CASCADE)
    created_at = models.DateTimeField(default=timezone.now)
    class Meta:
        unique_together = ("user", "album")
        ordering = ["-created_at", "-pk"]

class Collection(models.Model):
    """Coleção criada à mão. É pessoal e guarda só a ligação: a página filtra pelo acesso atual."""
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="collections", on_delete=models.CASCADE)
    title = models.CharField(max_length=60)
    albums = models.ManyToManyField(Album, related_name="collections", blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    class Meta:
        ordering = ["-created_at", "-pk"]
    def __str__(self):
        return self.title
class CoverDesign(models.Model):
    """Foto limpa e opções do editor; o pôster pronto fica em Album.cover."""
    album = models.OneToOneField(Album, related_name="cover_design", on_delete=models.CASCADE)
    background = models.ImageField(upload_to="cover_backgrounds/", db_index=True)
    config = models.JSONField(default=dict)
    updated_at = models.DateTimeField(auto_now=True)
class Ticket(models.Model):
    """Lembrança do rolê. Guarda a imagem pronta: mudar o álbum depois não altera ingressos antigos."""
    CLASSIC = "classic"
    VINTAGE = "vintage"
    PREMIUM = "premium"
    RETRO = "retro"
    STYLE = [(CLASSIC, "Cinema clássico"), (VINTAGE, "Viagem vintage"), (PREMIUM, "Premium"), (RETRO, "Retrô")]
    MAX_TAGLINE = 90
    album = models.ForeignKey(Album, related_name="tickets", on_delete=models.CASCADE)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="tickets", on_delete=models.CASCADE)
    style = models.CharField(max_length=10, choices=STYLE, default=CLASSIC)
    accent = models.CharField(max_length=7, blank=True)
    tagline = models.CharField(max_length=MAX_TAGLINE, blank=True)
    year = models.PositiveSmallIntegerField()
    sequence = models.PositiveIntegerField()
    upcoming = models.BooleanField(default=False)  # Gerado antes de o rolê acontecer.
    is_favorite = models.BooleanField(default=False)
    image = models.ImageField(upload_to="album_tickets/", db_index=True)
    created_at = models.DateTimeField(default=timezone.now)
    class Meta:
        unique_together = ("year", "sequence")
        ordering = ["-is_favorite", "-created_at", "-pk"]
    @property
    def number(self):
        return f"RF-{self.year}-{self.sequence:03}"