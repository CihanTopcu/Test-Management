#!/usr/bin/env bash
# Nightly backup: database dump plus the attachment blobs.
#
# The blobs are the part that cannot be regenerated -- a database can be
# rebuilt from the TestRail export while that subscription lasts, the
# attachments cannot.
set -euo pipefail

STAMP="$(date +%Y%m%d-%H%M%S)"
DIR="${1:-./backups}"
KEEP_DAYS="${KEEP_DAYS:-30}"
mkdir -p "$DIR"

echo "[$(date +%T)] veritabani yedekleniyor…"
docker compose exec -T db pg_dump -U "${DB_USER:-tm}" -Fc "${DB_NAME:-testmgmt}" \
  > "$DIR/db-$STAMP.dump"

echo "[$(date +%T)] ekler yedekleniyor…"
docker compose run --rm -v "$(realpath "$DIR")":/backup \
  -v testmanagement_attachments:/data alpine \
  tar czf "/backup/attachments-$STAMP.tar.gz" -C /data .

echo "[$(date +%T)] $KEEP_DAYS gunden eski yedekler siliniyor…"
find "$DIR" -name 'db-*.dump' -mtime +"$KEEP_DAYS" -delete
find "$DIR" -name 'attachments-*.tar.gz' -mtime +"$KEEP_DAYS" -delete

echo "[$(date +%T)] tamam:"
ls -lh "$DIR" | tail -4
