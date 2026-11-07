import os
from django.core.wsgi import get_wsgi_application
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
application = get_wsgi_application()

from roleflix import demo  # noqa: E402  Só pode ser importado depois de o Django iniciar.

demo.prepare()
