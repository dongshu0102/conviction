"""Contract for classifying a company's value chain position and
business model.

Genuinely different discipline from every other LLM interface in this
app (Master Lens, Market Structure narrative): those explain an
already-computed, deterministic value -- the LLM never decides the
result itself. Here, there IS no deterministic input to derive these
two dimensions from; nothing in this app's ingested, structured data
says whether a company designs, fabricates, or distributes, or
whether its revenue comes from subscriptions, advertising, or
hardware. The LLM genuinely performs the classification itself here,
constrained to a fixed, enumerated set of categories (not free text)
specifically so the result is usable as a real, consistent screener
filter -- "Chip Designer" and "Semiconductor Designer" must never
silently become two different, unmatchable filter values for what is
really the same category.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

# Fixed, enumerated categories -- deliberately not free text, so
# results are consistent and usable as real screener filter values.
VALUE_CHAIN_POSITIONS = [
    "Upstream — Materials/Components",
    "Upstream — Equipment/Tooling",
    "Midstream — Design/Development",
    "Midstream — Manufacturing/Fabrication",
    "Downstream — Platform/Distribution",
    "Downstream — Integration/Services",
    "Downstream — End-Product/Retail",
]

BUSINESS_MODELS = [
    "Subscription/SaaS",
    "Advertising",
    "Hardware/Product Sales",
    "Transaction/Platform Fees",
    "Licensing/Royalties",
    "Cloud Infrastructure/Usage-Based",
    "Mixed/Diversified",
]


@dataclass(frozen=True, slots=True)
class Nasdaq100ClassificationResult:
    value_chain_position: str | None  # None if the model's answer didn't match a real, known category
    business_model: str | None
    model_used: str


class Nasdaq100Classifier(ABC):
    @abstractmethod
    def classify(self, ticker: str, name: str, industry: str, description: str | None) -> Nasdaq100ClassificationResult:
        """Classify a real company into one value chain position and
        one business model, each from the fixed, enumerated lists
        above -- never inventing a new category outside them."""


class Nasdaq100ClassificationError(Exception):
    """Raised on any LLM provider failure — use cases catch this,
    never a provider-specific exception."""
