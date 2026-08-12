from contextlib import contextmanager
from datetime import date
from unittest.mock import patch

import pytest
from sqlalchemy.exc import OperationalError

from src.domain.entities.institutional_holding import InstitutionalHolding
from src.infrastructure.persistence.institutional_holding_repository_impl import (
    SqlAlchemyInstitutionalHoldingRepository,
)


def _sample_holding() -> InstitutionalHolding:
    return InstitutionalHolding(
        accession_number="0001-26-000001", filer_cik="0001067983", filer_name="BERKSHIRE HATHAWAY INC",
        period_of_report=date(2026, 3, 31), issuer_name="APPLE INC", title_of_class="COM",
        cusip="037833100", value_usd=151_000_000, shares_or_principal_amount=905_000, share_type="SH",
        put_call=None, investment_discretion="SOLE", voting_authority_sole=905_000,
        voting_authority_shared=0, voting_authority_none=0,
    )


class _FakeSession:
    def add_all(self, _objects) -> None:
        pass


def test_save_chunk_with_retry_succeeds_on_a_later_attempt() -> None:
    """Regression test for a real, confirmed production failure: RDS's
    own Postgres log showed "could not receive data from client:
    Connection timed out" during a real, multi-minute bulk insert over
    the public internet -- a transient connection drop mid-chunk must
    be retried, not fail the entire multi-million-row ingestion."""
    call_count = {"n": 0}

    @contextmanager
    def flaky_session_scope():
        call_count["n"] += 1
        if call_count["n"] < 2:
            raise OperationalError("insert failed", None, Exception("could not receive data from client"))
        yield _FakeSession()

    repo = SqlAlchemyInstitutionalHoldingRepository()
    with patch(
        "src.infrastructure.persistence.institutional_holding_repository_impl.session_scope",
        flaky_session_scope,
    ), patch("time.sleep"):
        repo.bulk_save([_sample_holding()])

    assert call_count["n"] == 2


def test_save_chunk_with_retry_raises_the_original_error_after_exhausting_attempts() -> None:
    call_count = {"n": 0}

    @contextmanager
    def always_flaky_session_scope():
        call_count["n"] += 1
        raise OperationalError("insert failed", None, Exception("persistent connection failure"))
        yield  # pragma: no cover — unreachable, satisfies generator syntax

    repo = SqlAlchemyInstitutionalHoldingRepository()
    with patch(
        "src.infrastructure.persistence.institutional_holding_repository_impl.session_scope",
        always_flaky_session_scope,
    ), patch("time.sleep"):
        with pytest.raises(OperationalError, match="persistent connection failure"):
            repo.bulk_save([_sample_holding()])

    assert call_count["n"] == 4
