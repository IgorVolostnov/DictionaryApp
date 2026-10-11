#!/bin/sh
# Копия последней резервной базы в Yandex Cloud Storage через rclone.
#
# Переменные окружения:
#   RCLONE_REMOTE — имя rclone-удаления (по умолчанию: yc-dictionary)
#
# Пример:
#   rclone sync /var/lib/dictionary-app/backups/ yc-dictionary:/dictionary-backups/ \
#       --include='dictionary-*.dump' --max-age=30d --log-file=/var/log/dictionary-backup-rclone.log \
#       --log-level=NOTICE

set -eu

RCLONE_REMOTE="${RCLONE_REMOTE:-yc-dictionary}"
BACKUP_DIR=/var/lib/dictionary-app/backups

# rclone sync: синхронизирует локальную директорию с облаком
# --include: только файлы резервных копий
# --max-age: удалять копии старше 30 дней (на всякий случай, main cleanup — в backup_db.sh)
# --ignore-existing: не перезаписывать существующие файлы (быстрее при повторных запусках)
# --log-level=NOTICE: только важные сообщения

rclone sync "$BACKUP_DIR" "$RCLONE_REMOTE:/dictionary-app/" \
    --include='dictionary-*.dump' \
    --max-age=30d \
    --ignore-existing \
    --log-file=/var/log/dictionary-backup-rclone.log \
    --log-level=NOTICE

echo "копия в YC Cloud Storage отправлена"
