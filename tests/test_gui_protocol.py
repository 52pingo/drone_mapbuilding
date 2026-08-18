from drone_gui.protocol import GUI_PROBE_PREFIX, GUI_STATUS_PREFIX, parse_prefixed_json


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
