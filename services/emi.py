"""EMI math, kept entirely separate from scraped offer facts per the test's
requirement: scraped data (price, offer text) is fact; everything here is a
*calculated estimate* and must be labelled as such in the UI/API.

Two modes:
- Standard reducing-balance EMI, when an interest rate applies.
- No-cost EMI, when the source explicitly states it (rate = 0): the monthly
  instalment is simply the financed amount divided by tenure, with no
  interest component. This is only used when a source's offer_text/emi_rate
  says so -- we never assume no-cost EMI silently.
"""

from dataclasses import dataclass


@dataclass
class EmiResult:
    principal: float
    down_payment: float
    financed_amount: float
    tenure_months: int
    annual_rate_percent: float
    monthly_emi: float
    total_repayment: float
    total_interest: float
    is_no_cost_emi: bool


def calculate_emi(
    price: float,
    down_payment: float = 0.0,
    tenure_months: int = 12,
    annual_rate_percent: float = 13.0,
) -> EmiResult:
    financed = max(price - down_payment, 0.0)
    is_no_cost = annual_rate_percent <= 0

    if tenure_months <= 0:
        raise ValueError("tenure_months must be positive")

    if is_no_cost or financed == 0:
        monthly = financed / tenure_months if tenure_months else 0.0
        total_repayment = financed
        total_interest = 0.0
    else:
        monthly_rate = (annual_rate_percent / 100) / 12
        factor = (1 + monthly_rate) ** tenure_months
        monthly = financed * monthly_rate * factor / (factor - 1)
        total_repayment = monthly * tenure_months
        total_interest = total_repayment - financed

    return EmiResult(
        principal=price,
        down_payment=down_payment,
        financed_amount=financed,
        tenure_months=tenure_months,
        annual_rate_percent=annual_rate_percent,
        monthly_emi=round(monthly, 2),
        total_repayment=round(total_repayment, 2),
        total_interest=round(total_interest, 2),
        is_no_cost_emi=is_no_cost,
    )


def effective_price(selling_price: float, offer_discount: float = 0.0) -> float:
    """Price after an eligible, source-stated offer/bank discount.
    Does not stack multiple offers automatically -- offers are not assumed
    to be universally combinable (per the test's requirement)."""
    return max(selling_price - (offer_discount or 0.0), 0.0)

