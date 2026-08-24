"""`--best` must not silently drop a row that holds the answer.

A row is quarantined when it conflicts with a column's established type. That
is a statement about the *schema*, not about the metric being compared — so a
row quarantined over an unrelated column (`lr="3e-4"`, a perfectly ordinary
thing to write) still holds a real measurement. `--best` was the only read path
that never consulted `TrialTable.invalid`, so such a row vanished from the
comparison and the winner came back silently wrong, rc 0, empty stderr.
"""

from __future__ import annotations

import json

from arctx.core.schema.payloads import payload_from_dict
from arctx_cli.commands.init import run_init_command
from arctx_cli.context import resolve_store
from arctx_cli.ext.optimize import cli_trials


class _Args:
    def __init__(self, **kw):
        self.name = "sweep"
        self.best = None
        self.sort = None
        self.desc = False
        self.as_json = False
        self.run = None
        self.store_dir = None
        self.__dict__.update(kw)


def _setup(tmp_path, monkeypatch, hidden_metrics):
    store_dir = str(tmp_path / "runs")
    run_init_command(
        requirement_id="r", target_type="task", target_id="t",
        run_id="tq", store_dir=store_dir, extensions=["optimize"],
    )
    store = resolve_store(store_dir)
    handle = store.load_run("tq")
    handle.ensure_lane(user_id="u", lane_id="L")

    from arctx.core.schema.payloads import StepPayload
    from arctx.ext.optimize.payloads import TrialPayload

    def trial(step, **kw):
        handle.attach(
            step.step_id,
            TrialPayload(payload_id="_", target_id="_", tables=("sweep",), **kw),
            user_id="u", lane_id="L",
        )

    s1 = handle.add_step([handle.root_node_id],
                         StepPayload(payload_id="_", target_id="_", type="t"),
                         user_id="u", lane_id="L")
    trial(s1, config={"lr": 0.1}, metrics={"loss": 0.9})
    s2 = handle.add_step([s1.output_node_id],
                         StepPayload(payload_id="_", target_id="_", type="t"),
                         user_id="u", lane_id="L")
    trial(s2, config={"lr": 0.01}, metrics={"loss": 0.1})
    # the row that actually won, quarantined for an unrelated column
    trial(s2, config={"lr": "3e-4"}, metrics=hidden_metrics)
    store.save_run(handle)
    monkeypatch.setenv("ARCTX_RUN_ID", "tq")
    return store_dir


def test_best_names_the_row_it_excluded(tmp_path, monkeypatch, capsys):
    store_dir = _setup(tmp_path, monkeypatch, {"loss": 0.01})
    rc = cli_trials(_Args(best="min:loss", store_dir=store_dir, run="tq"))
    out = capsys.readouterr()

    assert rc == 0
    # stdout stays machine-clean...
    assert "notice" not in out.out
    # ...and the user is told what was left out, and what it measured.
    assert "0.01" in out.err
    assert "excluded from this comparison" in out.err


def test_all_quarantined_does_not_claim_there_is_no_numeric_column(
    tmp_path, monkeypatch, capsys
):
    """The rows are active; they are hidden by a schema conflict, not absent."""
    store_dir = _setup(tmp_path, monkeypatch, {"other": 1.0})
    rc = cli_trials(_Args(name="sweep", best="min:other", store_dir=store_dir, run="tq"))
    out = capsys.readouterr()

    assert rc == 1
    assert "is quarantined" in out.err
    assert "no active row" not in out.err


def test_a_clean_table_is_unchanged(tmp_path, monkeypatch, capsys):
    store_dir = str(tmp_path / "runs")
    run_init_command(
        requirement_id="r", target_type="task", target_id="t",
        run_id="tc", store_dir=store_dir, extensions=["optimize"],
    )
    store = resolve_store(store_dir)
    handle = store.load_run("tc")
    handle.ensure_lane(user_id="u", lane_id="L")
    from arctx.core.schema.payloads import StepPayload
    from arctx.ext.optimize.payloads import TrialPayload

    step = handle.add_step([handle.root_node_id],
                           StepPayload(payload_id="_", target_id="_", type="t"),
                           user_id="u", lane_id="L")
    for lr, loss in ((0.1, 0.9), (0.01, 0.1)):
        handle.attach(
            step.step_id,
            TrialPayload(payload_id="_", target_id="_", tables=("sweep",),
                         config={"lr": lr}, metrics={"loss": loss}),
            user_id="u", lane_id="L",
        )
    store.save_run(handle)

    rc = cli_trials(_Args(best="min:loss", store_dir=store_dir, run="tc"))
    out = capsys.readouterr()
    assert rc == 0
    assert "0.1" in out.out
    assert out.err == ""
