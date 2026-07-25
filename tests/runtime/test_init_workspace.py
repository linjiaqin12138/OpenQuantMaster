import json

import pytest

from runtime.workspace.init_workspace import init_workspace


@pytest.fixture
def project_root(tmp_path):
    core = tmp_path / "skills" / "core"
    core.mkdir(parents=True)
    (core / "agent_demo.md").write_text("# agent_demo\n\nDo the demo.\n")
    return tmp_path


@pytest.mark.unit
def test_init_workspace_claude_target(project_root):
    written = init_workspace(project_root, ["claude"])

    assert project_root.joinpath("CLAUDE.md").exists()
    settings = json.loads(project_root.joinpath(".claude/settings.json").read_text())
    assert "Bash(python -m runtime.cli tool *)" in settings["permissions"]["allow"]
    assert project_root.joinpath(".claude/skills/oqm-tool/SKILL.md").exists()
    business = project_root.joinpath(".claude/skills/agent_demo/SKILL.md")
    assert business.exists()
    text = business.read_text()
    assert text.startswith("---\nname: agent_demo\ndescription: agent_demo\n---")
    assert "# agent_demo" in text
    assert not project_root.joinpath("AGENTS.md").exists()
    assert len(written) >= 4


@pytest.mark.unit
def test_init_workspace_codex_target(project_root):
    init_workspace(project_root, ["codex"])

    assert project_root.joinpath("AGENTS.md").exists()
    assert project_root.joinpath(".agents/skills/oqm-tool/SKILL.md").exists()
    assert project_root.joinpath(".agents/skills/agent_demo/SKILL.md").exists()
    assert not project_root.joinpath("CLAUDE.md").exists()


@pytest.mark.unit
def test_init_workspace_multiple_targets(project_root):
    init_workspace(project_root, ["claude", "kimi"])

    assert project_root.joinpath("CLAUDE.md").exists()
    assert project_root.joinpath("AGENTS.md").exists()


@pytest.mark.unit
def test_init_workspace_idempotent_without_force(project_root):
    init_workspace(project_root, ["claude"])
    claude_md = project_root / "CLAUDE.md"
    claude_md.write_text("user edits")
    (project_root / ".claude/settings.json").write_text(
        json.dumps({"permissions": {"allow": ["Bash(git *)"]}, "other": 1})
    )

    written = init_workspace(project_root, ["claude"])

    assert claude_md.read_text() == "user edits"
    settings = json.loads((project_root / ".claude/settings.json").read_text())
    assert "Bash(git *)" in settings["permissions"]["allow"]
    assert "Bash(python -m runtime.cli tool *)" in settings["permissions"]["allow"]
    assert settings["other"] == 1
    assert project_root / ".claude/settings.json" in written


@pytest.mark.unit
def test_init_workspace_force_overwrites(project_root):
    init_workspace(project_root, ["claude"])
    claude_md = project_root / "CLAUDE.md"
    claude_md.write_text("user edits")

    init_workspace(project_root, ["claude"], force=True)

    assert claude_md.read_text() != "user edits"


@pytest.mark.unit
def test_init_workspace_rejects_unknown_target(project_root):
    with pytest.raises(ValueError, match="Unknown agent target"):
        init_workspace(project_root, ["gpt"])
