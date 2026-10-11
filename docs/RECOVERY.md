# Восстановление сервера dictionary

Пошаговая инструкция по восстановлению приложения-словаря на новом сервере.

## Сценарии восстановления

| Сценарий | Источник данных | Время восстановления |
|----------|-----------------|---------------------|
| Сбой ВМ (диск) | Последняя копия на ноутбуке | 2-3 часа |
| Полный отказ сервера | Последняя копия на внешнем HDD | 2-3 часа |
| Миграция на новый хост | Последняя копия на ноутбуке | 2-3 часа |

## Необходимые данные

1. **Резервная копия базы** — файл `.dump` из:
   - Yandex Cloud Storage: bucket `dictionary-backups`, ключ `dictionary-app/dictionary-YYYY-MM_DDHH.dump`
   - Ноутбук: `~/backups/dictionary-app/dictionary-YYYY-MM_DDHH.dump` (через rclone sync с ноутбука)
   - Внешний HDD: `/media/visfin/dictionary-backups/dictionary-YYYY-MM_DDHH.dump` (ручное копирование)

2. **SSH-ключи** — deploy key для GitHub (read-only)
   - Файл: `/home/dictionary/.ssh/id_ed25519`
   - Если нет — восстановить из GitHub repo settings

3. **Данные для .env**:
   - `DATABASE_URL` — не нужен (создаётся заново)
   - `DISTR_PATH` — путь к сетевой папке 1С
   - `CUSTOMERS_PATH` — путь к сетевой папке 1С
   - `SNAPSHOT_DIR` — `/var/lib/dictionary-app/snapshots`

## Шаг 1: Подготовка нового сервера

```bash
# 1.1. Установить Ubuntu 24.04 LTS (не 26.04!)
# 1.2. Настроить hostname и IP
sudo hostnamectl set-hostname dictionary
sudo systemctl enable systemd-networkd

# 1.3. Настроить NTP (критично для PostgreSQL и синхронизации)
sudo timedatectl set-timezone Europe/Moscow
sudo timedatectl set-ntp true
# Проверить:
timedatectl status  # должно быть: synchronized: yes

# 1.4. Настроить UFW (только SSH)
sudo ufw allow 22/tcp
sudo ufw enable

# 1.5. Настроить SSH (ключ, без пароля)
# Скопировать ~/.ssh/authorized_keys с старого сервера
# Или добавить новый ключ:
mkdir -p ~/.ssh
chmod 700 ~/.ssh
# Вставить публичный ключ в authorized_keys

# 1.6. Настроить ~/.ssh/config для доступа к сетевым папкам 1С
# (если используется ssh-based mount)
```

## Шаг 2: Установка зависимостей

```bash
# 2.1. PostgreSQL 16
sudo apt update
sudo apt install -y postgresql-16

# 2.2. Python 3.12 и uv
sudo apt install -y python3.12 python3.12-venv python3.12-dev
curl -LsSf https://astral.sh/uv/install.sh | sh
# Добавить в ~/.bashrc:
# export PATH="$HOME/.local/bin:$PATH"

# 2.3. CIFS utils (для сетевых папок 1С)
sudo apt install -y cifs-utils

# 2.4. rsync (для offsite backup)
sudo apt install -y rsync

# 2.5. qemu-guest-agent (если ВМ на KVM)
sudo apt install -y qemu-guest-agent
sudo systemctl enable --now qemu-guest-agent
```

## Шаг 3: Создание пользователя и базы

```bash
# 3.1. Создать системного пользователя dictionary
sudo useradd -r -s /bin/bash -d /opt/dictionary-app dictionary
sudo mkdir -p /opt/dictionary-app
sudo chown dictionary:dictionary /opt/dictionary-app

# 3.2. Создать базу данных
sudo -u postgres createdb -O dictionary -T template0 -E UTF8 -l ru_RU.UTF-8 dictionary

# 3.3. Настроить peer-аутентификацию
# Добавить в /etc/postgresql/16/main/pg_hba.conf:
#   local   dictionary   dictionary                        peer
sudo -u postgres pg_ctlcluster 16 main reload
```

## Шаг 4: Восстановление базы из копии

