from pathlib import Path

from arctx.web import assets


def _static_dir(path: Path) -> Path:
    path.mkdir()
    (path / "index.html").write_text("<!doctype html>", encoding="utf-8")
    return path


def test_override_has_highest_priority(tmp_path, monkeypatch):
    override = _static_dir(tmp_path / "override")
    repo_dist = _static_dir(tmp_path / "repo-dist")
    packaged = _static_dir(tmp_path / "packaged")
    monkeypatch.setenv("ARCTX_WEB_STATIC", str(override))
    monkeypatch.setattr(assets, "_repo_web_dist", lambda: repo_dist)
    monkeypatch.setattr(assets, "PACKAGED_STATIC", packaged)

    assert assets.find_static_dir() == override


def test_source_checkout_prefers_fresh_dist(tmp_path, monkeypatch):
    repo_dist = _static_dir(tmp_path / "repo-dist")
    packaged = _static_dir(tmp_path / "packaged")
    monkeypatch.delenv("ARCTX_WEB_STATIC", raising=False)
    monkeypatch.setattr(assets, "_repo_web_dist", lambda: repo_dist)
    monkeypatch.setattr(assets, "PACKAGED_STATIC", packaged)

    assert assets.find_static_dir() == repo_dist


def test_installed_package_falls_back_to_packaged_static(tmp_path, monkeypatch):
    packaged = _static_dir(tmp_path / "packaged")
    monkeypatch.delenv("ARCTX_WEB_STATIC", raising=False)
    monkeypatch.setattr(assets, "_repo_web_dist", lambda: None)
    monkeypatch.setattr(assets, "PACKAGED_STATIC", packaged)

    assert assets.find_static_dir() == packaged
