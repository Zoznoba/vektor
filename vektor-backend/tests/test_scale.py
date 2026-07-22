import pytest

from vektor.shared.scale import convert_scale_1_3_to_1_5


@pytest.mark.parametrize(("old_score", "expected"), [(1, 1.0), (2, 3.0), (3, 5.0), (2.5, 4.0)])
def test_right_convertion(old_score, expected) -> None:
    assert convert_scale_1_3_to_1_5(old_score) == expected
