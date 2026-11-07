#!/bin/sh
export PATH="/usr/local/bin:/usr/bin:/bin:$PATH"  # O cron começa com um PATH mínimo.
# Cópia diária do banco e dos arquivos, guardada por 7 dias. Agende no cron do servidor.
# Fica no mesmo disco do site: copie também para fora, ou ative os backups da hospedagem.
set -eu
cd "$(dirname "$0")/.."
destino=backups
mkdir -p "$destino"
data=$(date +%Y-%m-%d)
docker compose exec -T web python -c "import sqlite3; o=sqlite3.connect('/data/db.sqlite3'); d=sqlite3.connect('/data/backup.sqlite3'); o.backup(d); d.close(); o.close()"
tar -czf "$destino/roleflix-$data.tar.gz" -C data backup.sqlite3 media
rm -f data/backup.sqlite3
find "$destino" -name 'roleflix-*.tar.gz' -mtime +7 -delete
