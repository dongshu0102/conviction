"""Use case: generate the full, ten-lens Master Lens analysis for one
ticker.

Structurally enforces the same grounding discipline as
GenerateCompanyResearchUseCase: real financial data and a live
valuation snapshot are fetched FIRST, all ten scores are computed by
exact, deterministic arithmetic (never by the LLM), and only THEN does
the LLM get called -- to explain those ten already-fixed scores
through each investor's own framework, never to invent or re-derive
them. There is no code path here where a score reaches the response
without having been computed by src.domain.services.master_lens_scoring.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from src.application.interfaces.master_lens_narrative_generator import (
    MasterLensGenerationError,
    MasterLensNarrativeGenerator,
    MasterLensScoredInput,
)
from src.application.use_cases.compute_financial_analysis import ComputeFinancialAnalysisUseCase
from src.application.use_cases.compute_valuation import ComputeValuationUseCase
from src.application.use_cases.get_company_financials import CompanyNotFoundError
from src.domain.entities.master_lens import MasterLensAnalysis, MasterLensResult
from src.domain.services import master_lens_scoring as scoring

logger = logging.getLogger(__name__)

# Fixed, documented order -- always these ten, always in this order,
# never a subset. Each tuple is (master_name, lens_label, scoring_fn,
# uses_valuation) -- uses_valuation selects whether the scoring
# function takes the ValuationSnapshot or the CompanyFinancialAnalysis,
# since different lenses are grounded in different real data.
_LENSES: list[tuple[str, str, object, bool]] = [
    ("Buffett", "Moats & Owner Earnings", scoring.score_buffett, False),
    ("Munger", "Inversion & Incentives", scoring.score_munger, False),
    ("Graham", "Margin of Safety", scoring.score_graham, True),
    ("Lynch", "Know What You Own", scoring.score_lynch, False),
    ("Dalio", "Machines & Cycles", scoring.score_dalio, False),
    ("Marks", "Second-Level Thinking & Cycles", scoring.score_marks, True),
    ("Klarman", "Risk First", scoring.score_klarman, False),
    ("Fisher", "Scuttlebutt", scoring.score_fisher, False),
    ("Templeton", "Maximum Pessimism", scoring.score_templeton, True),
    ("Soros", "Reflexivity", scoring.score_soros, False),
]


class GetMasterLensAnalysisUseCase:
    def __init__(
        self,
        compute_financial_analysis: ComputeFinancialAnalysisUseCase,
        compute_valuation: ComputeValuationUseCase,
        narrative_generator: MasterLensNarrativeGenerator,
    ) -> None:
        self._compute_financial_analysis = compute_financial_analysis
        self._compute_valuation = compute_valuation
        self._narrative_generator = narrative_generator

    def execute(self, ticker: str) -> MasterLensAnalysis:
        ticker = ticker.strip().upper()

        try:
            analysis = self._compute_financial_analysis.execute(ticker, years=5)
        except CompanyNotFoundError:
            raise

        # Valuation is fetched separately and degrades honestly if it
        # fails (e.g. a live price quote is unavailable) -- the three
        # valuation-grounded lenses (Graham, Marks, Templeton) simply
        # report insufficient data rather than the whole analysis
        # failing over one live data point.
        try:
            valuation = self._compute_valuation.execute(ticker)
        except Exception as exc:
            logger.warning("Valuation unavailable for %s master lens analysis: %s", ticker, exc)
            valuation = None

        scored_inputs: list[MasterLensScoredInput] = []
        for master_name, lens_label, score_fn, uses_valuation in _LENSES:
            score, basis = score_fn(valuation if uses_valuation else analysis)
            scored_inputs.append(MasterLensScoredInput(
                master_name=master_name, lens_label=lens_label, score=score, score_basis=basis,
            ))

        try:
            narrative_result = self._narrative_generator.generate(
                ticker, analysis, valuation, scored_inputs,
            )
        except MasterLensGenerationError:
            logger.exception("Master Lens narrative generation failed for %s", ticker)
            raise

        results = tuple(
            MasterLensResult(
                master_name=s.master_name, lens_label=s.lens_label,
                score=s.score, score_basis=s.score_basis,
                narrative=narrative_result.narratives[s.master_name],
            )
            for s in scored_inputs
        )

        logger.info("Generated Master Lens analysis for %s (model=%s)", ticker, narrative_result.model_used)
        return MasterLensAnalysis(
            ticker=ticker, generated_at=datetime.now(timezone.utc),
            results=results, model_used=narrative_result.model_used,
        )
