from src.domain.services.economic_cycle_math import classify_economic_cycle


def test_a_triggered_sahm_rule_means_contraction_regardless_of_the_curve() -> None:
    result = classify_economic_cycle(yield_curve_inverted=True, sahm_rule_triggered=True)
    assert result.state == "Contraction"


def test_sahm_rule_takes_priority_over_the_curve_even_when_curve_data_is_missing() -> None:
    """The Sahm Rule is the most direct, real-time recession signal --
    it should classify Contraction even without any real curve data
    at all."""
    result = classify_economic_cycle(yield_curve_inverted=None, sahm_rule_triggered=True)
    assert result.state == "Contraction"


def test_an_inverted_curve_with_sahm_not_yet_triggered_is_a_late_cycle_warning() -> None:
    result = classify_economic_cycle(yield_curve_inverted=True, sahm_rule_triggered=False)
    assert result.state == "Late-cycle warning"


def test_an_inverted_curve_with_no_real_sahm_data_is_still_a_late_cycle_warning() -> None:
    result = classify_economic_cycle(yield_curve_inverted=True, sahm_rule_triggered=None)
    assert result.state == "Late-cycle warning"


def test_neither_signal_present_means_a_genuine_expansion() -> None:
    result = classify_economic_cycle(yield_curve_inverted=False, sahm_rule_triggered=False)
    assert result.state == "Expansion"


def test_both_signals_genuinely_unavailable_is_honestly_reported_as_insufficient_data() -> None:
    """Never guessed -- an honest 'insufficient data' rather than a
    fabricated Expansion or Contraction classification."""
    result = classify_economic_cycle(yield_curve_inverted=None, sahm_rule_triggered=None)
    assert result.state == "Insufficient data"


def test_real_signal_values_are_preserved_directly_on_the_result_not_hidden() -> None:
    """Each real, individual signal is preserved on the result itself
    -- never collapsed into a state string alone, matching this app's
    own 'surface each signal, never fake a composite' discipline."""
    result = classify_economic_cycle(yield_curve_inverted=True, sahm_rule_triggered=False)
    assert result.yield_curve_inverted is True
    assert result.sahm_rule_triggered is False


def test_reasoning_is_never_empty_for_any_real_classification() -> None:
    for yc, sahm in [(True, True), (True, False), (False, False), (None, None)]:
        result = classify_economic_cycle(yield_curve_inverted=yc, sahm_rule_triggered=sahm)
        assert len(result.reasoning) > 0
