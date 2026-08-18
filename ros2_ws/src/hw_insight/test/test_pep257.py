"""Docstring check for newly maintained safety helpers."""

from ament_pep257.main import main
import pytest


@pytest.mark.linter
@pytest.mark.pep257
def test_pep257():
    """Check public safety helpers for usable API documentation."""
    rc = main(argv=['hw_insight/mission_safety.py'])
    assert rc == 0, 'Found code style errors / warnings'
