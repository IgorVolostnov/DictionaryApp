"""Отчёт по выгрузкам перед частью 2б. Запуск: uv run python -m tools.inspect_sources input"""

from __future__ import annotations

import sys
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from decimal import Decimal
from pathlib import Path

from app.domain.normalize import normalize_key
from app.sources.access_catalog import AccessProduct, read_access_catalog
from app.sources.cells import cell_decimal, cell_text, find_columns, xlsx_rows
from app.sources.customers import CustomerRow, find_duplicates, read_price_users
from app.sources.distr import DistrItem, read_distr

SHOW = 5
CENT = Decimal("0.01")
ONE = Decimal("1.00")
GROUP = "НаименованиеПрайса"
DEALER = "Дилерская"
DISTR = "Дистрибьюторская"


def say(line: str = "") -> None:
    sys.stdout.write(line + "\n")


def sample(values: Sequence[str]) -> str:
    return f"{len(values)} {list(values[:SHOW])}"


def repeated(values: Iterable[str | None]) -> list[str]:
    counts = Counter(value for value in values if value is not None)
    return [value for value, n in counts.most_common() if n > 1]


def problems(title: str, count: int, found: Sequence[str]) -> None:
    say(f"{title}: строк {count}, замечаний {len(found)}")
    for problem in found[:SHOW]:
        say(f"    {problem}")


def products(distr: Sequence[DistrItem], access: Sequence[AccessProduct]) -> None:
    say("\n== Товары")
    say(f"distr: повторы артикулов: {sample(repeated(i.article for i in distr))}")
    quantities = Counter(str(item.quantity) for item in distr).most_common(SHOW)
    say(f"distr: «Количество», частые значения: {quantities}")
    say(f"distr: без дистрибьюторской цены: {sum(i.price_distr is None for i in distr)}")
    say(f"Access: повторы КодВ1С: {sample(repeated(p.code_1c for p in access))}")
    say(f"Access: повторы артикулов: {sample(repeated(p.article for p in access))}")
    say(f"Access: без КодВ1С: {sum(p.code_1c is None for p in access)}")
    in_distr = {item.article for item in distr}
    in_access = {p.article for p in access if p.article is not None}
    say(f"артикулы в обоих файлах: {len(in_distr & in_access)}")
    say(f"только в distr: {sample(sorted(in_distr - in_access))}")
    say(f"только в Access: {sample(sorted(in_access - in_distr))}")


def dictionary(access: Sequence[AccessProduct], distr: Sequence[DistrItem]) -> None:
    say("\n== Словарь из Access")
    owners: defaultdict[str, set[str]] = defaultdict(set)
    for product in access:
        for key in product.keys:
            owners[key].add(product.code_1c or product.article or product.name)
    with_keys = sum(bool(p.keys) for p in access)
    say(f"ключей: {len(owners)}; товаров, где есть ключи: {with_keys} из {len(access)}")
    shared = {key: sorted(who) for key, who in owners.items() if len(who) > 1}
    say(f"ключ принадлежит нескольким товарам: {len(shared)}")
    for key, who in list(shared.items())[:SHOW]:
        say(f"    {key}: {who[:SHOW]}")
    say(f"ключи не в верхнем регистре: {sample([k for k in owners if k != k.upper()])}")
    articles = {item.article for item in distr}
    orphans = sum(len(p.keys) for p in access if p.keys and p.article not in articles)
    say(f"ключей товаров, которых нет в distr: {orphans}")


def customers(rows: Sequence[CustomerRow]) -> set[str]:
    say("\n== Покупатели")
    say(f"повторы наименований: {len(repeated(r.name for r in rows))}")
    twins = find_duplicates(rows)
    total = sum(len(group) for group in twins)
    say(f"не различить (наименование и e-mail совпадают): групп {len(twins)}, покупателей {total}")
    for group in twins[:SHOW]:
        say(f"    {group[0].name}: {len(group)} шт., адресов {len(group[0].emails)}")
    owners: defaultdict[str, set[str]] = defaultdict(set)
    for row in rows:
        for email in row.emails:
            owners[email].add(row.name)
    say(f"e-mail у нескольких разных покупателей: {sum(len(n) > 1 for n in owners.values())}")
    with_email = sum(bool(r.emails) for r in rows)
    say(f"e-mail заполнен: {with_email} из {len(rows)}, несколько адресов: "
        f"{sum(len(r.emails) > 1 for r in rows)}")
    groups = Counter(r.group_emails for r in rows if r.group_emails)
    say(f"групп по emailОсновногоКонтрагента: {len(groups)}")
    say(f"    без группы: {sum(not r.group_emails for r in rows)}")
    say(f"    где больше одного покупателя: {sum(n > 1 for n in groups.values())}")
    say(f"только предоплата: {sum(r.prepayment_only for r in rows)}")
    days = Counter(str(r.deferral_days) for r in rows).most_common(SHOW)
    say(f"отсрочка, частые значения: {days}")
    types = Counter(r.price_type for r in rows)
    say(f"виды цен: {types.most_common()}")
    return set(types)



def at(row: Sequence[object], i: int) -> object:
    return row[i] if i < len(row) else None


def at_number(row: Sequence[object], i: int) -> Decimal | None:
    try:
        return cell_decimal(at(row, i))
    except ValueError:
        return None


def rounding(value: Decimal) -> str:
    if value % 1 == 0:
        return "целые"
    if value * 2 % 1 == 0:
        return "до 0.50"
    return "копейки"


def ratio_report(
    name: str, base: str, rows: Sequence[Sequence[object]], columns: dict[str, int]
) -> None:
    table: defaultdict[str, Counter[Decimal]] = defaultdict(Counter)
    kinds: Counter[str] = Counter()
    for row in rows:
        value, base_value = at_number(row, columns[name]), at_number(row, columns[base])
        if value is None or not base_value:
            continue
        group = cell_text(at(row, columns[GROUP])) or "(без группы)"
        table[group][(value / base_value).quantize(CENT)] += 1
        kinds[rounding(value)] += 1
    odd = {group: c for group, c in table.items() if set(c) != {ONE}}
    say(f"{name} (от «{base}»): {dict(kinds)}; групп, где коэффициент не 1: {len(odd)}")
    for group, counter in sorted(odd.items()):
        total = sum(counter.values())
        top = ", ".join(f"{r} в {n * 100 // total}%" for r, n in counter.most_common(3))
        say(f"    {group}: {top}")


def prices(path: Path, price_types: set[str]) -> None:
    say("\n== Виды цен: колонки Access против базовых цен")
    rows = xlsx_rows(path)
    titles = {normalize_key(cell_text(title) or "") for title in rows[0]}
    present = sorted(t for t in price_types if normalize_key(t) in titles)
    say(f"видов цен без колонки в Access: {sample(sorted(price_types - set(present)))}")
    columns = find_columns(rows[0], [GROUP, DEALER, DISTR, *present])
    for name in present:
        ratio_report(name, DEALER if name.startswith("Дилер") else DISTR, rows[1:], columns)


def main(folder: Path) -> None:
    access_path = folder / "ОбщаяНоменклатура.xlsx"
    distr = read_distr(folder / "distr.xlsx")
    users = read_price_users(folder / "price_user.csv")
    access = read_access_catalog(access_path)
    say("== Файлы")
    problems("distr.xlsx", len(distr.items), distr.problems)
    problems("price_user.csv", len(users.items), users.problems)
    problems(access_path.name, len(access.items), access.problems)
    products(distr.items, access.items)
    dictionary(access.items, distr.items)
    prices(access_path, customers(users.items))


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "input"))
