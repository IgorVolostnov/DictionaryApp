from __future__ import annotations

import string
import unicodedata

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st

from app.domain.errors import InvalidAliasKeyError
from app.domain.normalize import (
    LOOKALIKE_LAT,
    LOOKALIKE_RUS,
    LOOKUP_FOLDS,
    REMOVED_CHARS,
    TRANSLIT_LAT,
    TRANSLIT_RUS,
    UNMAPPED,
    VBA_UPPER,
    ensure_storable_key,
    lookup_keys,
    lost_chars,
    normalize_key,
    to_upper,
    vba_transform,
)
from tests.golden_vba import EXPECTED_FILE, GOLDEN_INPUTS, read_expected

# Пары выведены вручную из кода VBA. Эталон Excel ниже проверяет больший набор.
CASES = [
    ("R-10", "R10"),
    ("Р-10", "P10"),  # кириллическая Р → латинская P, а не R
    ("Пластыри", "PLACTYPI"),
    ("Подъём", "POD''JOM"),
    ("Объём", "OB''JOM"),
    ("Нн", "HN"),  # Н заменяется двойником, строчная н транслитерируется
    ("Тт", "TT"),
    ("Щётка", "SCHJOTKA"),
    ("Ключ 17 мм", "KLYUCH17MM"),
    ("Хомут (CA102150)", "XOMYTCA102150"),
    ('Шланг 1/2"', "SHLANG12"),
    ("Съёмник", "C''JOMNIK"),
    ("Ель", "EL'"),
    ("Цепь", "TSEP'"),
    ("Эхо", "EXO"),
    ("Йогурт", "JOGYPT"),
    ("Ёлка", "JOLKA"),
    ("14174.R Переходник", "14174RPEPEXODNIK"),
    ("CB.006.", "CB006"),
    ("8-09614A (1683) SEAL", "809614A1683SEAL"),
    ("593 1851", "5931851"),
    ("№5 #12", "№5#12"),
    ("", ""),
    (REMOVED_CHARS, ""),
]


@pytest.mark.parametrize(("raw", "expected"), CASES)
def test_vba_transform(raw: str, expected: str) -> None:
    assert vba_transform(raw) == expected


def test_matches_excel() -> None:
    if not EXPECTED_FILE.exists():
        pytest.fail(
            "Нет эталона Excel: выполните «uv run python -m tests.golden_vba», "
            "запустите макрос ЭталонНормализации и положите vba_expected.txt в tests/unit/golden/"
        )
    pairs = read_expected()
    assert {src for src, _ in pairs} == set(GOLDEN_INPUTS), "эталон устарел: пересоздайте его"
    mismatches = [(src, exp, vba_transform(src)) for src, exp in pairs if vba_transform(src) != exp]
    assert not mismatches


def test_tables_use_correct_alphabets() -> None:
    assert len(LOOKALIKE_RUS) == len(LOOKALIKE_LAT) == 19
    assert all(unicodedata.name(ch).startswith("CYRILLIC") for ch in LOOKALIKE_RUS)
    assert LOOKALIKE_LAT.isascii()
    assert len(TRANSLIT_RUS) == len(TRANSLIT_LAT) == 33
    assert all(unicodedata.name(ch).startswith("CYRILLIC") for ch in TRANSLIT_RUS)
    assert all(lat.isascii() for lat in TRANSLIT_LAT)
    assert len(REMOVED_CHARS) == 20
    assert REMOVED_CHARS.isascii()


def test_vba_keeps_invisible_but_key_does_not() -> None:
    assert vba_transform("R-10\u00a0") == "R10\u00a0"
    assert normalize_key("R-10\u00a0") == "R10"


@pytest.mark.parametrize(
    "raw", ["R\t10", "R\u200b10", "R\r\n10", "R\u00ad10", "\ufeffR10", "R\u202f10"]
)
def test_key_strips_invisible(raw: str) -> None:
    assert normalize_key(raw) == "R10"


def test_apostrophes_make_transform_non_idempotent() -> None:
    key = vba_transform("Подъём")
    assert vba_transform(key) == "PODJOM" != key


def test_upper_follows_windows_cp1251() -> None:
    assert to_upper("straße") == "STRA?E"
    assert to_upper("😀") == "??"
    assert to_upper("іabc№") == "ІABC№"


