from datetime import date

import pytest

from vektor.shared.academic_year import academic_year_label


@pytest.mark.parametrize(
    ("today", "expected"),
    [
        (date(2026, 8, 18), "2025/2026 учебный год"),
        (date(2026, 1, 1), "2025/2026 учебный год"),
        (date(2026, 9, 1), "2026/2027 учебный год"),
        (date(2026, 12, 31), "2026/2027 учебный год"),
    ],
)
def test_academic_year_label(today: date, expected: str) -> None:
    assert academic_year_label(today) == expected
