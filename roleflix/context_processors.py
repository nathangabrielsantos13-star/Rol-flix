from django.conf import settings

from . import demo
from .views import user_notifications

def notifications(request):
    data = {
        "demo_mode": settings.ROLEFLIX_DEMO, "email_enabled": settings.ROLEFLIX_EMAIL_ENABLED,
        "serverless": settings.ROLEFLIX_SERVERLESS, "max_request_file": settings.ROLEFLIX_MAX_REQUEST_FILE,
    }
    if settings.ROLEFLIX_DEMO:
        data.update(demo_email=demo.DEMO_EMAIL, demo_password=demo.DEMO_PASSWORD, demo_falta=" ".join(settings.ROLEFLIX_DEMO_FALTA))
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return data
    return {**data, "unread_notifications": user_notifications(user).filter(read=False).count()}
