"""Anthropic (Claude) adapter for Master Lens narrative generation.

This is the ONLY module that knows we're using Anthropic specifically
for this feature -- same quarantine principle as
anthropic_research_generator.py. The prompt is deliberately explicit
that each narrative must explain the ALREADY-COMPUTED score and basis
given to it, not independently re-derive or contradict a different
number -- the LLM's job here is explanation through a specific
investor's real framework, never arithmetic.
"""
from __future__ import annotations

import json
import logging

import anthropic

from src.application.interfaces.master_lens_narrative_generator import (
    MasterLensGenerationError,
    MasterLensNarrativeGenerator,
    MasterLensNarrativeResult,
    MasterLensScoredInput,
)
from src.domain.entities.financial_analysis import CompanyFinancialAnalysis
from src.domain.entities.valuation_snapshot import ValuationSnapshot
from src.infrastructure.config import Settings

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are producing ten short investment commentaries on one \
stock, each written through the lens of a different, historically significant \
investor's OWN, real, documented framework -- not a biography of them, a \
MODEL applied to this specific company's real, given data.

You will be given, for each of the ten investors: their name, the name of \
their specific analytical lens, a deterministic score from 0-10 that has \
ALREADY been computed by exact arithmetic (not by you), and the exact basis \
(the real numbers) that score was computed from. Your job for each one is to \
write a short, honest narrative (2-4 sentences) explaining what that score \
means through that specific investor's real framework -- using ONLY the \
score_basis figures given for that lens, plus the shared company data below. \
Never invent a different score or contradict the one given. If the basis \
notes insufficient data, say so plainly and explain what would be needed, \
rather than speculating.

Write in that investor's genuine analytical voice and vocabulary (e.g. \
Buffett's own "moat," Munger's own "invert," Klarman's own "margin of \
safety" framing) without inventing quotes or claiming these are their exact \
words.

Respond with ONLY a JSON object, no other text: a single object whose keys \
are each investor's name exactly as given, and whose values are the \
narrative string for that investor.
"""


def _serialize_context(
    ticker: str,
    analysis: CompanyFinancialAnalysis,
    valuation: ValuationSnapshot | None,
    scored_inputs: list[MasterLensScoredInput],
) -> str:
    payload = {
        "ticker": ticker,
        "yearly_ratios": [
            {
                "fiscal_year": r.fiscal_year,
                "revenue_growth_yoy": r.revenue_growth_yoy,
                "gross_margin": r.gross_margin,
                "free_cash_flow_margin": r.free_cash_flow_margin,
                "return_on_assets": r.return_on_assets,
                "debt_to_equity": r.debt_to_equity,
                "current_ratio": r.current_ratio,
            }
            for r in analysis.yearly_ratios
        ],
        "valuation": (
            {
                "price_to_earnings": valuation.price_to_earnings,
                "price_to_sales": valuation.price_to_sales,
                "price_to_book": valuation.price_to_book,
                "ev_to_ebitda": valuation.ev_to_ebitda,
            }
            if valuation is not None else None
        ),
        "lenses": [
            {
                "master_name": s.master_name,
                "lens_label": s.lens_label,
                "score": s.score,
                "score_basis": s.score_basis,
            }
            for s in scored_inputs
        ],
    }
    return json.dumps(payload, indent=2)


class AnthropicMasterLensNarrativeGenerator(MasterLensNarrativeGenerator):
    def __init__(self, settings: Settings, client: anthropic.Anthropic | None = None) -> None:
        self._settings = settings
        self._client = client or anthropic.Anthropic(api_key=settings.anthropic_api_key)

    def generate(
        self,
        ticker: str,
        analysis: CompanyFinancialAnalysis,
        valuation: ValuationSnapshot | None,
        scored_inputs: list[MasterLensScoredInput],
    ) -> MasterLensNarrativeResult:
        data_json = _serialize_context(ticker, analysis, valuation, scored_inputs)

        try:
            response = self._client.messages.create(
                model=self._settings.anthropic_model,
                max_tokens=self._settings.anthropic_max_tokens,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": f"Company and lens data:\n{data_json}"}],
            )
        except anthropic.APIError as exc:
            raise MasterLensGenerationError(f"Anthropic API request failed: {exc}") from exc

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
            raise MasterLensGenerationError(f"Model response was not valid JSON: {raw_text[:200]}") from exc

        expected_names = {s.master_name for s in scored_inputs}
        missing = expected_names - parsed.keys()
        if missing:
            raise MasterLensGenerationError(f"Model response missing narratives for: {missing}")

        return MasterLensNarrativeResult(
            narratives={name: parsed[name] for name in expected_names},
            model_used=self._settings.anthropic_model,
            raw_response={"stop_reason": response.stop_reason, "usage": dict(response.usage)},
        )