def test_vba_upper_table_from_russian_windows() -> None:
    cp1251 = bytes(range(256)).decode("cp1251", errors="ignore")
    missing = [f"U+{ord(ch):04X}" for ch in cp1251 if ch != UNMAPPED and ch not in VBA_UPPER]
    assert not missing, "таблица снята не в русской Windows (cp1251)"
    assert all(VBA_UPPER[ch] == ch.upper() for ch in string.ascii_letters)


@pytest.mark.parametrize("raw", ["", "—", "()", "ъ"])
def test_keys_without_letters_rejected(raw: str) -> None:
    with pytest.raises(InvalidAliasKeyError, match="букв"):
        ensure_storable_key(normalize_key(raw))


def test_one_char_key_rejected() -> None:
    with pytest.raises(InvalidAliasKeyError, match="короткий"):
        ensure_storable_key("R")


def test_valid_key_returned() -> None:
    assert ensure_storable_key("R10") == "R10"


_RU = TRANSLIT_RUS + TRANSLIT_RUS.upper()
texts = st.text(
    alphabet=_RU + string.ascii_letters + string.digits + string.punctuation + " №«»—–\u00a0\t",
    max_size=60,
)


@given(texts)
def test_key_has_no_russian_letters_signs_or_spaces(s: str) -> None:
    key = normalize_key(s)
    assert not set(key) & set(_RU)
    # Апостроф остаётся только от ъ/ь: Translit выполняется после УдалениеЗнаков.
    assert not set(key) & (set(REMOVED_CHARS) - {"'"})
    assert "'" not in key or any(ch in "ъьЪЬ" for ch in s)
    assert not any(ch.isspace() for ch in key)
    assert key == key.upper()


@given(texts)
def test_key_without_apostrophes_is_stable(s: str) -> None:
    key = normalize_key(s)
    assume("'" not in key)
    assert normalize_key(key) == key


@pytest.mark.parametrize(
    ("raw", "keys"),
    [
        ("Ключ 10×13", ("KLYUCH10?13", "KLYUCH10X13")),
        ("Шланг 1/2’", ("SHLANG12’", "SHLANG12")),
        ("Труба ½", ("TPYBA?", "TPYBA12", "TRUBA12")),
        ("«Втулка» — 5", ("«BTYLKA»—5", "BTYLKA5", "VTULKA5")),
        ("Würth", ("WURTH",)),
        # Ключи старого формата из словаря Access (товары 2004501, 2005401, 2005601).
        ("головка в сборе", ("GOLOBKABCBOPE", "GOLOVKAVSBORE")),
        ("Пружина поз. 111", ("PPYZHINAPOZ111", "PRUZHINAPOZ111")),
        ("Соединительный", ("COEDINITEL'NYJ", "SOEDINITEL'NYJ")),
    ],
)
def test_lookup_keys(raw: str, keys: tuple[str, ...]) -> None:
    assert lookup_keys(raw) == keys


def test_cyrillic_kha_matches_latin_x() -> None:
    assert lookup_keys("Ключ 10х13")[0] == lookup_keys("Ключ 10x13")[0] == "KLYUCH10X13"


def test_folds_are_single_chars_to_ascii() -> None:
    assert all(len(src) == 1 and dst.isascii() for src, dst in LOOKUP_FOLDS.items())


def test_lost_chars() -> None:
    assert lost_chars("Ключ 10×13 ×½ 😀 ?") == "×½😀"
    assert lost_chars("Würth Ø6,3 «»") == ""


@given(texts)
def test_first_lookup_key_is_stored_key(s: str) -> None:
    keys = lookup_keys(s)
    assert keys[0] == normalize_key(s)
    assert len(set(keys)) == len(keys) <= 3
    if not set(s) & (LOOKUP_FOLDS.keys() | set(LOOKALIKE_RUS)):
        assert keys == (normalize_key(s),)


def test_degree_sign_kept_in_stored_key() -> None:
    # Совместимость с VBA: сохраняемый ключ не меняется.
    assert normalize_key("TR-570C-27°") == "TR570C27°"


def test_degree_sign_folded_in_lookup_keys() -> None:
    keys = lookup_keys("TR-570C-27°")
    assert keys[0] == "TR570C27°"
    assert normalize_key("TR-570C-27") in keys


def test_degree_fold_keeps_angles_apart() -> None:
    assert not set(lookup_keys("TR-570C-27°")) & set(lookup_keys("TR-570C-90°"))


def test_multiplication_sign_matches_latin_x() -> None:
    assert normalize_key("230×120") == "230?120"
    assert normalize_key("230x120") in lookup_keys("230×120")
