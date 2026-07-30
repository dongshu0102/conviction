"""Anthropic (Claude) adapter for company research generation.

This is the ONLY module that knows we're using Anthropic specifically —
same quarantine principle as the FMP adapter. The prompt construction
here is deliberately explicit about grounding: real ingested numbers are
serialized into the prompt, and the system prompt instructs the model to
base its analysis on that data rather than general knowledge about the
company, and to flag when data is insufficient rather than fill gaps
with unstated assumptions.
"""
from __future__ import annotations

import json
import logging

import anthropic

from src.application.interfaces.research_generator import (
    ResearchGenerationError,
    ResearchGenerationResult,
    ResearchGenerator,
)
from src.application.use_cases.get_company_financials import CompanyFinancials
from src.infrastructure.config import Settings

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are a financial research analyst producing a structured \
company research report. You will be given a company profile and its recent \
financial statements. Ground every claim in the data provided — do not rely on \
general knowledge about the company beyond what's given. If the data is \
insufficient to support a claim (e.g. too few years to identify a trend), say so \
explicitly rather than filling the gap with an assumption.

Respond with ONLY a JSON object, no other text, with exactly these four string keys:
- "business_overview": what the company does, 2-3 sentences
- "financial_highlights": key trends visible in the provided statements (revenue, \
margins, profitability), citing specific figures
- "competitive_position": sector/industry context inferable from the profile data
- "key_risks": risks visible from the financial data itself (e.g. declining \
margins, high leverage) — not general market risks unless evidenced in the data
"""


def _serialize_financials(financials: CompanyFinancials) -> str:
    """Turns the domain object into the exact numbers the model will see —
    kept separate from the prompt template so it's easy to verify exactly
    what data reaches the model.
    """
    company = financials.company
    payload = {
        "company": {
            "ticker": company.ticker,
            "name": company.name,
            "sector": company.sector.value,
            "industry": company.industry,
            "exchange": company.exchange,
            "country": company.country,
        },
        "income_statements": [
            {
                "fiscal_year": s.key.fiscal_year,
                "revenue": s.revenue,
                "gross_profit": s.gross_profit,
                "operating_income": s.operating_income,
                "net_income": s.net_income,
                "eps_diluted": s.eps_diluted,
            }
            for s in financials.income_statements
        ],
        "balance_sheets": [
            {
                "fiscal_year": s.key.fiscal_year,
                "total_assets": s.total_assets,
                "total_liabilities": s.total_liabilities,
                "total_equity": s.total_equity,
                "total_debt": s.total_debt,
            }
            for s in financials.balance_sheets
        ],
        "cash_flow_statements": [
            {
                "fiscal_year": s.key.fiscal_year,
                "operating_cash_flow": s.operating_cash_flow,
                "free_cash_flow": s.free_cash_flow,
            }
            for s in financials.cash_flow_statements
        ],
    }
    return json.dumps(payload, indent=2)


class AnthropicResearchGenerator(ResearchGenerator):
    def __init__(self, settings: Settings, client: anthropic.Anthropic | None = None) -> None:
        self._settings = settings
        self._client = client or anthropic.Anthropic(api_key=settings.anthropic_api_key)

    def generate(self, financials: CompanyFinancials) -> ResearchGenerationResult:
        data_json = _serialize_financials(financials)

        try:
            response = self._client.messages.create(
                model=self._settings.anthropic_model,
                max_tokens=self._settings.anthropic_max_tokens,
                system=_SYSTEM_PROMPT,
                messages=[
                    {
                        "role": "user",
                        "content": f"Company data:\n{data_json}",
                    }
                ],
            )
        except anthropic.APIError as exc:
            raise ResearchGenerationError(f"Anthropic API request failed: {exc}") from exc

        text_blocks = [block.text for block in response.content if block.type == "text"]
        raw_text = "".join(text_blocks).strip()

        # Models frequently wrap JSON in a markdown code fence even when
        # explicitly told not to. Stripping it here is more robust than
        # relying on prompt wording alone to prevent it every time.
        if raw_text.startswith("```"):
            raw_text = raw_text.split("\n", 1)[1] if "\n" in raw_text else raw_text
            raw_text = raw_text.removesuffix("```").strip()
            if raw_text.startswith("json"):
                raw_text = raw_text[4:].strip()

        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise ResearchGenerationError(
                f"Model response was not valid JSON: {raw_text[:200]}"
            ) from exc

        required_keys = {
            "business_overview",
            "financial_highlights",
            "competitive_position",
            "key_risks",
        }
        missing = required_keys - parsed.keys()
        if missing:
            raise ResearchGenerationError(f"Model response missing keys: {missing}")

        return ResearchGenerationResult(
            business_overview=parsed["business_overview"],
            financial_highlights=parsed["financial_highlights"],
            competitive_position=parsed["competitive_position"],
            key_risks=parsed["key_risks"],
            model_used=self._settings.anthropic_model,
            raw_response={"stop_reason": response.stop_reason, "usage": dict(response.usage)},
        )
