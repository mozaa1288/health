#!/usr/bin/env python3
"""Deterministic food quantity normalization."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any


class ConversionError(ValueError):
    pass


UNIT_ALIASES = {
    "gram": "g",
    "grams": "g",
    "kilogram": "kg",
    "kilograms": "kg",
    "milligram": "mg",
    "milligrams": "mg",
    "ounce": "oz",
    "ounces": "oz",
    "pound": "lb",
    "pounds": "lb",
    "milliliter": "ml",
    "milliliters": "ml",
    "millilitre": "ml",
    "millilitres": "ml",
    "liter": "l",
    "liters": "l",
    "litre": "l",
    "litres": "l",
    "teaspoon": "tsp",
    "teaspoons": "tsp",
    "tablespoon": "tbsp",
    "tablespoons": "tbsp",
    "fluid ounce": "fl oz",
    "fluid ounces": "fl oz",
    "fl_oz": "fl oz",
    "cups": "cup",
    "each": "count",
    "item": "count",
    "items": "count",
}

MASS_TO_G = {
    "mg": Decimal("0.001"),
    "g": Decimal("1"),
    "kg": Decimal("1000"),
    "oz": Decimal("28.349523125"),
    "lb": Decimal("453.59237"),
}

# US customary food-volume conversions.
VOLUME_TO_ML = {
    "ml": Decimal("1"),
    "l": Decimal("1000"),
    "tsp": Decimal("5"),
    "tbsp": Decimal("15"),
    "cup": Decimal("240"),
    "fl oz": Decimal("29.5735295625"),
}


def number(value: Any, label: str) -> Decimal:
    try:
        result = Decimal(str(value).strip())
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ConversionError(f"{label} must be numeric") from exc
    if not result.is_finite():
        raise ConversionError(f"{label} must be finite")
    return result


def normalize_unit(unit: Any) -> str:
    normalized = " ".join(str(unit or "").strip().casefold().split())
    normalized = UNIT_ALIASES.get(normalized, normalized)
    if not normalized:
        raise ConversionError("unit cannot be blank")
    return normalized


def base_quantity(quantity: Any, unit: Any) -> tuple[Decimal, str]:
    amount = number(quantity, "quantity")
    if amount < 0:
        raise ConversionError("quantity cannot be negative")
    normalized_unit = normalize_unit(unit)
    if normalized_unit in MASS_TO_G:
        return amount * MASS_TO_G[normalized_unit], "g"
    if normalized_unit in VOLUME_TO_ML:
        return amount * VOLUME_TO_ML[normalized_unit], "ml"
    return amount, "count" if normalized_unit == "count" else normalized_unit


def edible_grams(
    quantity: Any,
    unit: Any,
    *,
    grams_per_unit: Any | None = None,
    density_g_per_ml: Any | None = None,
    explicit_grams: Any | None = None,
) -> Decimal | None:
    """Return edible grams, requiring food-specific data for volume/count."""

    amount = number(quantity, "quantity")
    normalized_unit = normalize_unit(unit)
    computed: Decimal | None = None

    if normalized_unit in MASS_TO_G:
        computed = amount * MASS_TO_G[normalized_unit]
    elif grams_per_unit is not None:
        factor = number(grams_per_unit, "grams_per_unit")
        if factor <= 0:
            raise ConversionError("grams_per_unit must be positive")
        computed = amount * factor
    elif normalized_unit in VOLUME_TO_ML and density_g_per_ml is not None:
        density = number(density_g_per_ml, "density_g_per_ml")
        if density <= 0:
            raise ConversionError("density_g_per_ml must be positive")
        computed = amount * VOLUME_TO_ML[normalized_unit] * density

    supplied = (
        number(explicit_grams, "nutrition_grams_total")
        if explicit_grams is not None
        else None
    )
    if supplied is not None and supplied < 0:
        raise ConversionError("nutrition_grams_total cannot be negative")
    if supplied is not None and computed is not None:
        tolerance = max(Decimal("0.01"), computed * Decimal("0.001"))
        if abs(supplied - computed) > tolerance:
            raise ConversionError(
                "nutrition_grams_total conflicts with the deterministic unit conversion"
            )
    return computed if computed is not None else supplied