```bash
# 4.1. Скопировать .dump файл на сервер
# С ноутбука:
scp ~/backups/dictionary-app/dictionary-2026-10-11_0200.dump \
    dictionary:/tmp/dictionary-latest.dump

# 4.2. Скачать .dump из YC Cloud Storage
# На ноутбуке:
rclone copy yc-dictionary:/dictionary-app/ ~/backups/dictionary-app/
# Или на сервере (если rclone уже настроен):
rclone copy yc-dictionary:/dictionary-app/ /tmp/

# 4.3. Остановить таймеры (если работают)
sudo systemctl stop dictionary-sync.timer
sudo systemctl stop dictionary-backup.timer

# 4.5. Восстановить базу
sudo -u dictionary pg_restore \
    --no-owner \
    --exit-on-error \
    -d dictionary \
    /tmp/dictionary-*.dump

# 4.6. Проверить восстановление
for db in dictionary; do
    sudo -u dictionary psql -d "$db" -tAc \
        "select '$db', (select count(*) from product), (select count(*) from customer), (select count(*) from alias), (select version_num from alembic_version)"
done
# Ожидаемый вывод:
# dictionary|5030|2022|26299|0005
```

## Шаг 5: Развёртывание кода

```bash
# 5.1. Клонировать репозиторий
cd /opt/dictionary-app
sudo -u dictionary git clone git@github.com:IgorVolostnov/DictionaryApp.git .

# 5.2. Настроить deploy key
sudo -u dictionary ssh-keyscan 192.168.0.251 >> /home/dictionary/.ssh/known_hosts
# Скопировать deploy key из резервной копии или GitHub settings

# 5.3. Установить зависимости
sudo -u dictionary uv sync --frozen --no-dev

# 5.4. Создать .env
sudo -u dictionary tee /opt/dictionary-app/.env > /dev/null << 'EOF'
DATABASE_URL=postgresql+psycopg://dictionary@/dictionary?host=/var/run/postgresql
DISTR_PATH=/mnt/rossvik/ftp1/distrib/distr.xlsx
CUSTOMERS_PATH=/mnt/rossvik/ftp/CROSS/price_user.csv
SNAPSHOT_DIR=/var/lib/dictionary-app/snapshots
EOF
sudo chmod 600 /opt/dictionary-app/.env
sudo chown dictionary:dictionary /opt/dictionary-app/.env

# 5.5. Применить миграции
sudo -u dictionary uv run alembic upgrade head
```

## Шаг 6: Настройка сетевых папок

```bash
# 6.1. Создать учётные данные для CIFS
# Получить учётку от ИТ (только чтение ftp1\distrib, ftp\CROSS)
sudo tee /etc/smb-rossvik.cred > /dev/null << 'EOF'
username=ALCAR\волостновис
password=ВАШ_ПАРОЛЬ
EOF
sudo chmod 600 /etc/smb-rossvik.cred

# 6.2. Добавить в /etc/fstab (RO, auto-mount)
sudo tee -a /etc/fstab > /dev/null << 'EOF'
//192.168.0.251/ftp1/distrib  /mnt/rossvik/ftp1    cifs  ro,vers=3.0,iocharset=utf8,uid=dictionary,credentials=/etc/smb-rossvik.cred,x-systemd.automount,nofail  0 0
//192.168.0.251/ftp/CROSS     /mnt/rossvik/ftp     cifs  ro,vers=3.0,iocharset=utf8,uid=dictionary,credentials=/etc/smb-rossvik.cred,x-systemd.automount,nofail  0 0
EOF

# 6.3. Проверить монтирование
sudo mount -a
ls -la /mnt/rossvik/ftp1/distr.xlsx
ls -la /mnt/rossvik/ftp/CROSS/price_user.csv
```

## Шаг 7: Настройка systemd сервисов

```bash
# 7.1. Скопировать unit-файлы
sudo install -m 644 -o root -g root /opt/dictionary-app/deploy/*.service \
    /opt/dictionary-app/deploy/*.timer /etc/systemd/system/

# 7.2. Перезагрузить daemon
sudo systemctl daemon-reload

# 7.3. Включить таймеры
sudo systemctl enable --now dictionary-sync.timer
sudo systemctl enable --now dictionary-backup.timer
sudo systemctl enable --now dictionary-backup-rclone.timer

# 7.4. Проверить
systemctl list-timers 'dictionary-*'
```

## Шаг 8: Проверка работы

