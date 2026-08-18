"""Flake8 checks for the maintained autonomous mission pipeline."""

from ament_flake8.main import main_with_errors
import pytest


MAINTAINED_FILES = [
    'hw_insight/avoid_node.py',
    'hw_insight/avoid_vfh.py',
    'hw_insight/mission_safety.py',
    'hw_insight/qgc_mission_runner.py',
    'test_qgc_mission_runner.py',
    'test/test_mission_safety.py',
]


@pytest.mark.flake8
@pytest.mark.linter
def test_flake8():
    """Check files used by the autonomous mission workflow."""
    rc, errors = main_with_errors(argv=MAINTAINED_FILES)
    assert rc == 0, (
        'Found %d code style errors / warnings:\n' % len(errors)
        + '\n'.join(errors)
    )
