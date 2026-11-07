FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 ROLEFLIX_DATA_DIR=/data
RUN useradd --uid 1000 --create-home roleflix
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# Chave descartável: o collectstatic exige uma, e a real só existe no servidor.
RUN DJANGO_SECRET_KEY=build python manage.py collectstatic --noinput
RUN mkdir -p /data && chown -R roleflix:roleflix /app /data
USER roleflix

EXPOSE 8000
# Threads, não só processos: um envio lento de vídeo não pode travar o site para os outros.
CMD ["sh", "-c", "python manage.py migrate --noinput && python manage.py preparar_lancamento && exec gunicorn config.wsgi --bind 0.0.0.0:8000 --workers 2 --worker-class gthread --threads 8 --timeout 120 --access-logfile -"]
