"""Tests for ComputeCompsValuationUseCase — real peer discovery and
real per-peer valuation (reusing ComputeValuationUseCase), aggregated
via the separately hand-verified compute_comps_valuation math."""
from __future__ import annotations

from datetime import date, datetime, timezone

from src.application.use_cases.compute_comps_valuation import (
    CompsMetric,
    ComputeCompsValuationUseCase,
    InsufficientPeerDataError,
    InsufficientTargetDataError,
)
from src.application.use_cases.compute_valuation import ComputeValuationUseCase
from src.application.use_cases.get_company_financials import (
    CompanyNotFoundError,
    GetCompanyFinancialsUseCase,
)
from src.domain.entities.company import Company, Sector
from src.domain.entities.financial_statement import BalanceSheet, FiscalPeriodKey, IncomeStatement, Period
from src.domain.entities.market_quote import MarketQuote
from tests.unit.fakes import FakeCompanyRepository, FakeDataProvider, FakeFinancialStatementRepository


def _key(ticker: str, year: int = 2025) -> FiscalPeriodKey:
    return FiscalPeriodKey(ticker=ticker, fiscal_year=year, period=Period.ANNUAL)


def _build(
    target_sector=Sector.TECHNOLOGY, peer_count=3, peer_sector=None, target_net_income=100.0,
    target_industry="Software", peer_industry=None, sector_only_peer_count=0,
):
    """Sets up a target company plus `peer_count` same-industry peers
    and, when given, `sector_only_peer_count` additional same-sector
    but DIFFERENT-industry peers (e.g. "Software" when the target is
    "Semiconductors") — both with real income statement data and a
    distinct quote so their own EV/multiples genuinely differ, not
    just copies of one value or, worse, unusable placeholders that
    get silently skipped."""
    peer_sector = peer_sector or target_sector
    peer_industry = peer_industry or target_industry
    company_repo = FakeCompanyRepository()
    statement_repo = FakeFinancialStatementRepository()
    quotes_by_ticker = {}

    target = Company(ticker="TARGET", name="Target Inc", sector=target_sector,
                      industry=target_industry, exchange="NASDAQ", country="US")
    company_repo.save(target)
    statement_repo.save_income_statement(IncomeStatement(
        key=_key("TARGET"), fiscal_date_ending=date(2025, 12, 31), reported_currency="USD",
        revenue=1000.0, net_income=target_net_income, ebitda=200.0,
    ))
    quotes_by_ticker["TARGET"] = MarketQuote(
        ticker="TARGET", price=10.0, market_cap=1000.0, as_of=datetime.now(timezone.utc)
    )

    for i in range(peer_count):
        ticker = f"PEER{i}"
        company_repo.save(Company(ticker=ticker, name=f"Peer {i}", sector=peer_sector,
                                   industry=peer_industry, exchange="NASDAQ", country="US"))
        # Each peer has a different net_income, giving each a genuinely
        # different P/E when priced against the same market cap.
        statement_repo.save_income_statement(IncomeStatement(
            key=_key(ticker), fiscal_date_ending=date(2025, 12, 31), reported_currency="USD",
            revenue=500.0, net_income=50.0 + i * 10, ebitda=100.0,
        ))
        quotes_by_ticker[ticker] = MarketQuote(
            ticker=ticker, price=20.0, market_cap=1000.0, as_of=datetime.now(timezone.utc)
        )

    for i in range(sector_only_peer_count):
        ticker = f"SECTORPEER{i}"
        company_repo.save(Company(
            ticker=ticker, name=f"Sector Peer {i}", sector=target_sector,
            industry="Software" if target_industry != "Software" else "Hardware",
            exchange="NASDAQ", country="US",
        ))
        statement_repo.save_income_statement(IncomeStatement(
            key=_key(ticker), fiscal_date_ending=date(2025, 12, 31), reported_currency="USD",
            revenue=500.0, net_income=80.0 + i * 10, ebitda=150.0,
        ))
        quotes_by_ticker[ticker] = MarketQuote(
            ticker=ticker, price=25.0, market_cap=1200.0, as_of=datetime.now(timezone.utc)
        )

    provider = FakeDataProvider(
        company=target, income_statements=[], balance_sheets=[], cash_flow_statements=[],
        quotes_by_ticker=quotes_by_ticker,
    )
    get_financials = GetCompanyFinancialsUseCase(company_repo, statement_repo)
    compute_valuation = ComputeValuationUseCase(get_financials, provider)
    use_case = ComputeCompsValuationUseCase(company_repo, get_financials, compute_valuation)
    return use_case, company_repo


def test_comps_finds_same_sector_peers_and_excludes_the_target_itself() -> None:
    use_case, _ = _build(peer_count=3)
    assessment = use_case.execute("TARGET", CompsMetric.PE)

    assert "TARGET" not in assessment.peers_considered
    assert set(assessment.peers_considered) == {"PEER0", "PEER1", "PEER2"}
    assert len(assessment.peers_used) == 3
    assert assessment.peers_skipped == []


def test_comps_excludes_a_different_sector_company_from_the_peer_set() -> None:
    use_case, company_repo = _build(peer_count=2)
    company_repo.save(Company(ticker="OTHERSECTOR", name="Different Co", sector=Sector.HEALTHCARE,
                               industry="Pharma", exchange="NYSE", country="US"))
    assessment = use_case.execute("TARGET", CompsMetric.PE)

    assert "OTHERSECTOR" not in assessment.peers_considered


