from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    body: str
    raw: str


def load_skill(path: str | Path) -> Skill:
    skill_path = Path(path)
    raw = skill_path.read_text(encoding="utf-8")
    name = skill_path.stem
    description = ""
    body = raw

    if raw.startswith("---"):
        _, frontmatter, body = raw.split("---", 2)
        name, description = _parse_frontmatter(frontmatter)

    return Skill(name=name or skill_path.stem, description=description, body=body.strip(), raw=raw)


def _parse_frontmatter(text: str) -> tuple[str, str]:
    name = ""
    description_lines: list[str] = []
    in_description = False

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("name:"):
            name = stripped.removeprefix("name:").strip()
            in_description = False
            continue
        if stripped.startswith("description:"):
            in_description = True
            after = stripped.removeprefix("description:").strip()
            if after and after != "|":
                description_lines.append(after)
            continue
        if in_description:
            if line.startswith(" ") or not stripped:
                description_lines.append(stripped)
            else:
                in_description = False

    return name, "\n".join(line for line in description_lines if line).strip()
