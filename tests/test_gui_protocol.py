from drone_gui.protocol import (
    GUI_PROBE_PREFIX, GUI_SETUP_PREFIX, GUI_STATUS_PREFIX, GUI_UE4_PREFIX,
    parse_prefixed_json,
)


def test_prefixed_json_ignores_normal_logs_and_uses_last_payload():
    text = "\n".join([
        "starting backend",
        'GUI_STATUS {"state":"NAVIGATE","armed":true}',
        'GUI_STATUS {"state":"HOLD","armed":true}',
    ])
    assert parse_prefixed_json(text, GUI_STATUS_PREFIX) == {
        "state": "HOLD", "armed": True
    }


def test_prefixed_json_rejects_malformed_or_non_object_payloads():
    text = "GUI_PROBE nope\nGUI_PROBE [true]"
    assert parse_prefixed_json(text, GUI_PROBE_PREFIX) is None


def test_setup_and_ue4_status_payloads_are_supported():
    assert parse_prefixed_json(
        'GUI_UE4 {"window_ready":true,"airsim_ready":false}', GUI_UE4_PREFIX
    )["window_ready"] is True
    assert parse_prefixed_json(
        'GUI_SETUP {"component":"px4","status":"pass"}', GUI_SETUP_PREFIX
    )["component"] == "px4"
