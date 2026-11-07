import secrets

from django import forms
from django.conf import settings
from django.core.files.uploadedfile import UploadedFile
from django.forms.widgets import ClearableFileInput
from django.urls import reverse
from PIL import Image
from .models import Album, Collection, MediaItem, Profile, Ticket, Trailer
from .trailers import MUSIC

MUSIC_EXTENSIONS = {"mp3", "m4a", "aac", "wav", "ogg", "flac"}
MAX_MUSIC_SIZE = 30 * 1024 * 1024
PHOTO_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "gif"}
# MPO é um JPG com várias imagens, comum em fotos de celular (HDR, modo retrato).
PHOTO_FORMATS = {"JPEG", "MPO", "PNG", "WEBP", "GIF"}
VIDEO_EXTENSIONS = {"mp4", "webm", "mov", "m4v"}
MAX_PHOTO_SIZE = 20 * 1024 * 1024
MAX_VIDEO_SIZE = 300 * 1024 * 1024

def file_extension(name):
    return name.lower().rsplit(".", 1)[-1] if "." in name else ""

def media_kind(name):
    return MediaItem.VIDEO if file_extension(name) in VIDEO_EXTENSIONS else MediaItem.PHOTO

def is_valid_photo(uploaded):
    try:
        with Image.open(uploaded) as image:
            image.verify()
            return image.format in PHOTO_FORMATS
    except Exception:
        return False
    finally:
        uploaded.seek(0)

def check_image_upload(image):
    """Valida só arquivos novos: ao editar, o campo pode trazer a imagem já salva."""
    if isinstance(image, UploadedFile):
        if image.size > MAX_PHOTO_SIZE:
            raise forms.ValidationError("A foto passa do limite de 20 MB.")
        if file_extension(image.name) not in PHOTO_EXTENSIONS or not is_valid_photo(image):
            raise forms.ValidationError("Envie uma foto JPG, PNG, WEBP ou GIF.")
    return image

class SignupExtraForm(forms.Form):
    """Campos a mais no cadastro do allauth; o nome de usuário é gerado a partir do nome."""
    first_name = forms.CharField(label="Seu nome", max_length=150)
    field_order = ["first_name", "invite_code", "email", "password1", "password2"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if settings.ROLEFLIX_INVITE_CODE:
            self.fields["invite_code"] = forms.CharField(label="Código de convite", max_length=80)

    def clean_invite_code(self):
        code = self.cleaned_data.get("invite_code", "").strip()
        if not secrets.compare_digest(code.encode(), settings.ROLEFLIX_INVITE_CODE.encode()):
            raise forms.ValidationError("Código de convite incorreto.")
        return code

    def signup(self, request, user):
        pass  # O allauth já salva first_name; ele só exige que este método exista.

class FriendChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, friend):
        return friend.first_name or friend.username

