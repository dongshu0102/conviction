"""Use case: start tracking a ticker as a speculative-growth candidate.

Deliberately does NOT gate on whether the assessment "looks good" —
that would turn this into exactly the automated verdict Growth Hunter
is built to avoid giving. It runs the assessment once, for two honest
reasons: to validate the ticker is actually assessable (propagates
CompanyNotFoundError otherwise), and to establish the initial
last-known state so the next periodic check has a real baseline to
diff against, rather than treating "just added" the same as "first
check ever" and needing an extra no-op run first.
"""
from __future__ import annotations

from datetime import datetime, timezone

from src.application.use_cases.assess_speculative_growth import AssessSpeculativeGrowthUseCase
from src.domain.entities.speculative_growth_candidate import SpeculativeGrowthCandidate
from src.domain.repositories.speculative_growth_candidate_repository import (
    SpeculativeGrowthCandidateRepository,
)


class AddSpeculativeGrowthCandidateUseCase:
    def __init__(
        self,
        candidate_repo: SpeculativeGrowthCandidateRepository,
        assess: AssessSpeculativeGrowthUseCase,
    ) -> None:
        self._candidate_repo = candidate_repo
        self._assess = assess

    def execute(self, user_id: str, ticker: str) -> SpeculativeGrowthCandidate:
        ticker = ticker.strip().upper()
        assessment = self._assess.execute(ticker)
        candidate = SpeculativeGrowthCandidate(
            user_id=user_id,
            ticker=ticker,
            added_at=datetime.now(timezone.utc),
            last_growth_trend=assessment.growth_trend,
            last_cash_runway_months=assessment.cash_runway_months,
            last_market_cap=assessment.market_cap,
            last_checked_at=assessment.as_of,
        )
        return self._candidate_repo.add(candidate)


class RemoveSpeculativeGrowthCandidateUseCase:
    def __init__(self, candidate_repo: SpeculativeGrowthCandidateRepository) -> None:
        self._candidate_repo = candidate_repo

    def execute(self, user_id: str, ticker: str) -> bool:
        return self._candidate_repo.remove(user_id, ticker.strip().upper())


class ListSpeculativeGrowthCandidatesUseCase:
    def __init__(self, candidate_repo: SpeculativeGrowthCandidateRepository) -> None:
        self._candidate_repo = candidate_repo

    def execute(self, user_id: str) -> list[SpeculativeGrowthCandidate]:
        return self._candidate_repo.list_for_user(user_id)
