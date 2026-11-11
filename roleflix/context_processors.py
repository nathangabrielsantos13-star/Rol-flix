from django.conf import settings

from .views import user_notifications

def notifications(request):
    data = {
        "email_enabled": settings.ROLEFLIX_EMAIL_ENABLED,
        "serverless": settings.ROLEFLIX_SERVERLESS, "max_request_file": settings.ROLEFLIX_MAX_REQUEST_FILE,
    }
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return data
    return {**data, "unread_notifications": user_notifications(user).filter(read=False).count()}
