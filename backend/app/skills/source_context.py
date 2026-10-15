"""Bounded, exact-revision source context shared by repository and PR reviews."""
from __future__ import annotations

import json
import re
from pathlib import PurePosixPath
from typing import Any

from app.skills.base import SkillContext, SkillResult

MAX_SOURCE_FILES = 12
MAX_FILE_CHARS = 16000
MAX_CONTEXT_CHARS = 64000
_PROJECT_FILES = {
    "package.json", "pyproject.toml", "requirements.txt", "tsconfig.json",
    "Dockerfile", "docker-compose.yml", "compose.yaml", "pytest.ini",
}


def context_paths(diff: str, tree: Any = None) -> list[str]:
    changed = list(dict.fromkeys(re.findall(r"^\+\+\+ b/(.+)$", diff, re.M)))
    entries = tree.get("tree") if isinstance(tree, dict) else None
    related = []
    stems = {PurePosixPath(path).stem.split(".")[0].removeprefix("test_") for path in changed}
    for entry in entries if isinstance(entries, list) else []:
        if not isinstance(entry, dict) or entry.get("type") != "blob":
            continue
        path = entry.get("path")
        if not isinstance(path, str):
            continue
        file = PurePosixPath(path)
        is_test = bool(re.search(r"(?:^|[/_.-])(test|tests|spec)(?:[/_.-]|$)", path))
        if (is_test and any(stem in file.name for stem in stems)) or file.name in _PROJECT_FILES:
            related.append(path)
    return list(dict.fromkeys([*changed, *sorted(related)]))


async def read_source_context(ctx: SkillContext, result: SkillResult, diff: str, sha: str,
                              tree: Any = None, scope: dict[str, Any] | None = None) -> str:
    if tree is not None and not (isinstance(tree, dict) and isinstance(tree.get("tree"), list)):
        result.notes.append("Source tree response malformed; related-test discovery is incomplete.")
    paths = context_paths(diff, tree)
    if len(paths) > MAX_SOURCE_FILES:
        result.notes.append(f"Source context limited to {MAX_SOURCE_FILES} of {len(paths)} candidate files; "
                            "remaining source and test relationships are unassessed.")
    if not paths:
        result.notes.append("No source paths were available for contextual analysis.")
        return ""
    if not ctx.has_tool("gitea__get_file_content"):
        result.notes.append("gitea__get_file_content unavailable; full source and test context was not assessed.")
        return ""
    outcomes = await ctx.call_many([
        ("gitea__get_file_content", {**(scope or {}), "path": path, "ref": sha},
         f"Read source/test context at reviewed SHA {sha}: {path}")
        for path in paths[:MAX_SOURCE_FILES]
    ])
    sections = []
    remaining = MAX_CONTEXT_CHARS
    for path, outcome in zip(paths, outcomes):
        data = outcome.data
        content = (data.get("decodedContent") if isinstance(data, dict) else data)
        if isinstance(data, dict) and content is None and data.get("encoding") != "base64":
            content = data.get("content")
        if not outcome.ok or not isinstance(content, str):
            result.notes.append(f"Source context {path} at {sha} unavailable: "
                                f"{outcome.call.error or 'response did not contain decoded text'}.")
            continue
        # JSON delimiting keeps repository text distinct from review instructions.
        limit = min(MAX_FILE_CHARS, remaining)
        excerpt = content[:limit]
        remaining -= len(excerpt)
        if len(excerpt) != len(content):
            result.notes.append(f"Source context {path} clipped at {len(excerpt)} of {len(content)} characters; "
                                "unseen code was not assessed.")
        sections.append(json.dumps({"path": path, "ref": sha, "content": excerpt,
                                    "complete": len(excerpt) == len(content)}))
    if isinstance(tree, dict) and tree.get("truncated"):
        result.notes.append("Repository tree was truncated; related-test discovery is incomplete.")
    return "\n".join(sections)
