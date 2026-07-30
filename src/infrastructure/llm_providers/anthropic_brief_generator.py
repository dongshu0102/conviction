"""Anthropic (Claude) adapter for Daily Brief narrative generation.

Plain text output, not JSON — a brief is meant to read like something a
person skims over coffee, not a structured report. All the exact
numbers it's grounded in are serialized into the prompt explicitly, and
the system prompt forbids introducing any figure not present in that
data.
"""
from __future__ import annotations

import logging

import anthropic

from src.application.interfaces.brief_generator import (
    BriefGenerationError,
    BriefGenerationResult,
    BriefGenerator,
)
from src.domain.entities.daily_brief import PortfolioBriefSummary, WatchlistPriceMove
from src.infrastructure.config import Settings

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are writing a short daily brief for an individual investor, \
summarizing their watchlist and portfolios. You will be given structured data — use \
ONLY the numbers provided, never introduce a figure, trend, or claim not present in \
the data. If a section has no data (empty watchlist, no portfolios), simply omit \
that section rather than commenting on its absence.

Write 3-5 sentences, plain prose, no headers or bullet points. Lead with whatever is \
most notable (the largest price move, or the biggest portfolio change) rather than \
listing everything in order. Tone: direct and factual, like a colleague giving you \
a quick heads-up — not promotional, not alarmist.
"""


def _format_watchlist(moves: list[WatchlistPriceMove]) -> str:
    if not moves:
        return "Watchlist: empty."
    lines = ["Watchlist price moves:"]
    for m in moves:
        if m.change_pct is not None:
            lines.append(f"- {m.ticker}: ${m.current_price:.2f} ({m.change_pct * 100:+.1f}%)")
        else:
            lines.append(f"- {m.ticker}: ${m.current_price:.2f} (no prior baseline yet)")
    return "\n".join(lines)


def _format_portfolios(summaries: list[PortfolioBriefSummary]) -> str:
    if not summaries:
        return "Portfolios: none with holdings."
    lines = ["Portfolio summaries:"]
    for p in summaries:
        gain = f"{p.total_unrealized_gain_pct * 100:+.1f}%" if p.total_unrealized_gain_pct is not None else "N/A"
        concentration = f"{p.largest_position_weight * 100:.0f}%" if p.largest_position_weight is not None else "N/A"
        lines.append(
            f"- {p.name}: ${p.total_market_value:,.0f} total value, "
            f"{gain} unrealized gain, largest position is {concentration} of portfolio"
        )
    return "\n".join(lines)


class AnthropicBriefGenerator(BriefGenerator):
    def __init__(self, settings: Settings, client: anthropic.Anthropic | None = None) -> None:
        self._settings = settings
        self._client = client or anthropic.Anthropic(api_key=settings.anthropic_api_key)

    def generate(
        self,
        watchlist_moves: list[WatchlistPriceMove],
        portfolio_summaries: list[PortfolioBriefSummary],
        unread_alert_count: int,
    ) -> BriefGenerationResult:
        data_text = (
            f"{_format_watchlist(watchlist_moves)}\n\n"
            f"{_format_portfolios(portfolio_summaries)}\n\n"
            f"Unread alerts: {unread_alert_count}"
        )

        try:
            response = self._client.messages.create(
                model=self._settings.anthropic_model,
                max_tokens=400,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": data_text}],
            )
        except anthropic.APIError as exc:
            raise BriefGenerationError(f"Anthropic API request failed: {exc}") from exc

        text_blocks = [block.text for block in response.content if block.type == "text"]
        narrative = "".join(text_blocks).strip()

        if not narrative:
            raise BriefGenerationError("Model returned an empty narrative")

        return BriefGenerationResult(narrative=narrative, model_used=self._settings.anthropic_model)