class AlbumForm(forms.ModelForm):
    class Meta:
        model = Album
        fields = ["title", "synopsis", "description", "event_date", "location", "latitude", "longitude", "cover", "visibility"]
        help_texts = {"location": "Escolha uma sugestão da lista para o rolê aparecer no mapa."}
        labels = {
            "title": "Título do rolê",
            "synopsis": "Sinopse",
            "description": "Como foi a experiência",
            "event_date": "Data",
            "location": "Local",
            "cover": "Foto de capa",
            "visibility": "Quem pode ver",
        }
        widgets = {
            # O campo de data do navegador só entende o formato ISO, mesmo em pt-br.
            "event_date": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            "description": forms.Textarea(attrs={"rows": 3}),
            "location": forms.TextInput(attrs={"autocomplete": "off", "placeholder": "Digite uma cidade ou país"}),
            "latitude": forms.HiddenInput(),
            "longitude": forms.HiddenInput(),
        }

    def __init__(self, *args, friends=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["location"].widget.attrs["data-place-search"] = reverse("place_search")
        if not self.instance.pk:
            self.fields["make_ticket"] = forms.BooleanField(required=False, label="Criar o ingresso deste rolê")
        if friends is not None and friends.exists():
            self.fields["people"] = FriendChoiceField(
                queryset=friends, required=False, widget=forms.CheckboxSelectMultiple,
                label="Amigos que podem ver este álbum",
                help_text="Se o álbum estiver como Privado, ele passa a ser Compartilhado com quem você marcar.",
            )

    def clean_cover(self):
        return check_image_upload(self.cleaned_data.get("cover"))

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("latitude") is None or cleaned.get("longitude") is None or not cleaned.get("location"):
            cleaned["latitude"] = cleaned["longitude"] = None
        return cleaned

class MultipleFileInput(ClearableFileInput):
    allow_multiple_selected = True

class MultipleFileField(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput())
        super().__init__(*args, **kwargs)
    def clean(self, data, initial=None):
        single_clean = super().clean
        files = data if isinstance(data, (list, tuple)) else [data] if data else []
        if self.required and not files:
            raise forms.ValidationError(self.error_messages["required"], code="required")
        return [single_clean(item, initial) for item in files]

class MediaUploadForm(forms.Form):
    files = MultipleFileField(error_messages={"required": "Selecione pelo menos um arquivo."})
    caption = forms.CharField(required=False, max_length=180)

    def clean_files(self):
        files = self.cleaned_data["files"]
        for f in files:
            ext = file_extension(f.name)
            if ext in VIDEO_EXTENSIONS:
                if f.size > MAX_VIDEO_SIZE:
                    raise forms.ValidationError(f"{f.name}: o vídeo passa do limite de 300 MB.")
            elif ext not in PHOTO_EXTENSIONS or not is_valid_photo(f):
                raise forms.ValidationError(f"{f.name}: envie fotos JPG, PNG, WEBP ou GIF, ou vídeos MP4, WEBM ou MOV.")
            elif f.size > MAX_PHOTO_SIZE:
                raise forms.ValidationError(f"{f.name}: a foto passa do limite de 20 MB.")
        return files

class TrailerForm(forms.Form):
    """As fotos e vídeos vêm do próprio formulário na ordem escolhida, por isso são lidos à mão."""
    AUTOMATIC, UPLOAD = "auto", "upload"
    style = forms.ChoiceField(choices=Trailer.STYLE, initial=Trailer.CINEMATIC, widget=forms.RadioSelect)
    duration = forms.TypedChoiceField(choices=Trailer.DURATION, coerce=int, initial=30, widget=forms.RadioSelect)
    music = forms.ChoiceField(choices=[(AUTOMATIC, "auto"), *((key, track.label) for key, track in MUSIC.items()), (UPLOAD, "upload")], initial=AUTOMATIC)
    music_file = forms.FileField(required=False)

    def __init__(self, *args, album, **kwargs):
        super().__init__(*args, **kwargs)
        self.album = album

    def clean_music_file(self):
        music = self.cleaned_data.get("music_file")
        if music:
            if file_extension(music.name) not in MUSIC_EXTENSIONS:
                raise forms.ValidationError("Envie a música em MP3, M4A, AAC, WAV, OGG ou FLAC.")
            if music.size > MAX_MUSIC_SIZE:
                raise forms.ValidationError("A música passa do limite de 30 MB.")
        return music

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("music") == self.UPLOAD and not cleaned.get("music_file") and "music_file" not in self.errors:
            self.add_error("music_file", "Escolha o arquivo da música.")
        allowed = set(self.album.media.values_list("pk", flat=True))
        chosen = [int(value) for value in self.data.getlist("media") if value.isdigit() and int(value) in allowed]
        cleaned["media"] = list(dict.fromkeys(chosen))
        if not cleaned["media"]:
            self.add_error(None, "Escolha pelo menos uma foto ou vídeo.")
        return cleaned

    def save(self, user):
        data = self.cleaned_data
        upload = data["music_file"] if data["music"] == self.UPLOAD else None
        music = "" if data["music"] in (self.AUTOMATIC, self.UPLOAD) else data["music"]
        return Trailer.objects.create(album=self.album, created_by=user, style=data["style"], duration=data["duration"],
                                      music=music, music_file=upload, media_ids=data["media"])

class TicketForm(forms.Form):
    style = forms.ChoiceField(choices=Ticket.STYLE, initial=Ticket.CLASSIC, widget=forms.RadioSelect)
    tagline = forms.CharField(required=False, max_length=Ticket.MAX_TAGLINE, widget=forms.TextInput(attrs={"maxlength": Ticket.MAX_TAGLINE}))
    accent = forms.RegexField(regex=r"^#[0-9a-fA-F]{6}$", required=False)

class CollectionForm(forms.ModelForm):
    class Meta:
        model = Collection
        fields = ["title"]
        labels = {"title": "Nome da coleção"}

class ProfileForm(forms.ModelForm):
    name = forms.CharField(required=False, max_length=150, label="Nome")
    field_order = ["name", "avatar", "bio"]

    class Meta:
        model = Profile
        fields = ["avatar", "bio"]
        labels = {"avatar": "Foto de perfil", "bio": "Sobre você"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["name"].initial = self.instance.user.first_name

    def clean_avatar(self):
        return check_image_upload(self.cleaned_data.get("avatar"))

    def save(self, commit=True):
        profile = super().save(commit)
        user = profile.user
        user.first_name = self.cleaned_data["name"]
        user.save(update_fields=["first_name"])
        return profile

class AvatarForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ["avatar"]

    def clean_avatar(self):
        return check_image_upload(self.cleaned_data.get("avatar"))

class FriendSearchForm(forms.Form):
    username = forms.CharField(max_length=150, label="Nome, usuário ou e-mail")
