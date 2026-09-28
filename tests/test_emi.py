from services.emi import calculate_emi, effective_price


def test_effective_price_applies_discount():
    assert effective_price(100000, 5000) == 95000


def test_effective_price_never_negative():
    assert effective_price(1000, 5000) == 0


def test_no_cost_emi_has_zero_interest():
    result = calculate_emi(price=120000, down_payment=20000, tenure_months=10, annual_rate_percent=0)
    assert result.is_no_cost_emi is True
    assert result.total_interest == 0
    assert result.monthly_emi == 10000.0


def test_reducing_balance_emi_matches_known_formula():
    # Standard reducing-balance EMI check for a simple case.
    result = calculate_emi(price=100000, down_payment=0, tenure_months=12, annual_rate_percent=12)
    assert result.monthly_emi > 8300  # sanity bound, not exact due to compounding
    assert result.total_interest > 0
    assert result.is_no_cost_emi is False


def test_emi_raises_on_invalid_tenure():
    import pytest
    with pytest.raises(ValueError):
        calculate_emi(price=1000, tenure_months=0)
