#!/bin/sh
# Резервная копия базы dictionary. Запускает dictionary-backup.timer от пользователя dictionary.
set -eu
dir=/var/lib/dictionary-app/backups
keep_days=14
umask 077
mkdir -p "$dir"
file="$dir/dictionary-$(date +%F_%H%M).dump"
pg_dump -Fc -d dictionary -f "$file.part"
mv "$file.part" "$file"
find "$dir" -name 'dictionary-*.dump' -mtime +"$keep_days" -delete
echo "резервная копия: $file ($(du -h "$file" | cut -f1))"
