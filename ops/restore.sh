#!/usr/bin/env bash
# Restore from a backup pair. Destructive: it drops the current database.
set -euo pipefail

DUMP="${1:?kullanim: restore.sh <db-YYYYmmdd-HHMMSS.dump> [attachments-*.tar.gz]}"
BLOBS="${2:-}"

read -r -p "Mevcut veritabani SILINECEK. Devam? (evet/hayir) " answer
[ "$answer" = "evet" ] || { echo "vazgecildi"; exit 1; }

echo "servis durduruluyor…"
docker compose stop api web

docker compose exec -T db psql -U "${DB_USER:-tm}" -d postgres \
  -c "DROP DATABASE IF EXISTS ${DB_NAME:-testmgmt};" \
  -c "CREATE DATABASE ${DB_NAME:-testmgmt} OWNER ${DB_USER:-tm};"

echo "veritabani geri yukleniyor…"
docker compose exec -T db pg_restore -U "${DB_USER:-tm}" \
  -d "${DB_NAME:-testmgmt}" --no-owner < "$DUMP"

if [ -n "$BLOBS" ]; then
  echo "ekler geri yukleniyor…"
  docker compose run --rm -v "$(realpath "$(dirname "$BLOBS")")":/backup \
    -v testmanagement_attachments:/data alpine \
    sh -c "rm -rf /data/* && tar xzf /backup/$(basename "$BLOBS") -C /data"
fi

docker compose start api web
echo "tamam."
