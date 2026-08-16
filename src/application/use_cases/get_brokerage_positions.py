"""Use case: every currently-held position in the connected brokerage
account."""
from __future__ import annotations

from dataclasses import dataclass

from src.application.interfaces.brokerage_provider import (
    BrokerageProvider,
    BrokerageProviderError,
)
from src.domain.entities.brokerage import BrokeragePosition


class GetBrokeragePositionsError(Exception):
    """A real, visible failure — never silently swallowed."""


@dataclass(frozen=True, slots=True)
class GetBrokeragePositionsResult:
    positions: tuple[BrokeragePosition, ...]


class GetBrokeragePositionsUseCase:
    def __init__(self, provider: BrokerageProvider) -> None:
        self._provider = provider

    def execute(self) -> GetBrokeragePositionsResult:
        try:
            positions = self._provider.get_positions()
        except BrokerageProviderError as exc:
            raise GetBrokeragePositionsError(str(exc)) from exc

        return GetBrokeragePositionsResult(positions=tuple(positions))
