from drone_gui.config_store import find_config, portable_config_path, save_config
from drone_gui.models import RuntimeConfig


def test_portable_config_round_trip(tmp_path):
    config = RuntimeConfig.defaults(tmp_path)
    config.environment_name = "Park"
    target = portable_config_path(tmp_path)
    assert save_config(config, target) == target
    assert find_config(tmp_path) == target
    restored = RuntimeConfig.load(target, tmp_path)
    assert restored.environment_name == "Park"
