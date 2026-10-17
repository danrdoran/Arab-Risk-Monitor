"""Exercise the refresh job with local fixtures instead of external APIs."""

import importlib.util
import sys
from pathlib import Path


spec = importlib.util.spec_from_file_location(
    "container_entrypoint", Path(__file__).resolve().parents[1] / "docker" / "entrypoint.py",
)
entrypoint = importlib.util.module_from_spec(spec)
spec.loader.exec_module(entrypoint)


def prepare_refresh(monkeypatch, tmp_path, *, failed_source=False):
    from etl.build_dataset import FETCHERS

    scripts = tmp_path / "etl"
    scripts.mkdir()
    processed = tmp_path / "data" / "processed"
    processed.mkdir(parents=True)
    (processed / "scores.csv").write_text("previous scores")
    for name in FETCHERS:
        body = (
            "from pathlib import Path\n"
            f"Path({name!r} + '.done').touch()\n"
        )
        if failed_source and name == FETCHERS[0]:
            body += "raise SystemExit(7)\n"
        (scripts / name).write_text(body)
    (scripts / "build_dataset.py").write_text(
        "from pathlib import Path\n"
        f"assert all(Path(name + '.done').exists() for name in {FETCHERS!r})\n"
        "Path('data/processed/indicators.csv').write_text('updated indicators')\n"
    )
    (scripts / "build_scores.py").write_text(
        "from pathlib import Path\n"
        "assert Path('data/processed/indicators.csv').read_text() == 'updated indicators'\n"
        "Path('data/processed/scores.csv').write_text('updated scores')\n"
    )
    monkeypatch.setattr(entrypoint, "ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["entrypoint.py", "refresh"])
    return processed


def test_refresh_collects_before_merging_and_scoring(monkeypatch, tmp_path):
    processed = prepare_refresh(monkeypatch, tmp_path)
    assert entrypoint.main() == 0
    assert (processed / "indicators.csv").read_text() == "updated indicators"
    assert (processed / "scores.csv").read_text() == "updated scores"


def test_failed_fetcher_returns_failure_without_rebuilding_scores(monkeypatch, tmp_path, capsys):
    processed = prepare_refresh(monkeypatch, tmp_path, failed_source=True)
    assert entrypoint.main() == 7
    assert (processed / "scores.csv").read_text() == "previous scores"
    assert not (processed / "indicators.csv").exists()
    assert "Refresh failed" in capsys.readouterr().err
