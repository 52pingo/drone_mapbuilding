"""Tests for scripts/uav_semantic_schema.py."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import uav_semantic_schema as schema  # noqa: E402


# ---------------------------------------------------------------------------
# CLASSES / CLASS_TO_ID integrity
# ---------------------------------------------------------------------------

def test_classes_is_nonempty_list_of_str():
    assert isinstance(schema.CLASSES, list)
    assert schema.CLASSES
    assert all(isinstance(name, str) for name in schema.CLASSES)


def test_classes_have_no_empty_names():
    for name in schema.CLASSES:
        assert name.strip(), f"empty class name in CLASSES: {name!r}"


def test_classes_are_unique():
    assert len(schema.CLASSES) == len(set(schema.CLASSES)), "duplicate class names"


def test_class_to_id_is_bijective_with_classes():
    assert set(schema.CLASS_TO_ID.keys()) == set(schema.CLASSES)
    assert len(schema.CLASS_TO_ID) == len(schema.CLASSES)


def test_class_ids_are_contiguous_from_zero():
    ids = sorted(schema.CLASS_TO_ID.values())
    assert ids == list(range(len(schema.CLASSES)))


def test_class_to_id_values_unique():
    values = list(schema.CLASS_TO_ID.values())
    assert len(values) == len(set(values)), "duplicate ids in CLASS_TO_ID"


def test_class_to_id_matches_index():
    for index, name in enumerate(schema.CLASSES):
        assert schema.CLASS_TO_ID[name] == index


# ---------------------------------------------------------------------------
# Out-of-range / unknown id handling
# ---------------------------------------------------------------------------

def test_unknown_name_lookup_returns_none():
    assert schema.CLASS_TO_ID.get("definitely_not_a_class") is None


def test_unknown_name_lookup_raises_keyerror():
    with pytest.raises(KeyError):
        schema.CLASS_TO_ID["definitely_not_a_class"]


def test_out_of_range_positive_id_raises_indexerror():
    with pytest.raises(IndexError):
        schema.CLASSES[len(schema.CLASSES)]


def test_out_of_range_negative_id_wraps():
    # Python list semantics: -1 is the last element.
    assert schema.CLASSES[-1] == schema.CLASSES[len(schema.CLASSES) - 1]


def test_id_to_name_roundtrip_for_all_ids():
    id_to_name = {v: k for k, v in schema.CLASS_TO_ID.items()}
    for name, cid in schema.CLASS_TO_ID.items():
        assert id_to_name[cid] == name


# ---------------------------------------------------------------------------
# Source-dataset mapping integrity
# ---------------------------------------------------------------------------

def test_road20_names_length_matches_mapping():
    assert len(schema.ROAD20_NAMES) == len(schema.ROAD20_TO_TARGET)


def test_visdrone_names_length_matches_mapping():
    assert len(schema.VISDRONE_NAMES) == len(schema.VISDRONE_TO_TARGET)


def test_road20_mapping_keys_are_contiguous():
    assert sorted(schema.ROAD20_TO_TARGET.keys()) == list(range(len(schema.ROAD20_NAMES)))


def test_visdrone_mapping_keys_are_contiguous():
    assert sorted(schema.VISDRONE_TO_TARGET.keys()) == list(range(len(schema.VISDRONE_NAMES)))


def test_road20_targets_are_valid_class_ids():
    valid = set(schema.CLASS_TO_ID.values())
    for src, dst in schema.ROAD20_TO_TARGET.items():
        assert dst in valid, f"ROAD20 id {src} maps to unknown target id {dst}"


def test_visdrone_targets_are_valid_class_ids():
    valid = set(schema.CLASS_TO_ID.values())
    for src, dst in schema.VISDRONE_TO_TARGET.items():
        assert dst in valid, f"VisDrone id {src} maps to unknown target id {dst}"


# ---------------------------------------------------------------------------
# Serialization / deserialization roundtrip
# ---------------------------------------------------------------------------

def _serialize() -> str:
    payload = {
        "classes": list(schema.CLASSES),
        "class_to_id": dict(schema.CLASS_TO_ID),
        "road20_names": list(schema.ROAD20_NAMES),
        "road20_to_target": {str(k): v for k, v in schema.ROAD20_TO_TARGET.items()},
        "visdrone_names": list(schema.VISDRONE_NAMES),
        "visdrone_to_target": {str(k): v for k, v in schema.VISDRONE_TO_TARGET.items()},
    }
    return json.dumps(payload, sort_keys=True)


def test_json_roundtrip_preserves_classes():
    restored = json.loads(_serialize())
    assert restored["classes"] == list(schema.CLASSES)


def test_json_roundtrip_preserves_class_to_id():
    restored = json.loads(_serialize())
    assert restored["class_to_id"] == dict(schema.CLASS_TO_ID)


def test_json_roundtrip_preserves_road20_mapping():
    restored = json.loads(_serialize())
    restored_map = {int(k): v for k, v in restored["road20_to_target"].items()}
    assert restored_map == dict(schema.ROAD20_TO_TARGET)
    assert restored["road20_names"] == list(schema.ROAD20_NAMES)


def test_json_roundtrip_preserves_visdrone_mapping():
    restored = json.loads(_serialize())
    restored_map = {int(k): v for k, v in restored["visdrone_to_target"].items()}
    assert restored_map == dict(schema.VISDRONE_TO_TARGET)
    assert restored["visdrone_names"] == list(schema.VISDRONE_NAMES)


def test_serialize_is_deterministic():
    assert _serialize() == _serialize()


def test_roundtrip_rebuilds_equivalent_class_to_id():
    restored = json.loads(_serialize())
    rebuilt = {name: idx for idx, name in enumerate(restored["classes"])}
    assert rebuilt == restored["class_to_id"]
    assert rebuilt == schema.CLASS_TO_ID
