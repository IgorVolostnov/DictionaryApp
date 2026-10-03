from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from typing import Any

import openpyxl
import pytest

from app.sources import access_catalog, cells, customers, distr, price_groups

DISTR_VALUES: dict[str, object] = {
    "Артикул": "CA102150150",
    "Наименование": "(CA102150150) Насадка на выхлопную трубу 102мм",
    "ШтрихКод": "4655753254703",
    "Количество": "1",
    "Цена Дистрибьюторская": "2870",
    "Цена Дилерская": "3005",
    "Цена Розничная": "4020",
    "МОЦ": "3819",
    "Бренд": "ROSSVIK",
    "Детальное описание": None,
    "Основное фото": "/upload/a.jpg",
    "Дополнительные фото": "/upload/b.jpg; /upload/c.jpg;",
    "Вес (грамм)": "1900",
    "Длина (мм)": "310",
    "Ширина (мм)": "170",
    "Высота (мм)": "170",
    "Объем, м3": "0.008959",
    "Комплектация [KOMPLEKTATSIYA]": None,
    "Страна производства [COUNTRY]": "КИТАЙ",
    "Ссылка на сертификат [SSYLKA_NA_SERTIFIKAT]": None,
    "Срок действия сертификата [SROK_DEYSTVIYA_SERTIFIKATA]": "None",
}
DISTR_ITEM = distr.DistrItem(
    article="CA102150150",
    code_1c=None,
    name="(CA102150150) Насадка на выхлопную трубу 102мм",
    barcode="4655753254703",
    quantity=Decimal(1),
    price_distr=Decimal(2870),
    price_dealer=Decimal(3005),
    price_retail=Decimal(4020),
    price_min_retail=Decimal(3819),
    brand="ROSSVIK",
    description=None,
    photo="/upload/a.jpg",
    extra_photos=("/upload/b.jpg", "/upload/c.jpg"),
    weight_g=Decimal(1900),
    length_mm=Decimal(310),
    width_mm=Decimal(170),
    height_mm=Decimal(170),
    volume_m3=Decimal("0.008959"),
    package=None,
    country="КИТАЙ",
    certificate_url=None,
    certificate_until=None,
    price_group="РУБ",
)
# Как в настоящем distr.xlsx: в заголовке «Бренд» латинская e (\u0065).
DISTR_HEADER = [name.replace("Бренд", "Бр\u0065нд") for name in distr.COLUMNS]


def write_xlsx(path: Path, rows: Sequence[Sequence[object]]) -> Path:
    book: Any = openpyxl.Workbook()
    for row in rows:
        book.active.append(list(row))
    book.save(path)
    return path


def distr_row(changes: dict[str, object] | None = None) -> list[object]:
    values = DISTR_VALUES | (changes or {})
    return [values[name] for name in distr.COLUMNS]


def write_csv(path: Path, *lines: str) -> Path:
    header = ";".join(customers.COLUMNS) + ";"
    path.write_text("\r\n".join([header, *lines]) + "\r\n", encoding="utf-8-sig")
    return path


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(None, None), ("", None), (" None ", None), (" Ключ ", "Ключ"), (24, "24")],
)
def test_cell_text(raw: object, expected: str | None) -> None:
    assert cells.cell_text(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, None),
        (" ", None),
        (1855, Decimal(1855)),
        ("0.0018", Decimal("0.0018")),
        ("12\u00a0345,67", Decimal("12345.67")),
        (5.86e-07, Decimal("5.86E-7")),
    ],
)
def test_cell_decimal(raw: object, expected: Decimal | None) -> None:
    assert cells.cell_decimal(raw) == expected


@pytest.mark.parametrize("raw", ["abc", "1,2,3", "NaN", "Infinity"])
def test_cell_decimal_rejects_non_numbers(raw: str) -> None:
    with pytest.raises(ValueError, match="ожидалось число"):
        cells.cell_decimal(raw)


def test_find_columns_ignores_spaces_and_lookalikes() -> None:
    header = [" Бр\u0065нд ", None, "Артикул"]
    assert cells.find_columns(header, ["Артикул", "Бренд"]) == {"Артикул": 2, "Бренд": 0}


def test_find_columns_reports_missing() -> None:
    with pytest.raises(cells.SourceFormatError, match="Отсутствуют колонки: МОЦ"):
        cells.find_columns(["Артикул"], ["Артикул", "МОЦ"])


def _join(row: cells.Record) -> str:
    return row.required("a") + (row.text("b") or "-")


def test_load_skips_empty_rows_and_collects_problems() -> None:
    rows: list[Sequence[object]] = [["A", "B"], ["x", "y"], [None, " "], ["", "z"], ["w"]]
    loaded = cells.load(rows, ["a", "b"], _join)
    assert loaded.items == ("xy", "w-")
    assert loaded.problems == ("строка 4: пустая колонка «a»",)


def test_load_rejects_empty_file() -> None:
    with pytest.raises(cells.SourceFormatError, match="пустой"):
        cells.load([], ["a"], _join)


def test_xlsx_rows_rejects_other_files(tmp_path: Path) -> None:
    path = tmp_path / "distr.xlsx"
    path.write_text("Артикул;Наименование", encoding="utf-8")
    with pytest.raises(cells.SourceFormatError, match="ошибка открытия xlsx"):
        cells.xlsx_rows(path)


def test_distr_reads_items_and_problems(tmp_path: Path) -> None:
    rows: list[Sequence[object]] = [
        DISTR_HEADER,
        distr_row(),
        distr_row({"Артикул": None}),
        distr_row({"Вес (грамм)": "1,9 кг"}),
    ]
    loaded = distr.read_distr(write_xlsx(tmp_path / "distr.xlsx", rows))
    assert loaded.items == (DISTR_ITEM,)
    assert loaded.problems == (
        "строка 3: пустая колонка «Артикул»",
        "строка 4: «Вес (грамм)»: «1,9 кг»: ожидалось число",
    )


