"""Zahlen im deutschen Format (ohne Abhängigkeiten, auch für den Mail-Versand)."""
from __future__ import annotations


def number_de(value: float, decimals: int = 2) -> str:
    text = f"{abs(value):,.{decimals}f}".replace(",", " ").replace(".", ",").replace(" ", ".")
    return ("−" if value < 0 else "") + text


def change_de(value: float | None, absolute: bool = False) -> str:
    if value is None:
        return "–"
    sign = "+" if value > 0 else "−" if value < 0 else "±"
    unit = " Pp." if absolute else " %"
    return f"{sign}{number_de(abs(value), 2 if absolute else 1)}{unit}"
