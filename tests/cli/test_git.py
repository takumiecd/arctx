from stag.core.git.session import GitSession


def test_git_session_uses_transition_id():
    session = GitSession(
        session_id="gs_1",
        run_id="run",
        transition_id="t_1",
        repo_root="/repo",
        base_commit="abc",
        base_branch="main",
        base_dirty=False,
        started_at="2026-01-01T00:00:00+00:00",
        started_by="user",
    )

    data = session.to_dict()
    loaded = GitSession.from_dict(data)

    assert data["transition_id"] == "t_1"
    assert set(data) >= {"session_id", "run_id", "transition_id"}
    assert loaded.transition_id == "t_1"
