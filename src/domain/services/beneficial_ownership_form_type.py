"""Pure logic: FMP's acquisition-of-beneficial-ownership response has
no explicit "formType" field of its own -- the real, filed form type
(13D vs 13G) has to be derived from the filing's own SEC EDGAR URL,
which reliably embeds it. Confirmed directly against two real, distinct
filings, not assumed: Vanguard's routine, passive Apple stake carries
".../xslSCHEDULE_13G_X02/primary_doc.xml"; Temasek Capital's real
activist-adjacent stake in e2open (a real, reported Elliott Management
situation) carries ".../xslSCHEDULE_13D_X01/primary_doc.xml".
"""
from __future__ import annotations


def derive_form_type_from_url(url: str) -> str:
    """Returns "13D", "13G", or "UNKNOWN" -- never guesses when the
    URL doesn't match either known, confirmed pattern, since a wrong
    guess here would misclassify a passive stake as activist intent
    (or vice versa), which is the single most important distinction
    this entire feature exists to surface honestly."""
    if "SCHEDULE_13D" in url:
        return "13D"
    if "SCHEDULE_13G" in url:
        return "13G"
    return "UNKNOWN"
