"""Tests for the core AssetPayload and handle.attach_asset verb."""

from __future__ import annotations

from arctx.core.run import init as run_init
from arctx.core.schema.payloads import AssetPayload, payload_from_dict
from arctx.core.schema.requirements import Requirement


def test_asset_payload_deserialization():
    data = {
        "payload_type": "asset",
        "payload_id": "pl_asset",
        "target_id": "n_1",
        "target_kind": "node",
        "asset_id": "ast_123",
        "filename": "test_image.png",
        "mime_type": "image/png",
        "size_bytes": 1024,
        "path": "artifacts/ast_123_test_image.png",
        "metadata": {"caption": "Test Image"},
    }

    payload = payload_from_dict(data)

    assert isinstance(payload, AssetPayload)
    assert payload.target_kind == "node"
    assert payload.filename == "test_image.png"
    assert payload.size_bytes == 1024
    assert payload.metadata == {"caption": "Test Image"}


def test_attach_asset(tmp_path, monkeypatch):
    # Mock runs_dir so the copy lands under tmp_path.
    monkeypatch.setattr("arctx.core.run.asset.runs_dir", lambda: tmp_path)

    dummy_file = tmp_path / "my_photo.jpg"
    dummy_file.write_text("dummy binary data")

    req = Requirement(requirement_id="req_test", target_type="task", target_id="target")
    handle = run_init(req, run_id="run_test")

    node_id = handle.root_node_id
    payload = handle.attach_asset(node_id, dummy_file)

    assert isinstance(payload, AssetPayload)
    assert payload.target_id == node_id
    assert payload.filename == "my_photo.jpg"
    assert payload.mime_type == "image/jpeg"
    assert payload.size_bytes == len("dummy binary data")
    assert payload.path.startswith("artifacts/")

    copied_file = tmp_path / "run_test" / payload.path
    assert copied_file.exists()
    assert copied_file.read_text() == "dummy binary data"


def test_attach_asset_unknown_target(tmp_path, monkeypatch):
    monkeypatch.setattr("arctx.core.run.asset.runs_dir", lambda: tmp_path)
    dummy_file = tmp_path / "f.txt"
    dummy_file.write_text("x")
    req = Requirement(requirement_id="r", target_type="task", target_id="t")
    handle = run_init(req, run_id="run_x")
    try:
        handle.attach_asset("n_bogus", dummy_file)
    except KeyError:
        pass
    else:  # pragma: no cover
        raise AssertionError("expected KeyError for unknown target")
