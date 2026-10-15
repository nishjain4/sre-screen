"""Recognize repository overview requests without widening PR or issue requests."""
from __future__ import annotations

import re
from urllib.parse import urlsplit


def wants_repository_overview(query: str) -> bool:
    if re.match(r"\s*(?:please\s+)?(?:create|update|delete|merge|trigger|dispatch|remove)\b", query, re.I):
        return False
    urls = re.findall(r"https?://[^\s<>\"`]+", query)
    intent = re.sub(r"https?://[^\s<>\"`]+", "", query)
    if any(urlsplit(url).hostname in {"github.com", "gitlab.com"} for url in urls):
        return False
    if any(re.search(r"/(?:pulls|issues|commit|src)/", urlsplit(url).path) for url in urls):
        return False
    root_link = any(len(urlsplit(url.rstrip(".,;!?)")).path.strip("/").split("/")) >= 2 for url in urls)
    broad = bool(re.search(
        r"\b(?:overview|everything|deep analysis|deep dive|repository health|summari[sz]e|summary|investigate|analy[sz]e)\b",
        intent, re.I,
    ))
    focused = bool(re.search(
        r"\b(?:last commit|latest commit|branches|topics|languages|contributors|webhooks|readme|file|issues|prs?)\b",
        intent, re.I,
    ))
    if focused and not re.search(r"\b(?:overview|everything|repository health)\b", intent, re.I):
        return False
    return (root_link and (broad or not focused)) or (
        broad and bool(re.search(r"\b(?:gitea|repo|repository)\b", query, re.I))
    )
