"""Anthropic (Claude) adapter for value chain position / business
model classification. Same quarantine principle as the other LLM
provider modules in this app: this is the only module that knows
we're using Anthropic specifically for this feature.
"""
from __future__ import annotations

import json
import logging

import anthropic

from src.application.interfaces.nasdaq100_classifier import (
    BUSINESS_MODELS,
    VALUE_CHAIN_POSITIONS,
    Nasdaq100ClassificationError,
    Nasdaq100ClassificationResult,
    Nasdaq100Classifier,
)
from src.infrastructure.config import Settings

logger = logging.getLogger(__name__)

_VALUE_CHAIN_LIST = "\n".join(f"- {v}" for v in VALUE_CHAIN_POSITIONS)
_BUSINESS_MODEL_LIST = "\n".join(f"- {v}" for v in BUSINESS_MODELS)

_SYSTEM_PROMPT = f"""You are classifying a real, specific company into exactly one \
value chain position and exactly one business model, each from a fixed list below. \
Pick the single best-fitting category from each list -- never invent a new \
category, never pick more than one per list, even if a company genuinely spans \
several of these in reality. If a company is genuinely diversified across \
several real business models, use "Mixed/Diversified" for business_model rather \
than picking just one that undersells its real diversification.

Value chain positions (pick exactly one):
{_VALUE_CHAIN_LIST}

Business models (pick exactly one):
{_BUSINESS_MODEL_LIST}

Respond with ONLY a JSON object, using the EXACT text of your chosen categories \
from the lists above: {{"value_chain_position": "...", "business_model": "..."}} \
-- no other text.
"""


class AnthropicNasdaq100Classifier(Nasdaq100Classifier):
    def __init__(self, settings: Settings, client: anthropic.Anthropic | None = None) -> None:
        self._settings = settings
        self._client = client or anthropic.Anthropic(api_key=settings.anthropic_api_key)

    def classify(
        self, ticker: str, name: str, industry: str, description: str | None,
    ) -> Nasdaq100ClassificationResult:
        payload = {
            "ticker": ticker, "name": name, "industry": industry,
            "description": description or "(no real, ingested description available)",
        }
        data_json = json.dumps(payload, indent=2)

        try:
            response = self._client.messages.create(
                model=self._settings.anthropic_model,
                max_tokens=300,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": f"Company:\n{data_json}"}],
            )
        except anthropic.APIError as exc:
            raise Nasdaq100ClassificationError(f"Anthropic API request failed: {exc}") from exc

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
            raise Nasdaq100ClassificationError(f"Model response was not valid JSON: {raw_text[:200]}") from exc

        raw_value_chain = parsed.get("value_chain_position")
        raw_business_model = parsed.get("business_model")

        # Validated against the real, fixed lists rather than trusted
        # blindly -- an LLM can still, occasionally, answer with text
        # close to but not exactly matching an allowed category. A
        # non-matching answer becomes an honest None, never a silent,
        # unfiltered new category value slipping into the screener.
        value_chain_position = raw_value_chain if raw_value_chain in VALUE_CHAIN_POSITIONS else None
        business_model = raw_business_model if raw_business_model in BUSINESS_MODELS else None

        if value_chain_position is None:
            logger.warning("%s: model's value_chain_position %r did not match a known category", ticker, raw_value_chain)
        if business_model is None:
            logger.warning("%s: model's business_model %r did not match a known category", ticker, raw_business_model)

        return Nasdaq100ClassificationResult(
            value_chain_position=value_chain_position, business_model=business_model,
            model_used=self._settings.anthropic_model,
        )