```bash
# 8.1. Проверить таймеры
systemctl list-timers 'dictionary-*'

# 8.2. Запустить sync вручную
sudo -u dictionary /opt/dictionary-app/.venv/bin/python -m tools.sync_sources

# 8.3. Проверить логи
journalctl -u dictionary-sync -n 20
journalctl -u dictionary-backup -n 20

# 8.4. Проверить данные в базе
sudo -u dictionary psql -d dictionary -c \
    "select count(*) as products from product; select count(*) as customers from customer; select count(*) as aliases from alias;"

# 8.5. Проверить свежесть данных
sudo -u dictionary psql -d dictionary -c \
    "select source, max(source_mtime) from source_import group by source;"
```

## Шаг 9: Настройка offsite backup

```bash
# 9.1. Настроить rclone на ВМ
# Установить rclone:
sudo apt install -y rclone

# Настроить YC Object Storage:
sudo -u dictionary rclone config
# Ввести:
#   name: yc-dictionary
#   type: s3
#   provider: Yandex
#   access_key_id: <ваш_access_key>
#   secret_access_key: <ваш_secret_key>
#   endpoint: storage.yandexcloud.net

# 9.2. Настроить rclone на ноутбуке (для скачивания копий)
# На ноутбуке:
rclone config
# Та же конфигурация yc-dictionary

# 9.3. Проверить синхронизацию с ВМ на ноутбук
rclone copy yc-dictionary:/dictionary-app/ ~/backups/dictionary-app/

# 9.4. Проверить сервис rclone backup
sudo systemctl start dictionary-backup-rclone.service
sudo journalctl -u dictionary-backup-rclone -n 20
```

## Шаг 10: Автоматический старт после сбоя питания

Все systemd сервисы автоматически стартуют при загрузке благодаря:
- `WantedBy=multi-user.target` в unit-файлах
- `Restart=on-failure` для всех сервисов
- `x-systemd.automount` для сетевых папок

Проверить:
```bash
# Проверить, что сервисы включены на автозагрузку
systemctl is-enabled dictionary-sync.timer
systemctl is-enabled dictionary-backup.timer
systemctl is-enabled dictionary-backup-offsite.timer

# Проверить, что сетевые папки смонтируются автоматически
grep x-systemd.automount /etc/fstab
```

## Диагностика

### Сервис не запускается
```bash
sudo journalctl -u dictionary-sync -n 50 --no-pager
sudo -u dictionary /opt/dictionary-app/.venv/bin/python -m tools.sync_sources
```

### База не восстанавливается
```bash
# Проверить версию PostgreSQL
psql --version
# Должно быть: psql (PostgreSQL) 16.x

# Проверить кодировку
sudo -u postgres psql -c "SELECT datname, pg_encoding_to_char(encoding) FROM pg_database WHERE datname='dictionary';"
# Должно быть: dictionary | UTF8

# Проверить миграции
sudo -u dictionary psql -d dictionary -c "select * from alembic_version;"
# Должно быть: 0005
```

### Сетевая папка не монтируется
```bash
# Проверить учётные данные
smbclient -L //192.168.0.251 -A /etc/smb-rossvik.cred
# Проверить fstab
cat /etc/fstab | grep cifs
# Перемонтировать вручную
sudo mount -a
```

## Чек-лист восстановления

- [ ] Ubuntu 24.04 LTS установлена
- [ ] NTP синхронизирован
- [ ] UFW настроен (только SSH)
- [ ] SSH-ключи настроены
- [ ] PostgreSQL 16 установлен
- [ ] Python 3.12 + uv установлены
- [ ] CIFS utils установлены
- [ ] Пользователь dictionary создан
- [ ] База dictionary создана (UTF8, ru_RU)
- [ ] База восстановлена из .dump
- [ ] Данные проверены (product, customer, alias)
- [ ] Код клонирован из GitHub
- [ ] Зависимости установлены (uv sync)
- [ ] .env создан
- [ ] Миграции применены (alembic upgrade head)
- [ ] Сетевые папки смонтированы (RO)
- [ ] systemd сервисы скопированы
- [ ] Таймеры включены
- [ ] Sync запущен вручную
- [ ] Логи проверены
- [ ] Offsite backup настроен (rclone + YC Object Storage)
- [ ] Автозапуск после сбоя проверен
