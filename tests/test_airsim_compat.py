import builtins
import ssl

import pytest

from scripts import airsim_compat


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
