"""Anthropic (Claude) adapter for market structure narrative
generation. Same quarantine principle as
anthropic_master_lens_narrative_generator.py: this is the only module
that knows we're using Anthropic specifically for this feature.
"""
from __future__ import annotations

import json
import logging

import anthropic

from src.application.interfaces.market_structure_narrative_generator import (
    MarketStructureGenerationError,
    MarketStructureNarrativeGenerator,
    MarketStructureNarrativeResult,
)
from src.infrastructure.config import Settings

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are explaining a company's real, already-computed \
market structure classification -- one of the four classic microeconomic \
categories (Perfect Competition, Monopolistic Competition, Oligopoly, \
Monopoly) -- through genuine economic theory.

You will be given: the company's ticker and real industry, the category \
ALREADY assigned (by exact, deterministic arithmetic, not by you), the real \
Herfindahl-Hirschman Index (HHI) computed for that industry group within \
this app's own ingested company universe, this company's own real market \
share of that group's total revenue, how many real, ingested peer \
companies share this same industry, and their tickers.

Write a short, honest explanation (3-5 sentences) of what this classification \
genuinely means for this specific company, grounded explicitly in the real \
HHI and market-share figures given -- never inventing a different number or \
contradicting the category given. Explain the classification using the real, \
defining traits of that specific market structure (e.g. Oligopoly: a few \
large, interdependent firms; Monopoly: one dominant firm with no close \
substitute; Monopolistic Competition: many differentiated competitors, real \
but limited pricing power).

If the category is "Unclassifiable (insufficient ingested peer data)", say so \
plainly and explain that this app's own ingested universe doesn't include \
enough real peer companies in this specific industry to compute a meaningful \
HHI, rather than speculating about the real market structure without genuine \
data support.

Also state directly, in your own words, this real, honest caveat: the HHI and \
market share here are computed only from companies this app has actually \
ingested (a large-cap-only universe), not the full real-world market \
including every private and small-cap competitor -- so concentration may be \
genuinely overstated versus the true market.

Respond with ONLY a JSON object: {"narrative": "..."} -- no other text.
"""


class AnthropicMarketStructureNarrativeGenerator(MarketStructureNarrativeGenerator):
    def __init__(self, settings: Settings, client: anthropic.Anthropic | None = None) -> None:
        self._settings = settings
        self._client = client or anthropic.Anthropic(api_key=settings.anthropic_api_key)

    def generate(
        self,
        ticker: str,
        industry: str,
        category: str,
        hhi: float | None,
        company_share: float | None,
        peer_count: int,
        peer_tickers: list[str],
    ) -> MarketStructureNarrativeResult:
        payload = {
            "ticker": ticker,
            "industry": industry,
            "category": category,
            "hhi": hhi,
            "company_market_share": company_share,
            "peer_count": peer_count,
            "peer_tickers": peer_tickers,
        }
        data_json = json.dumps(payload, indent=2)

        try:
            response = self._client.messages.create(
                model=self._settings.anthropic_model,
                max_tokens=self._settings.anthropic_max_tokens,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": f"Classification data:\n{data_json}"}],
            )
        except anthropic.APIError as exc:
            raise MarketStructureGenerationError(f"Anthropic API request failed: {exc}") from exc

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
            raise MarketStructureGenerationError(f"Model response was not valid JSON: {raw_text[:200]}") from exc

        narrative = parsed.get("narrative")
        if not narrative:
            raise MarketStructureGenerationError("Model response was missing the 'narrative' field.")

        return MarketStructureNarrativeResult(narrative=narrative, model_used=self._settings.anthropic_model)
