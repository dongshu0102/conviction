"""Anthropic (Claude) adapter for thematic synthesis generation.

Same JSON-structured-output pattern as anthropic_research_generator.py.
The system prompt is explicit about the two DIFFERENT, OPPOSITE-polarity
scoring scales it will see (screen score: lower=better; factor score:
higher=better) — this is the single most likely way this feature could
silently produce a backwards narrative, so it gets stated in the prompt
itself, not just in code comments.
"""
from __future__ import annotations

import json
import logging

import anthropic

from src.application.interfaces.theme_synthesis_generator import (
    ThemeSynthesisGenerationError,
    ThemeSynthesisGenerationResult,
    ThemeSynthesisGenerator,
    TickerSynthesisInput,
)
from src.infrastructure.config import Settings

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are a financial analyst producing a thematic synthesis across a \
curated group of related companies. You will be given a theme name and structured data \
for each ticker in it. Ground every claim in the data provided — do not rely on general \
knowledge about these companies beyond what's given. If a ticker is missing a data point, \
work with what it has rather than guessing the gap.

CRITICAL — two DIFFERENT scoring scales with OPPOSITE polarity appear in the data:
- composite_screen_score: LOWER is better (rank 1 = cheapest/highest-quality in the group)
- factor_composite_score and the five *_z fields: HIGHER is better (a positive z-score \
means more attractive than the broader S&P 500 average)
Do not conflate these or describe a high screen_score as good, or a negative factor \
z-score as good — get this backwards and the entire narrative is wrong.

Respond with ONLY a JSON object, no other text, with exactly these four string keys:
- "overview": what ties this theme together and the broad picture across its members, \
2-3 sentences
- "common_threads": patterns/characteristics shared by most of the tickers, citing \
specific figures
- "notable_divergences": tickers that stand out from the rest of the group and why, \
citing specific figures
- "key_risks": risks visible from the data itself across the theme (e.g. broad \
overvaluation, weak momentum cluster) — not generic market risk unless evidenced in \
the data
"""


def _format_ticker(t: TickerSynthesisInput) -> dict:
    return {
        "ticker": t.ticker,
        "price": t.price,
        "price_to_earnings": t.price_to_earnings,
        "composite_screen_score_LOWER_IS_BETTER": t.composite_screen_score,
        "factor_composite_score_HIGHER_IS_BETTER": t.factor_composite_score,
        "value_z_HIGHER_IS_BETTER": t.value_z,
        "quality_z_HIGHER_IS_BETTER": t.quality_z,
        "growth_z_HIGHER_IS_BETTER": t.growth_z,
        "momentum_z_HIGHER_IS_BETTER": t.momentum_z,
        "size_z_HIGHER_IS_BETTER": t.size_z,
    }


class AnthropicThemeSynthesisGenerator(ThemeSynthesisGenerator):
    def __init__(self, settings: Settings, client: anthropic.Anthropic | None = None) -> None:
        self._settings = settings
        self._client = client or anthropic.Anthropic(api_key=settings.anthropic_api_key)

    def generate(
        self,
        theme_name: str,
        theme_description: str | None,
        tickers: list[TickerSynthesisInput],
    ) -> ThemeSynthesisGenerationResult:
        data_json = json.dumps(
            {
                "theme_name": theme_name,
                "theme_description": theme_description,
                "tickers": [_format_ticker(t) for t in tickers],
            },
            indent=2,
        )

        try:
            response = self._client.messages.create(
                model=self._settings.anthropic_model,
                max_tokens=self._settings.anthropic_max_tokens,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": f"Theme data:\n{data_json}"}],
            )
        except anthropic.APIError as exc:
            raise ThemeSynthesisGenerationError(f"Anthropic API request failed: {exc}") from exc

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
            raise ThemeSynthesisGenerationError(
                f"Model response was not valid JSON: {raw_text[:200]}"
            ) from exc

        required_keys = {"overview", "common_threads", "notable_divergences", "key_risks"}
        missing = required_keys - parsed.keys()
        if missing:
            raise ThemeSynthesisGenerationError(f"Model response missing keys: {missing}")

        return ThemeSynthesisGenerationResult(
            overview=parsed["overview"],
            common_threads=parsed["common_threads"],
            notable_divergences=parsed["notable_divergences"],
            key_risks=parsed["key_risks"],
            model_used=self._settings.anthropic_model,
            raw_response={"stop_reason": response.stop_reason, "usage": dict(response.usage)},
        )
