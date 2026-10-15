"""Auto-mode skill routing: LLM choice validated against a deterministic keyword/entity scorer."""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

from app.llm import prompts
from app.llm.base import LLMError, LLMProvider, Message
from app.skills.base import Skill
from app.skills.gitea_pr_review import wants_pr_review
from app.skills.repository_query import wants_repository_overview

logger = logging.getLogger(__name__)

@dataclass
class RouteDecision:
    skill_ids: list[str]
    reasoning: str
    method: str          # "llm" | "keywords"


def keyword_scores(query: str, skills: list[Skill]) -> dict[str, float]:
    text = query.lower()
    scores: dict[str, float] = {}
    for s in skills:
        score = 0.0
        for kw in s.keywords:
            if re.search(rf"(?<![a-z]){re.escape(kw.lower())}", text):
                score += 1.0 + 0.2 * kw.count(" ")      # multi-word keywords are more specific
        scores[s.id] = score

    def boost(skill_id: str, value: float) -> None:
        if skill_id in scores:
            scores[skill_id] += value

    if re.search(r"\bgitea\b|\brepo(?:sitory)?\b", text):
        boost("gitea_repository_discovery", 2.5)
    if wants_pr_review(query):
        boost("gitea_pull_requests", 10)
    return scores


def keyword_route(query: str, skills: list[Skill], limit: int) -> RouteDecision:
    if wants_repository_overview(query) and any(s.id == "gitea_repository_discovery" for s in skills):
        return RouteDecision(["gitea_repository_discovery"],
                             "Repository overview: run the eight-stage read-only Gitea playbook.", "keywords")
    scores = keyword_scores(query, skills)
    ranked = [sid for sid, sc in sorted(scores.items(), key=lambda kv: -kv[1]) if sc > 0.5][:limit]
    if not ranked:
        ranked = ["gitea_repository_discovery"] if "gitea_repository_discovery" in scores else []
        return RouteDecision(ranked, "No specific operation matched; using Gitea repository discovery.", "keywords")
    top = ", ".join(f"{sid} ({scores[sid]:.1f})" for sid in ranked)
    return RouteDecision(ranked, f"Selected by keyword and entity relevance: {top}.", "keywords")


async def route(query: str, skills: list[Skill], llm: LLMProvider, limit: int) -> RouteDecision:
    fallback = keyword_route(query, skills, limit)
    if wants_repository_overview(query):
        return fallback
    if not llm.available:
        return fallback
    known = {s.id for s in skills}
    listing = "\n".join(f"- {s.id}: {s.name} - {s.description}" for s in skills)
    user = prompts.ROUTER_USER.format(query=query[:4000], entities="Gitea repository context",
                                      skills=listing, suggestion=json.dumps(fallback.skill_ids), max_skills=limit)
    try:
        router_model = getattr(llm, "router_model", None)
        out = await llm.complete_json([Message("system", prompts.ROUTER_SYSTEM), Message("user", user)],
                                      temperature=0, model=router_model)
    except LLMError as exc:
        logger.warning("LLM routing failed, using keywords: %s", exc)
        return fallback
    chosen = [sid for sid in out.get("skills", []) if isinstance(sid, str) and sid in known]
    chosen = list(dict.fromkeys(chosen))[:limit]
    if wants_pr_review(query) and "gitea_pull_requests" in known:
        chosen = ["gitea_pull_requests", *[sid for sid in chosen if sid != "gitea_pull_requests"]][:limit]
    if not chosen:
        return fallback
    return RouteDecision(chosen, str(out.get("reasoning") or "").strip()[:600] or fallback.reasoning, "llm")
