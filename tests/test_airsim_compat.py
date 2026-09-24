import builtins
import json
import ssl
from types import SimpleNamespace

import pytest

from scripts import airsim_compat
from scripts.airsim_compat import AirSimLink
from scripts.semantic_geometry import SemanticObjectTracker
from scripts.semantic_perception import write_semantic_objects


def test_resolve_rpc_vendor_falls_back_to_parent_tools(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    vendor = tmp_path / ".tools" / "airsim_rpc"
    vendor.mkdir(parents=True)
    monkeypatch.setattr(airsim_compat, "REPO_ROOT", repo)
    assert airsim_compat.resolve_rpc_vendor(str(repo / "missing")) == vendor


def test_import_restores_ssl_context_when_client_import_fails(
    tmp_path, monkeypatch
):
    original_context = ssl.create_default_context
    original_import = builtins.__import__

    def rejecting_import(name, *args, **kwargs):
        if name == "airsim":
            raise RuntimeError("synthetic import failure")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", rejecting_import)
    with pytest.raises(RuntimeError, match="synthetic import failure"):
        airsim_compat.import_airsim(str(tmp_path))
    assert ssl.create_default_context is original_context


class FakeClient:
    def __init__(self, budget, payload="images"):
        # ``budget`` is shared across every client the factory hands out, so
        # "fail the next two calls" survives a reconnect -- which is the whole
        # point: reconnecting must be able to fix the stream.
        self.budget = budget
        self.payload = payload
        self.closed = False

    def confirmConnection(self):
        return True

    def simGetCameraInfo(self, camera, vehicle_name=""):
        return SimpleNamespace(fov=91.5)

    def simGetImages(self, requests, vehicle_name=""):
        if self.budget["remaining"] > 0:
            self.budget["remaining"] -= 1
            raise MemoryError("msgpack buffer exhausted")
        return self.payload

    def close(self):
        self.closed = True


def build(failures, **kwargs):
    """Return (link, created_clients); the first ``failures`` grabs fail."""
    created = []
    budget = {"remaining": failures}

    def factory():
        client = FakeClient(budget, **kwargs)
        created.append(client)
        return client

    link = AirSimLink(SimpleNamespace(MultirotorClient=factory), "CameraDepth")
    return link, created


def test_grab_returns_without_reconnecting_when_it_succeeds():
    link, created = build(failures=0)
    assert link.grab([]) == "images"
    assert len(created) == 1
    assert link.reconnects == 0


def test_grab_rebuilds_the_session_after_a_lost_response():
    """Each attempt gets a brand new client, so the bad buffer is discarded."""
    link, created = build(failures=2)
    assert link.grab([], attempts=3) == "images"
    assert len(created) == 3
    assert link.reconnects == 2
    # The abandoned sessions must be closed, not just dropped.
    assert created[0].closed is True
    assert created[1].closed is True
    assert created[2].closed is False


def test_grab_raises_once_the_attempts_are_exhausted():
    link, created = build(failures=99)
    with pytest.raises(MemoryError):
        link.grab([], attempts=3)
    assert len(created) == 3
    assert link.reconnects == 2


def test_camera_fov_comes_from_the_current_session():
    link, _ = build(failures=0)
    assert link.camera_fov() == pytest.approx(91.5)


def test_release_tolerates_a_client_without_close():
    link, _ = build(failures=0)
    link.client = SimpleNamespace()
    link.release()
    assert link.client is None


def test_checkpoint_writes_the_objects_a_crash_would_otherwise_lose(tmp_path):
    tracker = SemanticObjectTracker()
    tracker.update([SimpleNamespace(
        label="tree", confidence=0.8, world_ned=(1.0, 2.0, -3.0))], 0.0)

    write_semantic_objects(tmp_path, tracker)

    payload = json.loads(
        (tmp_path / "semantic_objects.json").read_text(encoding="utf-8"))
    assert payload["coordinate_frame"] == "px4_local_ned"
    assert [item["label"] for item in payload["objects"]] == ["tree"]
    assert payload["objects"][0]["position_ned"] == [1.0, 2.0, -3.0]
    # The temp file must not survive the atomic replace.
    assert not (tmp_path / "semantic_objects.json.tmp").exists()


def test_checkpoint_overwrites_so_a_rewrite_is_a_snapshot_not_a_log(tmp_path):
    tracker = SemanticObjectTracker()
    write_semantic_objects(tmp_path, tracker)
    first = (tmp_path / "semantic_objects.json").read_text(encoding="utf-8")

    tracker.update([SimpleNamespace(
        label="fence", confidence=0.5, world_ned=(4.0, 5.0, -1.0))], 1.0)
    write_semantic_objects(tmp_path, tracker)
    second = (tmp_path / "semantic_objects.json").read_text(encoding="utf-8")

    assert first != second
    payload = json.loads(second)
    assert [item["label"] for item in payload["objects"]] == ["fence"]
