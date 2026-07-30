"""Btw-codes voor verkoopfacturen en een indicatieve totaalberekening.

Let op: het bedrag dat e-Boekhouden zelf berekent is leidend. Deze module is
er alleen om vooraf een concept te kunnen tonen, zodat je weet wat je bevestigt.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

# Btw-codes zoals e-Boekhouden ze voor verkoop hanteert, met het percentage dat
# we gebruiken voor de conceptberekening.
VERKOOP_BTW_CODES: dict[str, tuple[Decimal, str]] = {
    "HOOG_VERK_21": (Decimal("21"), "Hoog tarief 21% (verkoop)"),
    "LAAG_VERK_9": (Decimal("9"), "Laag tarief 9% (verkoop)"),
    "VERL_VERK": (Decimal("0"), "Btw verlegd (binnenland)"),
    "BI_EU_VERK": (Decimal("0"), "Levering binnen de EU (0%)"),
    "BU_EU_VERK": (Decimal("0"), "Levering buiten de EU (0%)"),
    "GEEN": (Decimal("0"), "Geen btw"),
}


def btw_percentage(vat_code: str) -> Decimal | None:
    """Percentage bij een btw-code, of None als de code onbekend is."""
    entry = VERKOOP_BTW_CODES.get(vat_code.upper())
    return entry[0] if entry else None


def beschrijf_btw_codes() -> list[dict[str, str]]:
    return [
        {"vatCode": code, "percentage": f"{pct}%", "omschrijving": oms}
        for code, (pct, oms) in VERKOOP_BTW_CODES.items()
    ]


def _rond(bedrag: Decimal) -> Decimal:
    return bedrag.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@dataclass
class Totalen:
    excl_btw: Decimal
    btw: Decimal
    incl_btw: Decimal
    onbekende_codes: list[str]

    def as_dict(self) -> dict:
        return {
            "totaalExclBtw": float(self.excl_btw),
            "totaalBtw": float(self.btw),
            "totaalInclBtw": float(self.incl_btw),
            "indicatief": True,
            "onbekendeBtwCodes": self.onbekende_codes,
        }


def bereken_totalen(regels: list[dict]) -> Totalen:
    """Tel de regels op. Regels met een onbekende btw-code tellen mee voor het
    bedrag exclusief btw, maar dragen 0 btw bij; de code wordt gerapporteerd."""
    excl = Decimal("0")
    btw = Decimal("0")
    onbekend: list[str] = []

    for regel in regels:
        aantal = Decimal(str(regel.get("quantity", 1)))
        prijs = Decimal(str(regel["pricePerUnit"]))
        regel_excl = _rond(aantal * prijs)
        excl += regel_excl

        code = str(regel.get("vatCode", ""))
        pct = btw_percentage(code)
        if pct is None:
            if code and code not in onbekend:
                onbekend.append(code)
            continue
        btw += _rond(regel_excl * pct / Decimal("100"))

    excl, btw = _rond(excl), _rond(btw)
    return Totalen(excl_btw=excl, btw=btw, incl_btw=_rond(excl + btw), onbekende_codes=onbekend)
