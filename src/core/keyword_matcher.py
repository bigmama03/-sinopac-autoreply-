"""Keyword detection, relevance scoring, and template recommendation."""

import json
import logging
from typing import Optional

from src.data.models import Keyword, Template

logger = logging.getLogger(__name__)


class MatchResult:
    def __init__(self):
        self.is_relevant: bool = False
        self.matched_keywords: list[str] = []
        self.categories: list[str] = []
        self.score: float = 0.0
        self.has_negative: bool = False
        self.negative_hits: list[str] = []


class KeywordMatcher:
    """Matches post text against configured keywords and recommends templates."""

    def __init__(self, keywords: list[Keyword], negative_keywords: list[str],
                 threshold: float = 3.0):
        self.keywords = keywords
        self.negative_keywords = negative_keywords
        self.threshold = threshold

    def match(self, text: str) -> MatchResult:
        """Score a post's text against all keywords."""
        result = MatchResult()
        if not text:
            return result

        text_lower = text.lower()

        # Check negative keywords first
        for neg in self.negative_keywords:
            if neg in text_lower:
                result.has_negative = True
                result.negative_hits.append(neg)

        # Score against positive keywords (longer keywords first for compound matching)
        sorted_kws = sorted(self.keywords, key=lambda k: len(k.keyword), reverse=True)
        matched_spans: list[tuple[int, int]] = []

        for kw in sorted_kws:
            kw_lower = kw.keyword.lower()
            idx = text_lower.find(kw_lower)
            if idx == -1:
                continue

            # Avoid double-counting overlapping keywords
            kw_end = idx + len(kw_lower)
            already_covered = any(
                s <= idx and e >= kw_end for s, e in matched_spans
            )
            if already_covered:
                continue

            matched_spans.append((idx, kw_end))
            result.matched_keywords.append(kw.keyword)
            result.score += kw.weight
            if kw.category and kw.category not in result.categories:
                result.categories.append(kw.category)

        result.is_relevant = result.score >= self.threshold
        return result

    def recommend_templates(self, result: MatchResult, templates: list[Template],
                            platform: str, top_n: int = 3) -> list[Template]:
        """Recommend best-matching templates for a match result."""
        if not result.is_relevant or not templates:
            return []

        # Filter by platform
        platform_abbr = {"threads": "threads", "facebook": "fb", "instagram": "ig"}
        plat_key = platform_abbr.get(platform, platform)
        platform_templates = [
            t for t in templates
            if plat_key in t.platforms.lower()
        ]

        if not platform_templates:
            platform_templates = templates  # Fallback to all

        # Score templates by category match
        scored: list[tuple[Template, float]] = []
        for t in platform_templates:
            score = float(t.priority)
            # Bonus for matching category
            if t.category in result.categories:
                score += 10.0
            # Bonus if template's keywords overlap with matched keywords
            if t.keywords:
                try:
                    t_kws = json.loads(t.keywords) if isinstance(t.keywords, str) else []
                    overlap = set(t_kws) & set(result.matched_keywords)
                    score += len(overlap) * 2.0
                except (json.JSONDecodeError, TypeError):
                    pass
            scored.append((t, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return [t for t, _ in scored[:top_n]]
