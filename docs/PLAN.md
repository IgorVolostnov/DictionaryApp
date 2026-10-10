# dictionary-app: план и состояние проекта

Единственный источник правды о том, что сделано. Отметки ставятся по коду, а не по памяти.
Начало сессии с ассистентом: `cat docs/PLAN.md`; весь код — `scripts/dump_code.sh`
(→ output/code_dump.txt). Конец сессии: обновить отметки и журнал, закоммитить с кодом.

ВНИМАНИЕ АССИСТЕНТУ:
- Веба ещё НЕТ (этап 4 не начат). Не предлагать службу веба, Nginx, HTTPS, пока этап 4
  не отмечен. На сервере работают только таймеры обменов и резервных копий.
- PLAN.md присылать ТОЛЬКО целиком, готовым файлом. Правки кусками не предлагать.
- Код на сервере руками не правится: изменения делаются на ноутбуке → GitHub → git pull.

## Назначение
Подбор товаров по заявкам клиентов. Менеджер вставляет текст письма или таблицу из Excel.
Приложение находит товары (словарь синонимов из Access, артикулы, наименования),
считает цену по виду цен покупателя, распределяет резерв по остатку, проверяет кредит
и готовит выгрузку в 1С.

## Стек и правила кода
- Python 3.12, uv. Веб: FastAPI + Jinja2, gunicorn/uvicorn (веб ещё не начат).
- PostgreSQL (разработка 18, сервер 16), SQLAlchemy 2 async + psycopg 3,
  миграции Alembic (migrations/versions, 0001…).
- Окружение читает только app/config.py: DatabaseSettings (только БД), SourceSettings
  (выгрузки 1С), Settings (веб: вход, OCR).
- Вход: OIDC через Authentik (authlib). AUTH_MODE=dev только при APP_ENV=dev.
- Проверки (pre-commit): ruff, mypy --strict, pytest, покрытие app/ — 100 %.
  Тесты с БД — TEST_DATABASE_URL, имя базы оканчивается на _test.
- Слои: app/domain — логика без БД; app/sources — чтение файлов; app/db — работа с БД
  (транзакцией управляет вызывающий код); tools/ — команды, в покрытие не входят;
  scripts/ — shell-скрипты (dump_code.sh, backup_db.sh); deploy/ — unit-файлы systemd.

## Источники данных
| Данные                 | Откуда                                     | Как попадает             | Таблица                  |
|------------------------|--------------------------------------------|--------------------------|--------------------------|
| Каталог                | \\192.168.0.251\ftp1\distrib\distr.xlsx    | таймер, ~раз в час       | product                  |
| Покупатели             | \\192.168.0.251\ftp\CROSS\price_user.csv   | таймер, ~раз в час       | customer (замена целиком)|
| Справочник цен. групп  | ЦеновыеГруппы.xlsx                         | tools/load_prices → админка | price_document (groups)|
| Виды цен               | текст из 1С                                | tools/load_prices → админка | price_document (types) |
| Группа товара          | Номенклатура.xlsx (пока нет в distr)       | tools/load_groups        | product.price_group      |
| Синонимы               | ОбщаяНоменклатура.xlsx (Access) + менеджеры| tools/load_aliases, админка | alias (access/manager) |
| Журнал загрузок        | —                                          | —                        | source_import            |

1С обновляет distr.xlsx и price_user.csv примерно раз в час, время плавает.
Функция чтения покупателей называется read_price_users — это имя функции, не файла.

## Окружение
- Разработка: ноутбук, ~/PycharmProjects/dictionary-app, PostgreSQL 18.6,
  базы dictionary и dictionary_test (ru_RU.UTF-8). Вход в psql: sudo -u postgres psql.
  Копии выгрузок в input/ (distr.xlsx, price_user.csv, ОбщаяНоменклатура.xlsx, Номенклатура.xlsx).
- Код: GitHub IgorVolostnov/DictionaryApp (закрытый), ветка master.
- Сервер: ВМ dictionary, 192.168.100.20 (KVM, Cockpit), в одной ЛВС с 192.168.0.251.
  - Ubuntu 24.04.5 LTS (на 26.04 не обновлять), Python 3.12.3, uv 0.13.0 (/usr/local/bin),
    PostgreSQL 16.15, Europe/Moscow, NTP синхронизирован, ufw: открыт только SSH.
  - Вход: с офисного ПК `ssh dictionary` (ключ, ~/.ssh/config), администратор visfin (sudo).
  - Пользователь dictionary (системный): код /opt/dictionary-app, deploy key GitHub
    только на чтение (/home/dictionary/.ssh/id_ed25519).
  - База dictionary: владелец dictionary, ru_RU.UTF-8, вход peer через сокет, без пароля.
    .env (600): DATABASE_URL=postgresql+psycopg://dictionary@/dictionary?host=/var/run/postgresql,
    DISTR_PATH, CUSTOMERS_PATH, SNAPSHOT_DIR=/var/lib/dictionary-app/snapshots.
  - Сетевые папки ТОЛЬКО НА ЧТЕНИЕ: /mnt/rossvik/ftp1, /mnt/rossvik/ftp
    (/etc/fstab: cifs ro, vers=3.0, iocharset=utf8, uid=dictionary, x-systemd.automount, nofail).
    Учётка домена ALCAR в /etc/smb-rossvik.cred (root, 600). Сейчас ЛИЧНАЯ
    (ALCAR\волостновис): после смены пароля Windows сразу обновить файл
    (read -rsp … P; printf … | sudo tee …; проверка smbclient -A).
  - Таймеры (копии из deploy/ в /etc/systemd/system):
    dictionary-sync — обмены с 1С каждые 5 минут;
    dictionary-backup — pg_dump -Fc в /var/lib/dictionary-app/backups в 01:30, хранится 14 дней.
    Загрузки: journalctl -u dictionary-sync -g 'загружен|отклонён|недоступен' --since today
    Копии:    journalctl -u dictionary-backup -n 5

