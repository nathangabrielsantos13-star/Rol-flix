from .views import user_notifications

def notifications(request):
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {}
    return {"unread_notifications": user_notifications(user).filter(read=False).count()}
