from src.domain.services.beneficial_ownership_form_type import derive_form_type_from_url


def test_derives_13g_from_a_real_confirmed_url() -> None:
    """Real URL confirmed directly tonight: Vanguard Capital
    Management's routine, passive Apple stake."""
    url = "https://www.sec.gov/Archives/edgar/data/320193/000210011926000139/xslSCHEDULE_13G_X02/primary_doc.xml"
    assert derive_form_type_from_url(url) == "13G"


def test_derives_13d_from_a_real_confirmed_url() -> None:
    """Real URL confirmed directly tonight: Temasek Capital's stake in
    e2open, a real, reported Elliott Management activist situation."""
    url = "https://www.sec.gov/Archives/edgar/data/1021944/000110465925076163/xslSCHEDULE_13D_X01/primary_doc.xml"
    assert derive_form_type_from_url(url) == "13D"


def test_returns_unknown_for_an_empty_url() -> None:
    assert derive_form_type_from_url("") == "UNKNOWN"


def test_returns_unknown_rather_than_guessing_for_an_unrecognized_url_shape() -> None:
    """Never guesses -- a wrong guess here would misclassify passive
    vs. activist intent, the single most important distinction this
    feature exists to surface honestly."""
    assert derive_form_type_from_url("https://example.com/some-other-document.xml") == "UNKNOWN"
