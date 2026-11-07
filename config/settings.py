import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")
DEBUG = os.getenv("DJANGO_DEBUG", "0") == "1"
# A Vercel define VERCEL=1 e só deixa gravar em /tmp, que some a cada reinício. Veja roleflix/demo.py.
ROLEFLIX_DEMO = bool(os.getenv("VERCEL"))
HTTPS = ROLEFLIX_DEMO or os.getenv("DJANGO_HTTPS", "0") == "1"
DATA_DIR = Path(os.getenv("ROLEFLIX_DATA_DIR", "/tmp/roleflix" if ROLEFLIX_DEMO else BASE_DIR))
DATA_DIR.mkdir(parents=True, exist_ok=True)  # Banco e arquivos enviados: tudo que precisa de backup.
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    raise ImproperlyConfigured("Defina DJANGO_SECRET_KEY no arquivo .env (veja .env.example).")
hosts = [host.strip() for host in os.getenv("DJANGO_ALLOWED_HOSTS", "").split(",") if host.strip()]
if ROLEFLIX_DEMO:
    hosts.append(".vercel.app")  # O domínio final do projeto nem sempre vem nas variáveis da Vercel.
ALLOWED_HOSTS = [*hosts, "127.0.0.1", "localhost"]
CSRF_TRUSTED_ORIGINS = [f"https://*{host}" if host.startswith(".") else f"https://{host}" for host in hosts]

INSTALLED_APPS = [
    "django.contrib.admin", "django.contrib.auth", "django.contrib.contenttypes",
    "django.contrib.sessions", "django.contrib.messages", "django.contrib.staticfiles",
    "django.contrib.sites",
    "allauth", "allauth.account", "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
    "roleflix",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
]
if not DEBUG and not ROLEFLIX_DEMO:  # Na Vercel, a CDN dela entrega os arquivos estáticos.
    MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")
ROOT_URLCONF = "config.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "templates"],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.debug",
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
        "roleflix.context_processors.notifications",
    ]},
}]
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": DATA_DIR / "db.sqlite3"}}
if not DEBUG:
    # WAL deixa ler enquanto outro processo grava, como o gerador de trailers.
    DATABASES["default"]["OPTIONS"] = {
        "timeout": 20,
        "transaction_mode": "IMMEDIATE",
        "init_command": "PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;",
    }
    # Compartilhado entre os processos: os limites de tentativas de login precisam valer para todos.
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.filebased.FileBasedCache", "LOCATION": DATA_DIR / "cache"}}
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
if not DEBUG and not ROLEFLIX_DEMO:
    STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
    }
MEDIA_URL = "media/"
MEDIA_ROOT = DATA_DIR / "media"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
SITE_ID = 1

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]
ACCOUNT_SIGNUP_FORM_CLASS = "roleflix.forms.SignupExtraForm"
# Em desenvolvimento o e-mail só aparece no terminal, então a confirmação não pode bloquear a entrada.
ACCOUNT_EMAIL_VERIFICATION = "optional" if DEBUG else "none" if ROLEFLIX_DEMO else "mandatory"
# O Google garante o e-mail: quem já tem conta com senha entra na mesma conta.
# Se o e-mail da conta não estava confirmado, o allauth apaga a senha, o que barra quem o registrou antes do dono.
SOCIALACCOUNT_EMAIL_AUTHENTICATION = True
SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT = True

ACCOUNT_ADAPTER = "roleflix.adapters.ResilientAccountAdapter"
SOCIALACCOUNT_ADAPTER = "roleflix.adapters.InviteOnlySocialAdapter"

ROLEFLIX_INVITE_CODE = os.getenv("ROLEFLIX_INVITE_CODE", "").strip()
ROLEFLIX_CONTACT_EMAIL = os.getenv("ROLEFLIX_CONTACT_EMAIL", "").strip()
# Recusa envios antes de o disco lotar, o que derrubaria o site inteiro.
ROLEFLIX_MIN_FREE_DISK = 0 if DEBUG or ROLEFLIX_DEMO else 5 * 1024 ** 3

# Em desenvolvimento, os e-mails aparecem no terminal em vez de exigir um servidor SMTP.
if DEBUG or ROLEFLIX_DEMO:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
else:
    EMAIL_HOST = os.getenv("EMAIL_HOST", "")
    EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
    EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
    EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
    EMAIL_USE_TLS = True
    EMAIL_TIMEOUT = 15
    DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "Rolêflix <nao-responda@localhost>")
    SERVER_EMAIL = DEFAULT_FROM_EMAIL

if ROLEFLIX_DEMO:
    # Cada instância tem seu próprio banco temporário: a sessão precisa ficar no navegador.
    SESSION_ENGINE = "django.contrib.sessions.backends.signed_cookies"

if HTTPS:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")  # O Caddy é o único que fala com o Django.
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

# Sem isto, em produção os erros não aparecem no log do servidor.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO" if not DEBUG else "WARNING"},
}

# Configure Google OAuth credentials using environment variables.
google_id = os.getenv("GOOGLE_CLIENT_ID")
google_secret = os.getenv("GOOGLE_CLIENT_SECRET")
if google_id and google_secret:
    SOCIALACCOUNT_PROVIDERS = {
        "google": {
            "APP": {"client_id": google_id, "secret": google_secret, "key": ""},
            "SCOPE": ["profile", "email"],
            "AUTH_PARAMS": {"prompt": "select_account"},
        }
    }
