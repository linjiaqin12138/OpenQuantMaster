from __future__ import annotations

import json
from pathlib import Path

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "templates" / "workspace"

ALL_TARGETS = frozenset({"claude", "codex", "kimi"})
_AGENTS_TARGETS = frozenset({"codex", "kimi"})


def init_workspace(project_root: Path, targets: list[str], force: bool = False) -> list[Path]:
    unknown = set(targets) - ALL_TARGETS
    if unknown:
        raise ValueError(f"Unknown agent target(s): {sorted(unknown)}")

    project_root = project_root.resolve()
    skills = _load_skills(project_root)
    written: list[Path] = []

    if "claude" in targets:
        written += _write(project_root / "CLAUDE.md", _render("CLAUDE.md.tmpl"), force)
        written += _merge_settings(project_root / ".claude" / "settings.json")
        for name, body in skills:
            written += _write(project_root / ".claude" / "skills" / name / "SKILL.md", body, force)

    if _AGENTS_TARGETS & set(targets):
        written += _write(project_root / "AGENTS.md", _render("AGENTS.md.tmpl"), force)
        for name, body in skills:
            written += _write(project_root / ".agents" / "skills" / name / "SKILL.md", body, force)

    return written


def _render(template_name: str) -> str:
    return (TEMPLATES_DIR / template_name).read_text(encoding="utf-8")


def _load_skills(project_root: Path) -> list[tuple[str, str]]:
    skills: list[tuple[str, str]] = [
        ("oqm-tool", _render("skills/oqm-tool.SKILL.md")),
        ("vibe-trading", _render("skills/vibe-trading.SKILL.md")),
    ]
    core_dir = project_root / "skills" / "core"
    if core_dir.is_dir():
        for md in sorted(core_dir.glob("*.md")):
            skills.append((md.stem, _to_skill(md)))
    return skills


def _to_skill(md_path: Path) -> str:
    body = md_path.read_text(encoding="utf-8")
    description = md_path.stem
    for line in body.splitlines():
        if line.startswith("# "):
            description = line[2:].strip()
            break
    return f"---\nname: {md_path.stem}\ndescription: {description}\n---\n\n{body}"


def _write(path: Path, content: str, force: bool) -> list[Path]:
    if path.exists() and not force:
        return []
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return [path]


def _merge_settings(path: Path) -> list[Path]:
    template = json.loads(_render("settings.json.tmpl"))
    if path.exists():
        settings = json.loads(path.read_text(encoding="utf-8"))
    else:
        settings = {}
    allow = settings.setdefault("permissions", {}).setdefault("allow", [])
    for rule in template["permissions"]["allow"]:
        if rule not in allow:
            allow.append(rule)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    return [path]
