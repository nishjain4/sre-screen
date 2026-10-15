"""Resolve an investigation's explicit repository links before executing tools."""
from __future__ import annotations

import re
from urllib.parse import unquote, urlsplit

from app.core.tools import ToolError

_URL = re.compile(r"https?://[^\s<>\"`]+", re.I)


def repository_scope(query: str, base_url: str | None) -> dict[str, str]:
    if not base_url:
        if _URL.search(query):
            raise ToolError("Cannot validate the supplied repository link: GITEA_URL is not configured.")
        return {}
    configured = urlsplit(base_url.rstrip("/"))
    prefix = configured.path.rstrip("/")
    repositories: set[tuple[str, str]] = set()
    for match in _URL.finditer(query):
        url = urlsplit(match.group().rstrip(".,;!?)"))
        path = url.path
        resource_link = bool(re.search(r"/(?:pulls|issues)/\d+(?:/|$)", path))
        if (url.scheme.lower(), url.netloc.lower()) != (configured.scheme.lower(), configured.netloc.lower()):
            if resource_link or url.hostname in {"github.com", "gitlab.com"} or (
                url.hostname and url.hostname.lower().startswith("gitea.")
            ):
                raise ToolError(
                    "The supplied PR/issue link belongs to a different server than GITEA_URL. "
                    "No request was sent to the configured default repository. Configure that server separately."
                )
            continue
        if prefix:
            if not path.startswith(prefix + "/"):
                continue
            path = path[len(prefix):]
        parts = path.strip("/").split("/")
        if len(parts) < 2 or parts[0].lower() in {"api", "explore", "admin", "user", "org", "notifications"}:
            continue
        owner, repo = unquote(parts[0]), unquote(parts[1])
        repo = repo.removesuffix(".git")
        if not owner or not repo or any(c in owner + repo for c in "/\\"):
            raise ToolError("Invalid repository owner or name in the supplied Gitea link.")
        repositories.add((owner, repo))
    if len(repositories) > 1:
        raise ToolError("Multiple Gitea repositories were linked. Select one repository per investigation; "
                        "the configured default was not used.")
    if not repositories:
        return {}
    owner, repo = repositories.pop()
    return {"owner": owner, "repo": repo}
