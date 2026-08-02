"""Anthropic (Claude) adapter for AI-suggested investment themes.

Same JSON-structured-output pattern as anthropic_theme_synthesis_generator.py.
The system prompt is unusually explicit about NOT fabricating ticker
symbols — a hallucinated ticker here is more consequential than in
other generators, since it could end up as something a user tries to
act on. The structural safety net (an un-ingested ticker must survive
a real ingestion attempt before it can be tagged into a theme) doesn't
excuse being loose about this in the prompt.
"""
from __future__ import annotations

import json
import logging

import anthropic

from src.application.interfaces.theme_suggestion_generator import (
    SuggestedTickerResult,
    ThemeSuggestionGenerationError,
    ThemeSuggestionGenerationResult,
    ThemeSuggestionGenerator,
)
from src.domain.entities.general_news import GeneralNewsHeadline
from src.infrastructure.config import Settings

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are helping an investor identify an emerging investable theme from \
real, recent market news. You will be given a list of real general news headlines (and \
possibly a topic hint from the user) — ground your suggestion in the ACTUAL headlines \
provided, do not invent a trend unrelated to them.

CRITICAL — ticker accuracy: every ticker symbol you name must be a REAL, ACTUAL public \
company you have genuine knowledge of. Do NOT invent a plausible-sounding ticker or guess \
at one you're unsure about. If you are not confident a ticker is correct, omit that \
candidate entirely rather than guess. This matters more here than in ordinary analysis — \
a fabricated ticker could end up being something the user tries to act on.

This is a SUGGESTION for human review, not an instruction to create anything — do not \
phrase your rationale as though the theme has already been created or the tickers already \
tagged.

Respond with ONLY a JSON object, no other text, with exactly these keys:
- "theme_name": a short, specific theme name (e.g. "AI Infrastructure", not "Technology")
- "rationale": 2-3 sentences on why this is an emerging theme, citing what's in the \
headlines
- "candidate_tickers": an array of 3-8 objects, each with "ticker", "company_name", and \
"reasoning" (1 sentence each, specific to why this company fits the theme)
"""


def _format_headline(h: GeneralNewsHeadline) -> dict:
    return {
        "title": h.title,
        "publisher": h.publisher,
        "published_at": h.published_at.isoformat() if h.published_at else None,
        "snippet": h.snippet,
    }


class AnthropicThemeSuggestionGenerator(ThemeSuggestionGenerator):
    def __init__(self, settings: Settings, client: anthropic.Anthropic | None = None) -> None:
        self._settings = settings
        self._client = client or anthropic.Anthropic(api_key=settings.anthropic_api_key)

    def generate(
        self,
        headlines: list[GeneralNewsHeadline],
        user_hint: str | None,
    ) -> ThemeSuggestionGenerationResult:
        data_json = json.dumps(
            {
                "user_hint": user_hint,
                "headlines": [_format_headline(h) for h in headlines],
            },
            indent=2,
        )

        try:
            response = self._client.messages.create(
                model=self._settings.anthropic_model,
                max_tokens=self._settings.anthropic_max_tokens,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": f"Recent news + hint:\n{data_json}"}],
            )
        except anthropic.APIError as exc:
            raise ThemeSuggestionGenerationError(f"Anthropic API request failed: {exc}") from exc

        text_blocks = [block.text for block in response.content if block.type == "text"]
        raw_text = "".join(text_blocks).strip()

        if raw_text.startswith("```"):
            raw_text = raw_text.split("\n", 1)[1] if "\n" in raw_text else raw_text
            raw_text = raw_text.removesuffix("```").strip()
            if raw_text.startswith("json"):
                raw_text = raw_text[4:].strip()

        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise ThemeSuggestionGenerationError(
                f"Model response was not valid JSON: {raw_text[:200]}"
            ) from exc

        required_keys = {"theme_name", "rationale", "candidate_tickers"}
        missing = required_keys - parsed.keys()
        if missing:
            raise ThemeSuggestionGenerationError(f"Model response missing keys: {missing}")

        try:
            candidates = [
                SuggestedTickerResult(
                    ticker=t["ticker"].strip().upper(),
                    company_name=t["company_name"],
                    reasoning=t["reasoning"],
                )
                for t in parsed["candidate_tickers"]
            ]
        except (KeyError, AttributeError, TypeError) as exc:
            raise ThemeSuggestionGenerationError(
                f"Model response's candidate_tickers was malformed: {exc}"
            ) from exc

        return ThemeSuggestionGenerationResult(
            theme_name=parsed["theme_name"],
            rationale=parsed["rationale"],
            candidate_tickers=candidates,
            model_used=self._settings.anthropic_model,
            raw_response={"stop_reason": response.stop_reason, "usage": dict(response.usage)},
        )