## Обновление сервера (после git push с ноутбука)
    cd /opt/dictionary-app
    sudo -u dictionary git pull --ff-only
    sudo -u dictionary uv sync --frozen --no-dev
    sudo -u dictionary .venv/bin/alembic upgrade head      # перед этим — резервная копия
    sudo install -m 644 -o root -g root deploy/*.service deploy/*.timer /etc/systemd/system/
    sudo systemctl daemon-reload

Перенос базы ноутбук → сервер: pg_dump --no-owner --no-privileges, вырезать строку
`SET transaction_timeout` (её нет в PostgreSQL 16), psql --single-transaction -v ON_ERROR_STOP=1.

## Принятые решения (не пересматривать без причины)
1. По умолчанию APP_ENV=prod: забытая настройка не ослабляет защиту.
2. Инструментам нужны только DatabaseSettings/SourceSettings, без секретов входа.
3. «Код в 1С» в distr.xlsx обязателен: по нему узнаём товар со сменившимся артикулом.
4. Товары не удаляются, а получают active=False: на них ссылаются словарь и заявки.
5. Покупатели заменяются целиком; заявки хранят копию данных покупателя, а не ссылку.
6. Группа товара — из Номенклатура.xlsx, пока в distr нет «ЦеноваяГруппа». Справочник
   групп и виды цен — загрузки в price_document, действует последняя.
7. Таблицы нормализации (копия VBA «Преобразование») не менять: сломается словарь Access.
8. Поиск объединяет словарь, артикул и наименование. Несколько активных товаров —
   строка неоднозначна, выбирает менеджер. Снятые показываем, только если нет активных.
   Порядок кандидатов — как на сайте («Сортировка на сайте»).
9. Резерв распределяется по строкам заявки сверху вниз.
10. Нулевая или пустая базовая цена никогда не уходит в 1С.
11. Выгрузки 1С: таймер каждые 5 минут. Читается копия файла, который не менялся
    QUIET_SECONDS (120) и во время копирования. Файл с тем же mtime или sha256 не грузится.
12. Загрузка отклоняется, если пропадает больше MAX_DROP_PERCENT (20 %) активных
    товаров или покупателей. --force — только решение администратора.
13. Один источник грузит один процесс: pg_try_advisory_xact_lock(hashtext(lock_name)).
    Ручная загрузка из админки обязана брать ту же блокировку.
14. Свежесть данных = время файла 1С: max(source_import.source_mtime) по источнику.
15. На сервере код руками не правится: только git pull. Unit-файлы копируются
    в /etc/systemd/system (владелец root), а не ссылками на /opt: иначе пользователь
    dictionary мог бы изменить службу и получить root.
16. Пароль домена в /etc/smb-rossvik.cred сначала проверяется `smbclient -A`, потом fstab:
    неверный пароль + таймер каждые 5 минут = блокировка учётки в домене.
17. Резервная копия: pg_dump -Fc от пользователя dictionary, запись в .part и затем mv
    (оборванная копия не выглядит готовой), umask 077, хранится 14 дней.
    Синонимы менеджеров и заявки есть только в базе — их не восстановить из 1С.

## Этапы

### 1. Основа — готово
- [x] Настройки, модели, миграции 0001–0004

### 2. Источники и загрузка командами — готово
- [x] distr.xlsx: sources/distr.py → db/products.py (import_distr); tools/load_distr
- [x] Покупатели: sources/customers.py → db/customers.py; tools/load_customers
- [x] Словарь Access: sources/access_catalog.py → db/aliases.py; tools/load_aliases
- [x] Справочник групп и виды цен: domain/price_types.py, db/prices.py; tools/load_prices
- [x] Группа товара из Номенклатура.xlsx: update_price_groups; tools/load_groups
- [x] Отчёт по выгрузкам: tools/inspect_sources

### 3. Предметная логика
- [x] normalize (эталон Excel), parse_input, search + order_match, reserve, pricing, credit
- [x] tools/find_lines: разбор заявки и поиск из консоли
- [ ] Собрать результат подбора: цена + резерв + кредит по строкам (сейчас отдельные функции)
- [ ] OCR Yandex Vision (есть только настройки)

### 4. Веб — не начат
- [ ] app/main.py, обработчик DomainError → 4xx
- [ ] Вход через Authentik (OIDC)
- [ ] Подбор: вставка заявки, выбор покупателя, результат с ценами, резервом, кредитом
- [ ] Неоднозначные строки: выбор товара и добавление синонима (source=manager)
- [ ] Админка: справочник групп, виды цен, синонимы, ручная загрузка выгрузок
      (lock_name + подтверждение при большом снятии)
- [ ] Предупреждение: данным больше STALE_AFTER_MINUTES (по решению 14)
- [ ] Выгрузка в 1С (формат уточнить)

### 5. Обмены с 1С — готово
- [x] SourceSettings: DISTR_PATH, CUSTOMERS_PATH, SNAPSHOT_DIR, QUIET_SECONDS, MAX_DROP_PERCENT
- [x] app/sources/snapshot.py: копия «остывшего» файла + sha256
- [x] Миграция 0005: source_import.sha256, source_mtime
- [x] app/db/sync.py: пропуск неизменившихся, защита от снятия, блокировка
- [x] tools/sync_sources.py (--force), deploy/dictionary-sync.service + .timer
- [x] Проверено на сервере 2026-10-10: distr 5027 (+2/−2), customers 2022 (+18/−2),
      повторный запуск — пусто, таймер каждые 5 минут без ошибок

### 6. Развёртывание — обмены работают, резервные копии в работе
- [x] ВМ dictionary: Ubuntu 24.04.5, диск 57 ГБ, Europe/Moscow, ufw, qemu-guest-agent
- [x] NTP: timedatectl — synchronized: yes
- [x] PostgreSQL 16.15, база dictionary (ru_RU.UTF-8, peer), данные с ноутбука
      перенесены дампом и сверены (alias 26299, customer 2006, product 5028), alembic 0005
- [x] Пользователь dictionary, deploy key, /opt/dictionary-app, uv sync --frozen --no-dev, .env
- [x] /etc/smb-rossvik.cred, /etc/fstab: cifs ro, x-systemd.automount; запись запрещена (проверено)
- [x] Ручной запуск tools.sync_sources на сервере
- [x] dictionary-sync.timer включён, запуски каждые 5 минут без ошибок
- [x] scripts/backup_db.sh, deploy/dictionary-backup.service + .timer (код)
- [ ] dictionary-backup.timer: установить на сервере, проверить копию (pg_restore -l → 6 TABLE DATA)
- [ ] Копии вне ВМ (место не выбрано: хост KVM / Yandex Object Storage / 192.168.0.251)
- [ ] Служебная учётка домена от ИТ (только чтение ftp1\distrib, ftp\CROSS) вместо личной
- [ ] Сервис веба, Nginx, HTTPS — ТОЛЬКО после этапа 4

### Мелкие правки
- [x] pricing.py: комментарий «Цена» → «Цена Дистрибьюторская»
- [x] Имя файла покупателей: price_user.csv — и на сервере, и в коде
- [x] «price_users.csv» убран из deploy/dictionary-sync.service, app/db/sync.py, tests/db/test_sync.py
- [ ] tools/load_distr, load_customers: ловить ImportRejectedError, как load_aliases

## Открытые вопросы
- Формат выгрузки заказа в 1С.
- Когда ИТ выдаст служебную учётку домена ALCAR.
- Где хранить резервные копии вне ВМ; есть ли доступ к хосту KVM.

## Журнал сессий
- 2026-10-05 (1): заведён PLAN.md. Сервер в ЛВС с 192.168.0.251.
- 2026-10-05 (2): отметки сверены с полным кодом: веба и админки ещё нет, группы грузятся
  командами. Время выгрузок 1С плавает → таймер каждые 5 минут, загрузка только
  изменившегося «остывшего» файла. Сделан код этапа 5. Следующий шаг — этап 6
  (сервер) или этап 4 (веб).
- 2026-10-05 (3): этап 5 проверен локально: 240 тестов, покрытие 100 %, миграция 0005.
  sync_sources: distr 5027 товаров, customers 2006; повторный запуск ничего не грузит.
  Следующий шаг — этап 6: сбор сведений о сервере.
- 2026-10-10 (4): развёрнута ВМ dictionary (192.168.100.20): система, PostgreSQL 16,
  код с GitHub, .env, сетевые папки 1С (домен ALCAR, пока личная учётка), база перенесена
  с ноутбука (18.6 → 16.15) и сверена.
- 2026-10-10 (5): на сервере включён dictionary-sync.timer, обмены проверены (этап 5 готов).
  Добавлены scripts/backup_db.sh и dictionary-backup.{service,timer}; price_users.csv
  исправлен на price_user.csv. Следующий шаг — включить dictionary-backup.timer на сервере,
  выбрать место для копий вне ВМ, затем этап 3 (результат подбора) и этап 4 (веб).
