from pathlib import Path


def test_launcher_uses_its_own_project_root_for_the_application() -> None:
    """A stale shell environment must not make the launcher serve a worktree UI."""
    launcher = Path(__file__).parents[2] / "quantradar.sh"

    assert "QUANTRADAR_APP_ROOT" not in launcher.read_text(encoding="utf-8")
