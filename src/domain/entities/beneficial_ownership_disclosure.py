from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class BeneficialOwnershipDisclosure:
    """One reporting person's disclosure within one Schedule 13D or
    13G filing — the "who crossed 5% ownership, and did they say they
    want influence or not" disclosure, genuinely different from Form
    13F: 13F reports at the MANAGER level across their entire
    portfolio, quarterly, up to 45 days late; this reports at the
    SECURITY level the moment one specific holder crosses (or amends)
    a 5% stake, within days (5 business days for the initial filing,
    2 business days for a material amendment, per the SEC's 2023
    amendments effective February 2024).

    form_type distinguishes activist intent from passive: 13D means
    the filer stated a purpose that could include influencing
    management or control (Item 4); 13G is the shorter form for
    passive investors, index funds, and qualified institutions with no
    such stated intent. Confirmed directly against two real, distinct
    examples: Vanguard's routine, passive Apple stake files as 13G;
    Temasek's real, actual stake in e2open (a real, reported Elliott
    Management activist situation) files as 13D.

    One filing can involve several distinct reporting persons (e.g. a
    parent holding company alongside its operating affiliate) --
    confirmed directly against real data (Temasek Capital and its
    affiliate Aranda Investments both appear as separate rows for the
    same e2open filing), so a single filing is NOT the same as a
    single reporting person, and amount_beneficially_owned can
    genuinely be 0 for a holding-company-level entity in the group
    even though the filing as a whole represents a real, non-zero
    stake held by a different, related entity in the same group.

    percent_of_class is stored as a fraction (0.0748, not 7.48),
    matching this codebase's existing convention for percentage
    fields (e.g. PositionChange.pct_change) elsewhere.

    citizenship_or_place_of_organization and type_of_reporting_person
    are genuinely nullable, not just defensively typed: confirmed
    directly against a real, live production response (a real e2open
    disclosure) that FMP's own data can have citizenshipOrPlaceOfOrganization
    as a real, explicit null, not merely an empty string -- this is
    not a hypothetical edge case."""

    cik: str
    symbol: str
    filing_date: date
    accepted_date: date
    cusip: str
    name_of_reporting_person: str
    citizenship_or_place_of_organization: str | None
    sole_voting_power: int
    shared_voting_power: int
    sole_dispositive_power: int
    shared_dispositive_power: int
    amount_beneficially_owned: int
    percent_of_class: float
    type_of_reporting_person: str | None  # raw, as-filed, e.g. "IA" or "IA, OO"
    form_type: str  # "13D", "13G", or "UNKNOWN" -- see derive_form_type_from_url
    source_url: str
