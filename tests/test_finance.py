import pytest

from bluecredit.finance import LENDERS, capacity, ea_from_monthly, monthly_rate, payment, schedule, simulate


def test_ea_monthly_round_trip():
    assert ea_from_monthly(monthly_rate(0.25)) == pytest.approx(0.25)
    assert monthly_rate(0.25) < 0.25 / 12          # E.A. ÷ 12 overstates the monthly rate


def test_prototype_payment_matches():
    # The prototype charged 1.8% a month; that is 23.87% E.A., not the 21.6% it displayed.
    ea = LENDERS["banco"]["ea"]
    assert ea == pytest.approx(0.2387, abs=1e-4)
    assert payment(5_000_000, ea, 24) == pytest.approx(258_404, abs=1)


def test_schedule_pays_off():
    rows = schedule(5_000_000, 0.24, 36)
    assert rows[-1].balance == pytest.approx(0, abs=1e-6)
    assert sum(r.capital for r in rows) == pytest.approx(5_000_000)
    assert rows[0].interest > rows[-1].interest


def test_capacity_includes_existing_debt():
    alone = capacity(2_500_000, 0, 258_404, 0.24, 24)
    with_debt = capacity(2_500_000, 600_000, 258_404, 0.24, 24)
    assert alone.level == "buena"
    assert with_debt.ratio_total > alone.ratio_total
    assert with_debt.level == "ajustada"


def test_max_loan_respects_30_percent():
    c = capacity(3_000_000, 200_000, 0, 0.30, 36)
    assert payment(c.max_loan, 0.30, 36) == pytest.approx(0.30 * 3_000_000 - 200_000)


def test_usury_flag():
    s = simulate(5_000_000, "otro", 24, 3_000_000, 0, "fintech", usury_ea=0.25)
    assert s.over_usury
    s = simulate(5_000_000, "otro", 24, 3_000_000, 0, "banco", usury_ea=0.25)
    assert not s.over_usury


def test_longer_term_costs_more():
    s = simulate(5_000_000, "otro", 24, 3_000_000, 0, "banco")
    totals = [t for _, _, t, _ in s.alternatives]
    assert totals == sorted(totals)
