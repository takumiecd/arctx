"""Tests for the asset extension payloads and verbs."""

from __future__ import annotations

from pathlib import Path
from arctx.core.run import init as run_init
from arctx.core.schema.payloads import payload_from_dict
from arctx.ext import attach_extensions
from arctx.ext.asset import AssetExtension
from arctx.ext.asset.payloads import AssetPayload


def test_asset_payload_deserialization():
    AssetExtension().register_schema()
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


def test_asset_extension_attach(tmp_path, monkeypatch):
    # Mock runs_dir so it uses tmp_path
    monkeypatch.setattr("arctx.ext.asset.runs_dir", lambda: tmp_path)

    # 1. Create a dummy file to attach
    dummy_file = tmp_path / "my_photo.jpg"
    dummy_file.write_text("dummy binary data")

    # 2. Init run and attach extension
    from arctx.core.schema.requirements import Requirement
    req = Requirement(requirement_id="req_test", target_type="task", target_id="target")
    handle = run_init(req, run_id="run_test")
    attach_extensions(handle, ["asset"])

    # 3. Attach file to root node
    node_id = handle.root_node_id
    payload = handle.asset.attach(node_id, dummy_file)

    # 4. Assert payload properties
    assert isinstance(payload, AssetPayload)
    assert payload.target_id == node_id
    assert payload.filename == "my_photo.jpg"
    assert payload.mime_type == "image/jpeg"
    assert payload.size_bytes == len("dummy binary data")
    assert payload.path.startswith("artifacts/")

    # 5. Assert file is copied inside run directory
    copied_file = tmp_path / "run_test" / payload.path
    assert copied_file.exists()
    assert copied_file.read_text() == "dummy binary data"