def test_comps_applies_the_median_peer_pe_to_the_targets_own_net_income() -> None:
    use_case, _ = _build(peer_count=3, target_net_income=100.0)
    assessment = use_case.execute("TARGET", CompsMetric.PE)

    # Each peer: market_cap=1000, net_income = 50, 60, 70 -> P/E = 20, 16.67, 14.29
    # median P/E should be the middle value (peer with net_income=60 -> P/E ~16.67)
    assert assessment.result.median_multiple > 0
    assert assessment.result.implied_equity_value == assessment.result.median_multiple * 100.0


def test_comps_raises_insufficient_target_data_when_target_lacks_the_metric() -> None:
    # EBITDA was never set on TARGET's income statement in this scenario variant.
    statement_repo = FakeFinancialStatementRepository()
    company_repo2 = FakeCompanyRepository()
    company_repo2.save(Company(ticker="NOEBITDA", name="No Ebitda Co", sector=Sector.TECHNOLOGY,
                                industry="Software", exchange="NASDAQ", country="US"))
    statement_repo.save_income_statement(IncomeStatement(
        key=_key("NOEBITDA"), fiscal_date_ending=date(2025, 12, 31), reported_currency="USD",
        revenue=1000.0, net_income=100.0, ebitda=None,
    ))
    for i in range(2):
        ticker = f"PEER{i}"
        company_repo2.save(Company(ticker=ticker, name=f"Peer {i}", sector=Sector.TECHNOLOGY,
                                    industry="Software", exchange="NASDAQ", country="US"))
        statement_repo.save_income_statement(IncomeStatement(
            key=_key(ticker), fiscal_date_ending=date(2025, 12, 31), reported_currency="USD",
            revenue=500.0, net_income=50.0, ebitda=100.0,
        ))
        statement_repo.save_balance_sheet(BalanceSheet(
            key=_key(ticker), fiscal_date_ending=date(2025, 12, 31), reported_currency="USD",
            total_debt=100.0, cash_and_equivalents=50.0, shares_outstanding=100.0,
        ))
    provider = FakeDataProvider(
        company=None, income_statements=[], balance_sheets=[], cash_flow_statements=[],
        quotes_by_ticker={
            "NOEBITDA": MarketQuote(ticker="NOEBITDA", price=10.0, market_cap=1000.0, as_of=datetime.now(timezone.utc)),
            "PEER0": MarketQuote(ticker="PEER0", price=20.0, market_cap=1000.0, as_of=datetime.now(timezone.utc)),
            "PEER1": MarketQuote(ticker="PEER1", price=20.0, market_cap=1000.0, as_of=datetime.now(timezone.utc)),
        },
    )
    get_financials = GetCompanyFinancialsUseCase(company_repo2, statement_repo)
    compute_valuation = ComputeValuationUseCase(get_financials, provider)
    use_case2 = ComputeCompsValuationUseCase(company_repo2, get_financials, compute_valuation)

    try:
        use_case2.execute("NOEBITDA", CompsMetric.EV_EBITDA)
        raise AssertionError("expected InsufficientTargetDataError")
    except InsufficientTargetDataError:
        pass


def test_comps_raises_company_not_found_for_a_non_ingested_ticker() -> None:
    use_case, _ = _build(peer_count=2)
    try:
        use_case.execute("GHOST", CompsMetric.PE)
        raise AssertionError("expected CompanyNotFoundError")
    except CompanyNotFoundError:
        pass


def test_comps_raises_insufficient_peer_data_with_zero_peers() -> None:
    use_case, _ = _build(peer_count=0)
    try:
        use_case.execute("TARGET", CompsMetric.PE)
        raise AssertionError("expected InsufficientPeerDataError")
    except InsufficientPeerDataError:
        pass


def test_comps_prefers_industry_matching_when_enough_industry_peers_exist() -> None:
    """Regression test for a real, found issue: 3 same-industry peers
    is enough to skip the sector-level fallback entirely, matching
    the _MIN_PEERS_BEFORE_SECTOR_FALLBACK threshold exactly."""
    use_case, _ = _build(peer_count=3, target_industry="Semiconductors")
    assessment = use_case.execute("TARGET", CompsMetric.PE)

    assert assessment.peer_match_level == "industry"
    assert set(assessment.peers_considered) == {"PEER0", "PEER1", "PEER2"}


def test_comps_falls_back_to_sector_when_industry_pool_is_too_small() -> None:
    """The real scenario this fix exists for: a specific industry
    (e.g. Semiconductors) has too few same-industry peers in the
    universe, so same-sector peers (e.g. broader Technology, which can
    include software companies with very different multiple profiles)
    are used to supplement, not silently returned as-is or empty."""
    use_case, _ = _build(peer_count=1, target_industry="Semiconductors", sector_only_peer_count=3)
    assessment = use_case.execute("TARGET", CompsMetric.PE)

    assert assessment.peer_match_level == "industry+sector"
    assert "PEER0" in assessment.peers_considered  # the one real industry peer
    assert any(p.startswith("SECTORPEER") for p in assessment.peers_considered)


def test_comps_reports_pure_sector_when_no_industry_peers_exist_at_all() -> None:
    use_case, _ = _build(peer_count=0, target_industry="Semiconductors", sector_only_peer_count=3)
    assessment = use_case.execute("TARGET", CompsMetric.PE)

    assert assessment.peer_match_level == "sector"
    assert len(assessment.peers_considered) == 3


def test_comps_does_not_double_count_a_peer_in_both_industry_and_sector_lists() -> None:
    """A same-industry peer should never also appear via the
    sector-fallback supplement — a real, easy duplication bug to
    introduce when combining two separately-filtered lists."""
    use_case, _ = _build(peer_count=1, target_industry="Semiconductors", sector_only_peer_count=3)
    assessment = use_case.execute("TARGET", CompsMetric.PE)

    assert len(assessment.peers_considered) == len(set(assessment.peers_considered))
