"""Нормализация наименований: точная копия VBA-функции «Преобразование».

    Преобразование(s) = Регистр(Translit(ЗаменаРуссвихБукв(УдалениеЗнаков(s))))

Таблицы перенесены из VBA посимвольно. НЕ МЕНЯЙТЕ ИХ: один изменённый символ
тихо ломает совместимость со словарём из Access. Совпадение с Excel проверяет
tests/unit/test_normalize.py по эталону, рассчитанному самим Excel.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Mapping
from pathlib import Path
from typing import Final

from app.domain.errors import InvalidAliasKeyError

# УдалениеЗнаков: 20 символов, порядок как в VBA.
REMOVED_CHARS: Final = " ,.-_+*\\/[]{}';:=\"()"

# ЗаменаРуссвихБукв: 19 кириллических букв → латинские двойники.
LOOKALIKE_RUS: Final = "авекорсухАВЕКНОРСТХ"
LOOKALIKE_LAT: Final = "abekopcyxABEKHOPCTX"

# Translit: 33 строчные буквы. Заглавные в VBA дают те же значения в верхнем регистре.
TRANSLIT_RUS: Final = "абвгдеёжзийклмнопрстуфхцчшщъыьэюя"
TRANSLIT_LAT: Final = (
    "a", "b", "v", "g", "d", "e", "jo", "zh", "z", "i", "j", "k", "l", "m", "n", "o",
    "p", "r", "s", "t", "u", "f", "kh", "ts", "ch", "sh", "sch", "''", "y", "'", "e",
    "yu", "ya",
)  # fmt: skip

MIN_KEY_LENGTH: Final = 2

# Регистр = StrConv(s, vbUpperCase). VBA переводит строку в кодировку Windows (cp1251),
# меняет регистр и переводит обратно: символы вне cp1251 становятся «?».
# Таблицу для всех 65 536 кодов снял сам Excel (макрос ТаблицаРегистра).
# В файле только символы, которые НЕ превращаются в «?».
VBA_UPPER_FILE: Final = Path(__file__).with_name("vba_strconv.txt")
UNMAPPED: Final = "?"
BMP_MAX: Final = 0xFFFF

_REMOVE_TABLE: Final = str.maketrans("", "", REMOVED_CHARS)
_LOOKALIKE_TABLE: Final = str.maketrans(LOOKALIKE_RUS, LOOKALIKE_LAT)
_TRANSLIT_TABLE: Final = str.maketrans(
    dict(zip(TRANSLIT_RUS, TRANSLIT_LAT, strict=True))
    | {rus.upper(): lat.upper() for rus, lat in zip(TRANSLIT_RUS, TRANSLIT_LAT, strict=True)}
)
# Третий ключ: старые ключи словаря сделаны транслитом без ЗаменаРуссвихБукв
# («головка в сборе» → GOLOVKAVSBORE, а Преобразование даёт GOLOBKABCBOPE).
# Буквы-двойники заранее заменяются по таблице транслита, остальное делает vba_transform.
_PLAIN_TABLE: Final[dict[int, str]] = {
    ord(ch): _TRANSLIT_TABLE[ord(ch)] for ch in LOOKALIKE_RUS if ord(ch) in _TRANSLIT_TABLE
}
# Невидимые символы, которые VBA не удалял: неразрывный пробел, табуляция,
# переводы строк, символы нулевой ширины, мягкий перенос, BOM.
_INVISIBLE: Final = frozenset({"Cc", "Cf", "Zs", "Zl", "Zp"})
# Второй ключ — только для поиска, в базу не сохраняется. Типографские знаки,
# которые VBA теряет («×», «½» → «?») или оставляет («’», «"», «—»), заменяются
# обычными. Дальше работает тот же vba_transform, поэтому «'», «"», «-», «/», «.»
# всё равно удалятся. Коды вместо символов: «–» и «—» на глаз не различить.
LOOKUP_FOLDS: Final[dict[str, str]] = {
    "\u00d7": "x",  # знак умножения
    "\u00b2": "2",  # верхний индекс 2
    "\u00b3": "3",  # верхний индекс 3
    "\u00bc": "1/4",
    "\u00bd": "1/2",
    "\u00be": "3/4",
    "\u2018": "'",  # левая одинарная кавычка
    "\u2019": "'",  # правая одинарная кавычка (типографский апостроф)
    "\u2032": "'",  # штрих (футы)
    "\u00ab": '"',  # ёлочка левая
    "\u00bb": '"',  # ёлочка правая
    "\u201c": '"',  # лапка левая
    "\u201d": '"',  # лапка правая
    "\u201e": '"',  # лапка нижняя
    "\u2033": '"',  # двойной штрих (дюймы)
    "\u2010": "-",  # дефис
    "\u2011": "-",  # неразрывный дефис
    "\u2013": "-",  # короткое тире
    "\u2014": "-",  # длинное тире
    "\u2212": "-",  # минус
    "\u2026": "...",  # многоточие
}
_FOLD_TABLE: Final = str.maketrans(LOOKUP_FOLDS)


def _from_codes(codes: str) -> str:
    return "".join(chr(int(code, 16)) for code in codes.split())


def load_vba_upper(path: Path) -> dict[str, str]:
    table: dict[str, str] = {}
    for line in path.read_text(encoding="ascii").splitlines():
        source, _, result = line.partition("\t")
        table[_from_codes(source)] = _from_codes(result)
    return table


VBA_UPPER: Final[Mapping[str, str]] = load_vba_upper(VBA_UPPER_FILE)


def remove_signs(s: str) -> str:
    """УдалениеЗнаков."""
    return s.translate(_REMOVE_TABLE)


def replace_lookalikes(s: str) -> str:
    """ЗаменаРуссвихБукв (с учётом регистра, как Option Compare Binary)."""
    return s.translate(_LOOKALIKE_TABLE)


def translit(s: str) -> str:
    """Translit."""
    return s.translate(_TRANSLIT_TABLE)


def _upper_char(ch: str) -> str:
    if ord(ch) > BMP_MAX:  # для VBA это две половинки суррогатной пары → «??»
        return UNMAPPED * 2
    return VBA_UPPER.get(ch, UNMAPPED)


def to_upper(s: str) -> str:
    """Регистр: StrConv(s, vbUpperCase) на русской Windows."""
    return "".join(_upper_char(ch) for ch in s)


def vba_transform(s: str) -> str:
    """Преобразование: бит в бит как в Excel."""
    return to_upper(translit(replace_lookalikes(remove_signs(s))))


def strip_invisible(s: str) -> str:
    return "".join(ch for ch in s if unicodedata.category(ch) not in _INVISIBLE)


def normalize_key(s: str) -> str:
    """Ключ для поиска. Старые ключи из Access проходят только strip_invisible."""
    return vba_transform(strip_invisible(s))


def lookup_keys(s: str) -> tuple[str, ...]:
    """Ключи поиска без повторов: VBA-ключ, после LOOKUP_FOLDS и старого формата.

    Сохраняемый ключ всегда первый. Если ключи найдут разные товары,
    строка помечается как неоднозначная.
    """
    clean = strip_invisible(s)
    folded = clean.translate(_FOLD_TABLE)
    plain = folded.translate(_PLAIN_TABLE)
    return tuple(dict.fromkeys(vba_transform(text) for text in (clean, folded, plain)))



def lost_chars(s: str) -> str:
    """Символы, которые Регистр() заменит на «?» (без повторов), для админки."""
    lost = (ch for ch in strip_invisible(s) if ch != UNMAPPED and ch not in VBA_UPPER)
    return "".join(dict.fromkeys(lost))


def ensure_storable_key(key: str) -> str:
    if not any(ch.isalnum() for ch in key):
        raise InvalidAliasKeyError("В строке нет букв и цифр: такой синоним сохранить нельзя.")
    if len(key) < MIN_KEY_LENGTH:
        raise InvalidAliasKeyError(
            f"Ключ «{key}» слишком короткий: он совпадёт со множеством строк."
        )
    return key
