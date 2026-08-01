"""Chat API route.

Deliberately wires together dependency factories that already exist in
every other router — companies.py, portfolios.py, watchlist.py,
research.py — rather than redefining them. Several of those functions
share names across files (get_valuation_use_case means something
different in companies.py vs portfolios.py) so imports here are
explicitly aliased to keep that straight.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from src.api.auth import get_authenticated_user_id
from src.api.routers.companies import (
    get_analysis_use_case,
    get_company_repository,
    get_data_provider,
)
from src.api.routers.companies import get_valuation_use_case as get_company_valuation_use_case
from src.api.routers.portfolios import (
    get_add_holding_use_case,
    get_portfolio_repository,
    get_risk_use_case,
)
from src.api.routers.portfolios import get_create_use_case as get_create_portfolio_use_case
from src.api.routers.portfolios import get_delete_use_case as get_delete_portfolio_use_case
from src.api.routers.portfolios import get_get_use_case as get_get_portfolio_use_case
from src.api.routers.portfolios import get_list_use_case as get_list_portfolios_use_case
from src.api.routers.portfolios import get_valuation_use_case as get_portfolio_valuation_use_case
from src.api.routers.research import get_research_report_repository
from src.api.routers.watchlist import get_add_use_case as get_add_to_watchlist_use_case
from src.api.routers.watchlist import get_list_use_case as get_get_watchlist_use_case
from src.api.routers.watchlist import get_remove_use_case as get_remove_from_watchlist_use_case
from src.api.schemas import ChatRequestSchema, ChatResponseSchema, VercelChatRequestSchema
from src.application.interfaces.chat_agent import ChatAgentError, ChatMessage
from src.api.routers.watchlist import get_watchlist_repository
from src.application.use_cases.chat_with_agent import ChatWithAgentUseCase
from src.application.use_cases.manage_watchlist import (
    ListWatchlistNamesUseCase,
    UpdateWatchlistItemUseCase,
)
from src.application.use_cases.compute_universe_factor_snapshot import (
    ComputeUniverseFactorSnapshotUseCase,
)
from src.application.use_cases.get_factor_scores import GetFactorScoresUseCase
from src.application.use_cases.get_watchlist_news import GetWatchlistNewsUseCase
from src.application.use_cases.triage_watchlist import TriageWatchlistUseCase
from src.application.use_cases.compute_option_portfolio_valuation import (
    ComputeOptionPortfolioValuationUseCase,
)
from src.application.use_cases.compute_portfolio_greeks import ComputePortfolioGreeksUseCase
from src.application.use_cases.manage_option_holdings import (
    AddOptionHoldingUseCase,
    RemoveOptionHoldingUseCase,
)
from src.application.use_cases.recommend_stocks import RecommendStocksUseCase
from src.application.use_cases.screen_stocks import ScreenStocksUseCase
from src.application.use_cases.suggest_hedging import SuggestHedgingUseCase
from src.application.use_cases.suggest_rebalancing import SuggestRebalancingUseCase
from src.infrastructure.config import get_settings
from src.infrastructure.data_providers.marketdata_app_provider import MarketDataAppProvider
from src.infrastructure.llm_providers.anthropic_chat_agent import AnthropicChatAgent
from src.infrastructure.persistence.factor_score_repository_impl import (
    SqlAlchemyFactorScoreRepository,
)
from src.infrastructure.persistence.monitoring_repository_impl import (
    SqlAlchemyPriceSnapshotRepository,
)

router = APIRouter(prefix="/chat", tags=["chat"])


def get_chat_agent() -> AnthropicChatAgent:
    return AnthropicChatAgent(settings=get_settings())


def get_options_provider() -> MarketDataAppProvider:
    return MarketDataAppProvider(settings=get_settings())


def get_chat_use_case(
    chat_agent: AnthropicChatAgent = Depends(get_chat_agent),
    get_watchlist=Depends(get_get_watchlist_use_case),
    add_to_watchlist=Depends(get_add_to_watchlist_use_case),
    remove_from_watchlist=Depends(get_remove_from_watchlist_use_case),
    list_portfolios=Depends(get_list_portfolios_use_case),
    create_portfolio=Depends(get_create_portfolio_use_case),
    get_portfolio=Depends(get_get_portfolio_use_case),
    compute_valuation=Depends(get_portfolio_valuation_use_case),
    compute_risk=Depends(get_risk_use_case),
    add_holding=Depends(get_add_holding_use_case),
    delete_portfolio=Depends(get_delete_portfolio_use_case),
    compute_analysis=Depends(get_analysis_use_case),
    compute_company_valuation=Depends(get_company_valuation_use_case),
    research_repo=Depends(get_research_report_repository),
    company_repo=Depends(get_company_repository),
    portfolio_repo=Depends(get_portfolio_repository),
    options_provider: MarketDataAppProvider = Depends(get_options_provider),
    data_provider=Depends(get_data_provider),
    watchlist_repo=Depends(get_watchlist_repository),
) -> ChatWithAgentUseCase:
    screen_stocks = ScreenStocksUseCase(compute_company_valuation, compute_analysis)
    factor_repo = SqlAlchemyFactorScoreRepository()
    get_factor_scores = GetFactorScoresUseCase(
        factor_repo,
        ComputeUniverseFactorSnapshotUseCase(
            data_provider, compute_company_valuation, compute_analysis, factor_repo
        ),
    )
    return ChatWithAgentUseCase(
        chat_agent=chat_agent,
        get_watchlist=get_watchlist,
        add_to_watchlist=add_to_watchlist,
        remove_from_watchlist=remove_from_watchlist,
        list_portfolios=list_portfolios,
        create_portfolio=create_portfolio,
        get_portfolio=get_portfolio,
        compute_valuation=compute_valuation,
        compute_risk=compute_risk,
        add_holding=add_holding,
        delete_portfolio=delete_portfolio,
        compute_analysis=compute_analysis,
        compute_company_valuation=compute_company_valuation,
        research_repo=research_repo,
        suggest_rebalancing=SuggestRebalancingUseCase(compute_valuation),
        screen_stocks=screen_stocks,
        recommend_stocks=RecommendStocksUseCase(compute_risk, company_repo, screen_stocks),
        add_option_holding=AddOptionHoldingUseCase(portfolio_repo),
        remove_option_holding=RemoveOptionHoldingUseCase(portfolio_repo),
        compute_portfolio_greeks=ComputePortfolioGreeksUseCase(portfolio_repo, options_provider),
        compute_option_portfolio_valuation=ComputeOptionPortfolioValuationUseCase(
            portfolio_repo, options_provider
        ),
        suggest_hedging=SuggestHedgingUseCase(portfolio_repo, options_provider),
        update_watchlist_item=UpdateWatchlistItemUseCase(watchlist_repo),
        list_watchlists=ListWatchlistNamesUseCase(watchlist_repo),
        triage_watchlist=TriageWatchlistUseCase(
            watchlist_repo,
            data_provider,
            SqlAlchemyPriceSnapshotRepository(),
            valuation_use_case=compute_company_valuation,
        ),
        get_watchlist_news=GetWatchlistNewsUseCase(watchlist_repo, data_provider),
        get_factor_scores=get_factor_scores,
    )


@router.post("", response_model=ChatResponseSchema)
def chat(
    request: ChatRequestSchema,
    user_id: str = Depends(get_authenticated_user_id),
    use_case: ChatWithAgentUseCase = Depends(get_chat_use_case),
) -> ChatResponseSchema:
    history = [ChatMessage(role=m.role, content=m.content) for m in request.history]
    try:
        reply = use_case.execute(user_id, request.message, history)
    except ChatAgentError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return ChatResponseSchema(reply=reply)


@router.post("/stream")
def chat_stream(
    request: VercelChatRequestSchema,
    user_id: str = Depends(get_authenticated_user_id),
    use_case: ChatWithAgentUseCase = Depends(get_chat_use_case),
) -> StreamingResponse:
    """Vercel AI SDK-compatible endpoint, using the 'text' stream
    protocol (plain text chunks, no special framing) — the simplest
    protocol variant, documented specifically for non-JS backends.
    The request shape differs from the JSON endpoint above: the whole
    conversation arrives as one `messages` array, newest message last,
    rather than a separate message/history split.
    """
    if not request.messages:
        raise HTTPException(status_code=422, detail="messages must not be empty")
    *history_schemas, latest = request.messages
    history = [ChatMessage(role=m.role, content=m.text_content) for m in history_schemas]

    def generate():
        try:
            for chunk in use_case.execute_streaming(user_id, latest.text_content, history):
                yield chunk
        except ChatAgentError as exc:
            # Streaming has already started (status 200 sent) by the time
            # an error could occur mid-generation — can't switch to a real
            # HTTP error status at this point, so the error becomes visible
            # text instead, same principle as tool failures becoming
            # information fed back to the model rather than a hard crash.
            yield f"\n\n[Error: {exc}]"

    return StreamingResponse(generate(), media_type="text/plain")
