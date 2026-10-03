"""Эталон нормализации, рассчитанный самим Excel.

1. uv run python -m tests.golden_vba   → tests/unit/golden/vba_inputs.txt
2. В Excel макрос «ЭталонНормализации» → vba_expected.txt
3. vba_expected.txt положить в tests/unit/golden/ и закоммитить.

Строки передаются кодами UTF-16, поэтому кодировка Windows ничего не искажает.
"""

from __future__ import annotations

import string
from pathlib import Path
from typing import Final

GOLDEN_DIR: Final = Path(__file__).parent / "unit" / "golden"
INPUTS_FILE: Final = GOLDEN_DIR / "vba_inputs.txt"
EXPECTED_FILE: Final = GOLDEN_DIR / "vba_expected.txt"

_RU: Final = "абвгдеёжзийклмнопрстуфхцчшщъыьэюя"

GOLDEN_INPUTS: Final[tuple[str, ...]] = (
    "", "R-10", "Р-10", "P10", "Пластыри", "Подъём", "Объём", "Нн", "Тт", "Щётка",
    "Ключ 17 мм", "Хомут (CA102150)", 'Шланг 1/2"', "Съёмник", "Ель", "Цепь", "Эхо",
    "Йогурт", "Ёлка", "14174.R Переходник", "CB.006.", "8-09614A (1683) SEAL", "593 1851",
    "POD''JOM", " ,.-_+*\\/[]{}';:=\"()", "№5 #12 a&b 50% «»—–",
    "straße", "ﬁ", "Ø 6,3 × 2² ½ µ° ±", "Würth Müller é ç", "• ™ € … ’ “” „ ‰",
    "іїєґІЇЄҐ", "и\u0306", "R-10\u00a0", "R\t10", "R\u200b10", "😀",
    _RU, _RU.upper(), string.ascii_letters, string.digits, string.punctuation,
    *_RU, *_RU.upper(),
)  # fmt: skip


def to_hex(s: str) -> str:
    data = s.encode("utf-16-le", "surrogatepass")
    units = (int.from_bytes(data[i : i + 2], "little") for i in range(0, len(data), 2))
    return " ".join(f"{u:04X}" for u in units)


def from_hex(h: str) -> str:
    data = b"".join(int(u, 16).to_bytes(2, "little") for u in h.split())
    return data.decode("utf-16-le", "surrogatepass")


def read_expected() -> list[tuple[str, str]]:
    pairs = []
    for line in EXPECTED_FILE.read_text(encoding="ascii").splitlines():
        if line:
            source, _, result = line.partition("\t")
            pairs.append((from_hex(source), from_hex(result)))
    return pairs


def write_inputs() -> None:
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    # VBA Line Input понимает только CRLF.
    with INPUTS_FILE.open("w", encoding="ascii", newline="\r\n") as f:
        for s in GOLDEN_INPUTS:
            f.write(to_hex(s) + "\n")


if __name__ == "__main__":
    write_inputs()
