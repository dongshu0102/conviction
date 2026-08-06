"""Use case: re-check every tracked speculative-growth candidate for a
user, diff against last-known state, and fire an Alert on genuine
condition changes only — never on steady-state, same principle as
RunMonitoringCheckUseCase for price moves.

Three triggers, matching the conditions discussed as the checkable
half of the "is 100x possible" framework:

1. Growth trend flips (accelerating <-> decelerating). Transitions
   involving "insufficient_data" are skipped — that state means the
   assessment genuinely can't tell yet, not a real change worth an
   alert.
2. Cash runway newly drops under 12 months — one-directional, since
   this is a risk escalating, not a two-way signal.
3. Market cap crosses the small-cap threshold, in either direction —
   crossing OUT can mean "the thesis may be playing out" just as much
   as crossing IN means "getting riskier," so both directions matter
   here, unlike runway.

A missing prior state (first check after adding) establishes the
baseline and fires nothing — there's no change to report before a
baseline exists.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from src.application.use_cases.assess_speculative_growth import AssessSpeculativeGrowthUseCase
from src.domain.entities.monitoring import Alert, AlertType
from src.domain.repositories.monitoring_repository import AlertRepository
from src.domain.repositories.speculative_growth_candidate_repository import (
    SpeculativeGrowthCandidateRepository,
)

logger = logging.getLogger(__name__)

_SMALL_CAP_THRESHOLD = 2_000_000_000  # matches AssessSpeculativeGrowthUseCase


class CheckSpeculativeGrowthCandidatesUseCase:
    def __init__(
        self,
        candidate_repo: SpeculativeGrowthCandidateRepository,
        alert_repo: AlertRepository,
        assess: AssessSpeculativeGrowthUseCase,
    ) -> None:
        self._candidate_repo = candidate_repo
        self._alert_repo = alert_repo
        self._assess = assess

    def execute(self, user_id: str) -> list[Alert]:
        candidates = self._candidate_repo.list_for_user(user_id)
        fired: list[Alert] = []

        for candidate in candidates:
            try:
                assessment = self._assess.execute(candidate.ticker)
            except Exception as exc:
                logger.warning(
                    "Speculative growth check: assessment failed for %s: %s",
                    candidate.ticker, exc,
                )
                continue

            now = datetime.now(timezone.utc)
            has_baseline = candidate.last_checked_at is not None

            if has_baseline:
                fired.extend(self._detect_changes(user_id, candidate, assessment, now))

            self._candidate_repo.update_last_state(
                user_id=user_id,
                ticker=candidate.ticker,
                growth_trend=assessment.growth_trend,
                cash_runway_months=assessment.cash_runway_months,
                market_cap=assessment.market_cap,
                checked_at=now,
            )

        return fired

    def _detect_changes(self, user_id, candidate, assessment, now) -> list[Alert]:
        alerts: list[Alert] = []
        ticker = candidate.ticker

        # 1. Growth trend flip — skip transitions involving unknown data.
        if (
            candidate.last_growth_trend != assessment.growth_trend
            and candidate.last_growth_trend not in (None, "insufficient_data")
            and assessment.growth_trend != "insufficient_data"
        ):
            alerts.append(self._save(Alert(
                user_id=user_id, ticker=ticker,
                alert_type=AlertType.GROWTH_CONDITION_CHANGED,
                message=(
                    f"{ticker}: revenue growth trend flipped from "
                    f"{candidate.last_growth_trend} to {assessment.growth_trend}."
                ),
                created_at=now,
            )))

        # 2. Cash runway newly under 12 months.
        was_low_runway = (
            candidate.last_cash_runway_months is not None
            and candidate.last_cash_runway_months < 12
        )
        is_low_runway = (
            assessment.cash_runway_months is not None
            and assessment.cash_runway_months < 12
        )
        if is_low_runway and not was_low_runway:
            alerts.append(self._save(Alert(
                user_id=user_id, ticker=ticker,
                alert_type=AlertType.GROWTH_CONDITION_CHANGED,
                message=(
                    f"{ticker}: cash runway dropped under 12 months "
                    f"(~{assessment.cash_runway_months:.0f} months) — worth a careful look."
                ),
                created_at=now,
            )))

        # 3. Market cap crosses the small-cap threshold, either direction.
        if candidate.last_market_cap is not None and assessment.market_cap is not None:
            was_small = candidate.last_market_cap < _SMALL_CAP_THRESHOLD
            is_small = assessment.market_cap < _SMALL_CAP_THRESHOLD
            if was_small != is_small:
                direction = "above" if is_small is False else "back under"
                alerts.append(self._save(Alert(
                    user_id=user_id, ticker=ticker,
                    alert_type=AlertType.GROWTH_CONDITION_CHANGED,
                    message=(
                        f"{ticker}: market cap moved {direction} the "
                        f"${_SMALL_CAP_THRESHOLD / 1e9:.0f}B small-cap threshold "
                        f"(now ${assessment.market_cap / 1e9:.1f}B)."
                    ),
                    created_at=now,
                )))

        return alerts

    def _save(self, alert: Alert) -> Alert:
        return self._alert_repo.save(alert)
