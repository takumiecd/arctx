"""CLI integration tests for assets (now a core payload, always available)."""

from __future__ import annotations

import json

from arctx_cli.commands.init import run_init_command
from arctx_cli.context import resolve_store
from arctx_cli.main import main


def test_asset_cli_available_without_enabling(tmp_path, capsys):
    # asset is a core command now; it is registered for every run and fails
    # gracefully (exit 1) on an unknown target rather than being absent.
    store_dir = str(tmp_path / "runs")
    run_init_command(
        requirement_id="req",
        target_type="task",
        target_id="target",
        run_id="run_plain",
        store_dir=store_dir,
    )

    dummy_file = tmp_path / "dummy.txt"
    dummy_file.write_text("hello")

    rc = main(
        [
            "asset", "attach", str(dummy_file),
            "--target", "n_0000",
            "--run", "run_plain",
            "--store-dir", store_dir,
        ]
    )
    assert rc == 1
    assert "target_id not found" in capsys.readouterr().err


def test_asset_cli_attach_and_list(tmp_path, capsys):
    store_dir = str(tmp_path / "runs")
    run_init_command(
        requirement_id="req",
        target_type="task",
        target_id="target",
        run_id="run_asset_cli",
        store_dir=store_dir,
    )

    store = resolve_store(store_dir)
    handle = store.load_run("run_asset_cli")
    root_node_id = handle.root_node_id

    dummy_file = tmp_path / "my_doc.pdf"
    dummy_file.write_text("dummy pdf contents")

    # 1. Attach via CLI
    rc = main(
        [
            "asset", "attach", str(dummy_file),
            "--target", root_node_id,
            "--run", "run_asset_cli",
            "--store-dir", store_dir,
        ]
    )

    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data["payload_type"] == "asset"
    assert data["filename"] == "my_doc.pdf"
    assert data["mime_type"] == "application/pdf"
    assert data["size_bytes"] == len("dummy pdf contents")

    # 2. List via CLI
    rc = main(
        [
            "asset", "list",
            "--target", root_node_id,
            "--run", "run_asset_cli",
            "--store-dir", store_dir,
        ]
    )
    assert rc == 0
    list_data = json.loads(capsys.readouterr().out)
    assert len(list_data) == 1
    assert list_data[0]["payload_id"] == data["payload_id"]

    # 3. Show details via CLI
    rc = main(
        [
            "asset", "show", data["payload_id"],
            "--run", "run_asset_cli",
            "--store-dir", store_dir,
        ]
    )
    assert rc == 0
    show_data = json.loads(capsys.readouterr().out)
    assert show_data["payload_id"] == data["payload_id"]
    assert show_data["filename"] == "my_doc.pdf"
