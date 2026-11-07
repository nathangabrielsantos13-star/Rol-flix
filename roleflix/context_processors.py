from django.conf import settings

from .views import user_notifications

def notifications(request):
    data = {"demo_mode": settings.ROLEFLIX_DEMO, "email_enabled": settings.ROLEFLIX_EMAIL_ENABLED}
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return data
    return {**data, "unread_notifications": user_notifications(user).filter(read=False).count()}
