"""Contract any LLM-backed research generator must satisfy.

Same pattern as FinancialDataProvider: the use case depends on this
abstraction, never on the Anthropic SDK directly. Swapping models or
providers later is a new adapter class, not a rewrite of the use case.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from src.application.use_cases.get_company_financials import CompanyFinancials


@dataclass(frozen=True, slots=True)
class ResearchGenerationResult:
    business_overview: str
    financial_highlights: str
    competitive_position: str
    key_risks: str
    model_used: str
    raw_response: dict


class ResearchGenerator(ABC):
    @abstractmethod
    def generate(self, financials: CompanyFinancials) -> ResearchGenerationResult:
        """Produce a grounded research report from real financial data.

        Implementations must pass `financials` into the prompt context —
        the whole point of this agent is analysis grounded in ingested
        data, not the model's unverified training-data recollection of
        the company.
        """


class ResearchGenerationError(Exception):
    """Raised on any LLM provider failure (API error, rate limit, malformed
    response) — use cases catch this, never a provider-specific exception.
    """
