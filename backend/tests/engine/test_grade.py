# backend/tests/engine/test_grade.py
import pytest

from app.engine.grade import grade_of


@pytest.mark.parametrize(
    "core, expected",
    [
        (1.122, "S"),
        (0.80, "S"),
        (0.79, "A"),
        (0.60, "A"),
        (0.59, "B"),
        (0.40, "B"),
        (0.39, "C"),
        (0.0001, "C"),
        (0.0, None),
        (-1.0, None),
    ],
)
def test_grade_cutoffs_on_core(core, expected):
    assert grade_of(core) == expected
