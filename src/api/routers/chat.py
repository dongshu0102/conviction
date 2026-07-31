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
from src.application.use_cases.chat_with_agent import ChatWithAgentUseCase
from src.application.use_cases.screen_stocks import ScreenStocksUseCase
from src.application.use_cases.suggest_rebalancing import SuggestRebalancingUseCase
from src.infrastructure.config import get_settings
from src.infrastructure.llm_providers.anthropic_chat_agent import AnthropicChatAgent

router = APIRouter(prefix="/chat", tags=["chat"])


def get_chat_agent() -> AnthropicChatAgent:
    return AnthropicChatAgent(settings=get_settings())


def get_chat_use_case(
    chat_agent: AnthropicChatAgent = Depends(get_chat_agent),
    get_watchlist=Depends(get_get_watchlist_use_case),
    add_to_watchlist=Depends(get_add_to_watchlist_use_case),
    remove_from_watchlist=Depends(get_remove_from_watchlist_use_case),
    list_portfolios=Depends(get_list_portfolios_use_case),
    get_portfolio=Depends(get_get_portfolio_use_case),
    compute_valuation=Depends(get_portfolio_valuation_use_case),
    compute_risk=Depends(get_risk_use_case),
    add_holding=Depends(get_add_holding_use_case),
    delete_portfolio=Depends(get_delete_portfolio_use_case),
    compute_analysis=Depends(get_analysis_use_case),
    compute_company_valuation=Depends(get_company_valuation_use_case),
    research_repo=Depends(get_research_report_repository),
) -> ChatWithAgentUseCase:
    return ChatWithAgentUseCase(
        chat_agent=chat_agent,
        get_watchlist=get_watchlist,
        add_to_watchlist=add_to_watchlist,
        remove_from_watchlist=remove_from_watchlist,
        list_portfolios=list_portfolios,
        get_portfolio=get_portfolio,
        compute_valuation=compute_valuation,
        compute_risk=compute_risk,
        add_holding=add_holding,
        delete_portfolio=delete_portfolio,
        compute_analysis=compute_analysis,
        compute_company_valuation=compute_company_valuation,
        research_repo=research_repo,
        suggest_rebalancing=SuggestRebalancingUseCase(compute_valuation),
        screen_stocks=ScreenStocksUseCase(compute_company_valuation, compute_analysis),
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
