"""Load the home-page investigation templates from YAML."""
from __future__ import annotations

import logging
from pathlib import Path

import yaml
from pydantic import ValidationError

from app.schemas import TemplateInfo

logger = logging.getLogger(__name__)


def load_templates(path: Path) -> list[TemplateInfo]:
    if not path.exists():
        logger.warning("templates file %s not found", path)
        return []
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        logger.warning("failed to read templates file %s: %s", path, exc)
        return []
    templates: list[TemplateInfo] = []
    for item in raw.get("templates", []) if isinstance(raw, dict) else []:
        try:
            templates.append(TemplateInfo.model_validate(item))
        except (ValidationError, TypeError) as exc:
            logger.warning("ignoring invalid template in %s: %s", path, exc)
    return templates