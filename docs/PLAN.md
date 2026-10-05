# dictionary-app: план и состояние проекта

Единственный источник правды о том, что сделано. Отметки ставятся по коду, а не по памяти.
Начало сессии с ассистентом: `cat docs/PLAN.md`; весь код — `scripts/dump_code.sh`
(→ output/code_dump.txt). Конец сессии: обновить отметки и журнал, закоммитить с кодом.

## Назначение
Подбор товаров по заявкам клиентов. Менеджер вставляет текст письма или таблицу из Excel.
Приложение находит товары (словарь синонимов из Access, артикулы, наименования),
считает цену по виду цен покупателя, распределяет резерв по остатку, проверяет кредит
и готовит выгрузку в 1С.

## Стек и правила кода
- Python 3.12, uv. Веб: FastAPI + Jinja2, gunicorn/uvicorn (веб ещё не начат).
- PostgreSQL, SQLAlchemy 2 async + psycopg 3, миграции Alembic (migrations/versions, 0001…).
- Окружение читает только app/config.py: DatabaseSettings (только БД), SourceSettings
  (выгрузки 1С), Settings (веб: вход, OCR).
- Вход: OIDC через Authentik (authlib). AUTH_MODE=dev только при APP_ENV=dev.
- Проверки (pre-commit): ruff, mypy --strict, pytest, покрытие app/ — 100 %.
  Тесты с БД — TEST_DATABASE_URL, имя базы оканчивается на _test.
- Слои: app/domain — логика без БД; app/sources — чтение файлов; app/db — работа с БД
  (транзакцией управляет вызывающий код); tools/ — команды, в покрытие не входят.

## Источники данных
| Данные                 | Откуда                                     | Как попадает             | Таблица                  |
|------------------------|--------------------------------------------|--------------------------|--------------------------|
| Каталог                | \\192.168.0.251\ftp1\distrib\distr.xlsx    | таймер, ~раз в час       | product                  |
| Покупатели             | \\192.168.0.251\ftp\CROSS\price_users.csv  | таймер, ~раз в час       | customer (замена целиком)|
| Справочник цен. групп  | ЦеновыеГруппы.xlsx                         | tools/load_prices → админка | price_document (groups)|
| Виды цен               | текст из 1С                                | tools/load_prices → админка | price_document (types) |
| Группа товара          | Номенклатура.xlsx (пока нет в distr)       | tools/load_groups        | product.price_group      |
| Синонимы               | ОбщаяНоменклатура.xlsx (Access) + менеджеры| tools/load_aliases, админка | alias (access/manager) |
| Журнал загрузок        | —                                          | —                        | source_import            |

1С обновляет distr.xlsx и price_users.csv примерно раз в час, время плавает.

## Окружение
- Разработка: ~/PycharmProjects/dictionary-app, копии выгрузок в input/
  (distr.xlsx, price_user.csv, ОбщаяНоменклатура.xlsx, Номенклатура.xlsx).
- Сервер: в одной ЛВС с 192.168.0.251. Пользователь dictionary, /opt/dictionary-app.
  Сетевые папки ТОЛЬКО НА ЧТЕНИЕ: /mnt/rossvik/ftp1, /mnt/rossvik/ftp (cifs + automount).
  Снимки выгрузок: /var/lib/dictionary-app/snapshots (StateDirectory в systemd).

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

### 5. Обмены с 1С — код готов
- [x] SourceSettings: DISTR_PATH, CUSTOMERS_PATH, SNAPSHOT_DIR, QUIET_SECONDS, MAX_DROP_PERCENT
- [x] app/sources/snapshot.py: копия «остывшего» файла + sha256
- [x] Миграция 0005: source_import.sha256, source_mtime
- [x] app/db/sync.py: пропуск неизменившихся, защита от снятия, блокировка
- [x] tools/sync_sources.py (--force), deploy/dictionary-sync.service + .timer
- [ ] Проверить на сервере (этап 6)

### 6. Развёртывание
- [ ] Пользователь dictionary, /opt/dictionary-app, uv sync --no-dev, .env, alembic upgrade head
- [ ] NTP на сервере (timedatectl): проверка «файл остыл» сравнивает часы двух серверов
- [ ] /etc/smb-rossvik.cred, /etc/fstab: cifs ro, x-systemd.automount
- [ ] Включить dictionary-sync.timer, проверить journalctl -u dictionary-sync
- [ ] Сервис веба, Nginx, HTTPS
- [ ] Резервное копирование PostgreSQL

### Мелкие правки
- [x] pricing.py: комментарий «Цена» → «Цена Дистрибьюторская»
- [ ] Имя файла покупателей: price_user.csv (код, input/) или price_users.csv (сервер)?
- [ ] tools/load_distr, load_customers: ловить ImportRejectedError, как load_aliases

## Открытые вопросы
- Точное имя csv покупателей на сервере.
- Формат выгрузки заказа в 1С.

## Журнал сессий
- 2026-10-05 (1): заведён PLAN.md. Сервер в ЛВС с 192.168.0.251.
- 2026-10-05 (2): отметки сверены с полным кодом: веба и админки ещё нет, группы грузятся
  командами. Время выгрузок 1С плавает → таймер каждые 5 минут, загрузка только
  изменившегося «остывшего» файла. Сделан код этапа 5. Следующий шаг — этап 6
  (сервер) или этап 4 (веб).
