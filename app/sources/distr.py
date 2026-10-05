"""distr.xlsx — ежедневная выгрузка каталога сайта: цены, остаток, данные карточки."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Final

from app.sources.cells import Loaded, Record, load, xlsx_rows

# «Код в 1С» обязателен: по нему import_distr узнаёт переименованные товары, а словарь
# из Access находит товары. Старый файл без этой колонки не загрузится.
COLUMNS: Final = (
    "Артикул",
    "Наименование",
    "ШтрихКод",
    "Количество",
    "Цена Дистрибьюторская",
    "Цена Дилерская",
    "Цена Розничная",
    "МОЦ",
    "Бренд",
    "Детальное описание",
    "Основное фото",
    "Дополнительные фото",
    "Вес (грамм)",
    "Длина (мм)",
    "Ширина (мм)",
    "Высота (мм)",
    "Объем, м3",
    "Комплектация [KOMPLEKTATSIYA]",
    "Страна производства [COUNTRY]",
    "Ссылка на сертификат [SSYLKA_NA_SERTIFIKAT]",
    "Срок действия сертификата [SROK_DEYSTVIYA_SERTIFIKATA]",
    "Код в 1С",
    "Сортировка на сайте",
    "URL страницы",
)
# Появится в выгрузке из 1С. Пока её нет: группу ставит справочник номенклатуры
# (tools/load_groups), загрузка distr её не меняет.
OPTIONAL_COLUMNS: Final = ("ЦеноваяГруппа",)


@dataclass(frozen=True, slots=True)
class DistrItem:
    article: str
    code_1c: str | None
    name: str
    barcode: str | None
    quantity: Decimal | None
    price_distr: Decimal | None
    price_dealer: Decimal | None
    price_retail: Decimal | None
    price_min_retail: Decimal | None
    brand: str | None
    description: str | None
    photo: str | None
    extra_photos: tuple[str, ...]
    weight_g: Decimal | None
    length_mm: Decimal | None
    width_mm: Decimal | None
    height_mm: Decimal | None
    volume_m3: Decimal | None
    package: str | None
    country: str | None
    certificate_url: str | None
    certificate_until: str | None
    price_group: str | None  # None — колонки нет, группа товара в базе не меняется
    sort_order: int | None = None  # «Сортировка на сайте»: порядок строк в результате подбора
    page_url: str | None = None  # карточка товара на сайте


def read_distr(path: Path) -> Loaded[DistrItem]:
    return load(xlsx_rows(path), COLUMNS, _item, OPTIONAL_COLUMNS)


def _integer(row: Record, column: str) -> int | None:
    number = row.number(column)
    if number is None:
        return None
    if number != number.to_integral_value():
        raise ValueError(f"«{column}»: {number} — нужно целое число")
    return int(number)


def _item(row: Record) -> DistrItem:
    photos = row.text("Дополнительные фото") or ""
    return DistrItem(
        article=row.required("Артикул"),
        code_1c=row.text("Код в 1С"),
        name=row.required("Наименование"),
        barcode=row.text("ШтрихКод"),
        quantity=row.number("Количество"),
        price_distr=row.number("Цена Дистрибьюторская"),
        price_dealer=row.number("Цена Дилерская"),
        price_retail=row.number("Цена Розничная"),
        price_min_retail=row.number("МОЦ"),
        brand=row.text("Бренд"),
        description=row.text("Детальное описание"),
        photo=row.text("Основное фото"),
        extra_photos=tuple(p.strip() for p in photos.split(";") if p.strip()),
        weight_g=row.number("Вес (грамм)"),
        length_mm=row.number("Длина (мм)"),
        width_mm=row.number("Ширина (мм)"),
        height_mm=row.number("Высота (мм)"),
        volume_m3=row.number("Объем, м3"),
        package=row.text("Комплектация [KOMPLEKTATSIYA]"),
        country=row.text("Страна производства [COUNTRY]"),
        certificate_url=row.text("Ссылка на сертификат [SSYLKA_NA_SERTIFIKAT]"),
        certificate_until=row.text("Срок действия сертификата [SROK_DEYSTVIYA_SERTIFIKATA]"),
        price_group=row.text("ЦеноваяГруппа"),
        sort_order=_integer(row, "Сортировка на сайте"),
        page_url=row.text("URL страницы"),
    )
