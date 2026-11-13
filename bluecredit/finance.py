"""Loan math for BlueCredit.

Colombian lenders quote rates as *efectiva anual* (E.A.). The monthly rate is (1 + E.A.)^(1/12) − 1, not E.A. ÷ 12.
Payments use the French system (equal monthly payments), which is what Colombian consumer loans use.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Reference rates per lender type. They come from the original BlueCredit prototype, which stored them as monthly
# rates (1.8%, 2.2%, 3.5%, 2.5%); here they are converted correctly to E.A. Editable in Settings.
LENDERS = {
    "banco": {"name": "Banco tradicional", "ea": (1.018 ** 12 - 1),
              "desc": "Ej.: Bancolombia, Davivienda. Tasas más bajas, más requisitos."},
    "cooperativa": {"name": "Cooperativa o caja", "ea": (1.022 ** 12 - 1),
                    "desc": "Tasas medias, condiciones más flexibles."},
    "fintech": {"name": "Fintech o app", "ea": (1.035 ** 12 - 1),
                "desc": "Ej.: apps de crédito. Aprobación rápida, tasas más altas."},
    "nose": {"name": "No sé todavía", "ea": (1.025 ** 12 - 1),
             "desc": "Te mostramos un promedio de referencia."},
}

PURPOSES = {
    "negocio": "Negocio o emprendimiento",
    "tecnologia": "Electrodomésticos o tecnología",
    "vehiculo": "Vehículo",
    "vivienda": "Vivienda o mejoras del hogar",
    "educacion": "Educación",
    "deuda": "Pagar otra deuda",
    "otro": "Otro",
}


def monthly_rate(ea: float) -> float:
    return (1 + ea) ** (1 / 12) - 1


def ea_from_monthly(m: float) -> float:
    return (1 + m) ** 12 - 1


def payment(principal: float, ea: float, months: int) -> float:
    i = monthly_rate(ea)
    if i == 0:
        return principal / months
    return principal * i / (1 - (1 + i) ** -months)


@dataclass
class Row:
    month: int
    payment: float
    interest: float
    capital: float
    balance: float


def schedule(principal: float, ea: float, months: int) -> list[Row]:
    i, p, bal, rows = monthly_rate(ea), payment(principal, ea, months), principal, []
    for k in range(1, months + 1):
        intr = bal * i
        cap = p - intr
        bal = max(0.0, bal - cap)
        rows.append(Row(k, p, intr, cap, bal))
    return rows


@dataclass
class Capacity:
    ratio_new: float          # new payment ÷ income
    ratio_total: float        # (existing debts + new payment) ÷ income
    level: str               # buena / ajustada / riesgosa
    message: str
    max_payment: float       # largest payment that keeps total debt at 30% of income
    max_loan: float          # largest loan with that payment, same rate and term


def capacity(income: float, existing: float, new_payment: float, ea: float, months: int) -> Capacity:
    rn = new_payment / income if income else 1.0
    rt = (existing + new_payment) / income if income else 1.0
    room = max(0.0, 0.30 * income - existing)
    i = monthly_rate(ea)
    max_loan = room * (1 - (1 + i) ** -months) / i if i else room * months
    if rt <= 0.30:
        lvl, msg = "buena", (f"Entre esta cuota y tus otras deudas usarías el {rt:.0%} de tus ingresos. "
                             "Está por debajo del 30%, el límite que se considera sano.")
    elif rt <= 0.40:
        lvl, msg = "ajustada", (f"Entre esta cuota y tus otras deudas usarías el {rt:.0%} de tus ingresos. "
                                "Pasa del 30% recomendado: se puede, pero te deja poco margen para imprevistos.")
    else:
        lvl, msg = "riesgosa", (f"Entre esta cuota y tus otras deudas usarías el {rt:.0%} de tus ingresos. "
                                "Es más del 40%: hay riesgo real de atrasarte. Considera un monto menor o un plazo más largo.")
    return Capacity(rn, rt, lvl, msg, room, max_loan)


@dataclass
class Simulation:
    amount: float
    purpose: str
    months: int
    income: float
    existing: float
    lender: str
    ea: float
    usury_ea: float | None = None
    monthly: float = 0.0
    total: float = 0.0
    interest: float = 0.0
    cost_per_peso: float = 0.0
    cap: Capacity | None = None
    over_usury: bool = False
    alternatives: list = field(default_factory=list)   # (months, payment, total, interest)
    rows: list = field(default_factory=list)

    @property
    def monthly_pct(self) -> float:
        return monthly_rate(self.ea)


def simulate(amount, purpose, months, income, existing, lender, ea=None, usury_ea=None, lenders=None) -> Simulation:
    lenders = lenders or LENDERS
    ea = ea if ea is not None else lenders[lender]["ea"]
    s = Simulation(amount, purpose, months, income, existing, lender, ea, usury_ea)
    s.monthly = payment(amount, ea, months)
    s.total = s.monthly * months
    s.interest = s.total - amount
    s.cost_per_peso = s.interest / amount
    s.cap = capacity(income, existing, s.monthly, ea, months)
    s.over_usury = usury_ea is not None and ea > usury_ea + 1e-9
    terms = sorted({12, 24, 36, 48, 60, months})
    for m in terms:
        p = payment(amount, ea, m)
        s.alternatives.append((m, p, p * m, p * m - amount))
    s.rows = schedule(amount, ea, months)
    return s


def pesos(x: float) -> str:
    return ("-" if x < 0 else "") + "$" + f"{abs(x):,.0f}".replace(",", ".")
