"""Exclusão de conta. O banco apaga em cascata, mas os arquivos no disco precisam sair à mão."""
from .models import Album, CoverDesign, MediaItem, Profile, Ticket


def album_files(album):
    files = [item.file for item in album.media.all()]
    if album.cover:
        files.append(album.cover)
    for trailer in album.trailers.all():
        files.extend(field for field in (trailer.file, trailer.music_file) if field)
    design = CoverDesign.objects.filter(album=album).first()
    if design:
        files.append(design.background)
    files.extend(ticket.image for ticket in album.tickets.all())
    return files


def delete_files(files):
    for field in files:
        field.storage.delete(field.name)


def delete_account(user):
    """Apaga a pessoa, seus álbuns e o que ela enviou aos álbuns de amigos."""
    files = []
    for album in Album.objects.filter(owner=user):
        files.extend(album_files(album))
    files.extend(item.file for item in MediaItem.objects.filter(uploaded_by=user).exclude(album__owner=user))
    files.extend(ticket.image for ticket in Ticket.objects.filter(created_by=user).exclude(album__owner=user))
    profile = Profile.objects.filter(user=user).first()
    if profile and profile.avatar:
        files.append(profile.avatar)
    user.delete()
    delete_files(files)