def test_distr_requires_all_columns(tmp_path: Path) -> None:
    path = write_xlsx(tmp_path / "distr.xlsx", [DISTR_HEADER[:-1]])
    with pytest.raises(cells.SourceFormatError, match="SROK_DEYSTVIYA"):
        distr.read_distr(path)


def test_price_users(tmp_path: Path) -> None:
    path = write_csv(
        tmp_path / "price_user.csv",
        'Фирма "Ромашка";;Дилерская;0;7;;Sale@Podnimi.net;end;',
        "ИП Иванов;a@b.ru, C@d.ru; a@b.ru;Дистр_30;150 000,50;30;12345,6;e@f.ru; x;end;",
        "Фирма; Лютик;;Дилерская;1;7;;;end;",
        "Фирма;Лютик;;Дилерская;0;7;;;end;",
        "ИП Петров;;Дилерская;0;7,5;;;end;",
        "",
        "ИП Сидоров;;Розничная;;;;;end;",
    )
    loaded = customers.read_price_users(path)
    assert loaded.items == (
        customers.CustomerRow(
            'Фирма "Ромашка"', (), "Дилерская", Decimal(0), 7, None, ("sale@podnimi.net",)
        ),
        customers.CustomerRow(
            "ИП Иванов",
            ("a@b.ru", "c@d.ru"),
            "Дистр_30",
            Decimal("150000.50"),
            30,
            Decimal("12345.6"),
            ("e@f.ru",),
        ),
        customers.CustomerRow("Фирма; Лютик", (), "Дилерская", Decimal(1), 7, None, ()),
        customers.CustomerRow("ИП Сидоров", (), "Розничная", None, None, None, ()),
    )
    assert loaded.problems == (
        "строка 5: сдвиг полей: лишняя или потерянная «;»",
        "строка 6: «МаксимальнаяОтсрочкаОплаты»: 7.5 — нужно целое число дней",
    )


@pytest.mark.parametrize(
    ("limit", "expected"),
    [(None, True), (Decimal(0), True), (Decimal(1), True), (Decimal(15000), False)],
)
def test_prepayment_only(limit: Decimal | None, expected: bool) -> None:
    row = customers.CustomerRow("ИП", (), "Дилерская", limit, None, None, ())
    assert row.prepayment_only is expected


def test_find_duplicates() -> None:
    a = customers.CustomerRow("Частное лицо", (), "Все_10", None, None, None, ())
    b = replace(a, name="частное  лицо", price_type="Все_5")
    c = replace(a, emails=("a@b.ru",))
    d = replace(a, name="ИП Иванов")
    assert customers.find_duplicates([a, b, c, d]) == [(a, b)]



def test_price_users_requires_utf8(tmp_path: Path) -> None:
    path = tmp_path / "price_user.csv"
    path.write_bytes(";".join(customers.COLUMNS).encode("cp1251"))
    with pytest.raises(cells.SourceFormatError, match="UTF-8"):
        customers.read_price_users(path)


def test_access_catalog(tmp_path: Path) -> None:
    keys = "YL90L222220 024OSNOVANIE\u200b YL90L222220 \u200b SOEDINITEL'NYJ"
    rows: list[Sequence[object]] = [
        ["Код", *access_catalog.COLUMNS, "Дилер_0"],
        [13708, "ЦБ0001", "024", "Основание коробки", "Запчасти", "Поршневые", "ROSSVIK",
         keys, 185],
        [13726, None, "2004501", "Головка", None, None, None, None, 3258],
        [13727, None, None, "Без кода", None, None, None, None, 1],
    ]  # fmt: skip
    loaded = access_catalog.read_access_catalog(write_xlsx(tmp_path / "access.xlsx", rows))
    assert loaded.items == (
        access_catalog.AccessProduct(
            code_1c="ЦБ0001",
            article="024",
            name="Основание коробки",
            price_group="Запчасти",
            subgroup="Поршневые",
            brand="ROSSVIK",
            keys=("YL90L222220", "024OSNOVANIE", "SOEDINITEL'NYJ"),
        ),
        access_catalog.AccessProduct(
            code_1c=None,
            article="2004501",
            name="Головка",
            price_group=None,
            subgroup=None,
            brand=None,
            keys=(),
        ),
    )
    assert loaded.problems == ("строка 4: пустые «КодВ1С» и «Артикул»",)


def test_distr_reads_optional_columns(tmp_path: Path) -> None:
    rows: list[Sequence[object]] = [
        [*DISTR_HEADER, "Код в 1С", "ЦеноваяГруппа"],
        [*distr_row(), "ЕК000020771", "Инструмент"],
        [*distr_row({"Артикул": "TTH50"}), None, None],
    ]
    loaded = distr.read_distr(write_xlsx(tmp_path / "distr.xlsx", rows))
    assert loaded.items == (
        replace(DISTR_ITEM, code_1c="ЕК000020771", price_group="Инструмент"),
        replace(DISTR_ITEM, article="TTH50"),
    )

def test_price_groups(tmp_path: Path) -> None:
    rows: list[Sequence[object]] = [
        ["Ценовая группа"], ["Расходка"], ["Грузики  CLIPPER"], [None], ["Расходка"], ["РУБ"],
    ]
    loaded = price_groups.read_price_groups(write_xlsx(tmp_path / "groups.xlsx", rows))
    assert loaded.items == ("РУБ", "Расходка", "Грузики CLIPPER")
    assert loaded.problems == ()
