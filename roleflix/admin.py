from django.contrib import admin
from .models import Profile, FriendRequest, Album, AlbumParticipant, MediaItem
admin.site.register([Profile, FriendRequest, Album, AlbumParticipant, MediaItem])
