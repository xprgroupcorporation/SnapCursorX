from __future__ import annotations


TIMING_MODE_CYCLE = "cycle"
TIMING_MODE_FREQUENCY = "frequency"

CYCLE_UNITS = ("ms", "sec", "min")
FREQUENCY_UNITS = ("CPS", "CPM", "CPH")


def _coerce_float(value, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _coerce_positive(value, default: float, minimum: float = 1.0) -> float:
    return max(float(minimum), _coerce_float(value, default))


def _coerce_positive_int(value, default: int, minimum: int = 1) -> int:
    try:
        parsed = int(round(float(value)))
    except (TypeError, ValueError):
        parsed = int(default)
    return max(int(minimum), parsed)


def cycle_to_interval_ms(value, unit: str) -> float:
    normalized_unit = str(unit or "ms").strip().lower()
    amount = _coerce_positive(value, 100.0)
    if normalized_unit == "sec":
        return amount * 1000.0
    if normalized_unit == "min":
        return amount * 60000.0
    return amount


def frequency_to_interval_ms(value, unit: str) -> float:
    normalized_unit = str(unit or "CPS").strip().upper()
    amount = _coerce_positive(value, 1.0)
    if normalized_unit == "CPM":
        return 60000.0 / amount
    if normalized_unit == "CPH":
        return 3600000.0 / amount
    return 1000.0 / amount


def sanitize_cycle_config(config: dict | None, default_interval_ms: float = 100.0) -> dict:
    source = dict(config or {})
    unit = str(source.get("unit", "ms") or "ms").strip().lower()
    if unit not in CYCLE_UNITS:
        unit = "ms"
    fallback_value = default_interval_ms
    if unit == "sec":
        fallback_value = max(1.0, default_interval_ms / 1000.0)
    elif unit == "min":
        fallback_value = max(1.0, default_interval_ms / 60000.0)
    value = _coerce_positive_int(source.get("value", fallback_value), fallback_value)
    return {
        "value": value,
        "unit": unit,
    }


def sanitize_frequency_config(config: dict | None, default_interval_ms: float = 100.0) -> dict:
    source = dict(config or {})
    unit = str(source.get("unit", "CPS") or "CPS").strip().upper()
    if unit not in FREQUENCY_UNITS:
        unit = "CPS"
    fallback_value = max(1.0, round(1000.0 / max(1.0, float(default_interval_ms))))
    if unit == "CPM":
        fallback_value = max(1.0, round(60000.0 / max(1.0, float(default_interval_ms))))
    elif unit == "CPH":
        fallback_value = max(1.0, round(3600000.0 / max(1.0, float(default_interval_ms))))
    value = _coerce_positive_int(source.get("value", fallback_value), int(fallback_value))
    return {
        "value": value,
        "unit": unit,
    }


def interval_ms_from_timing(source: dict | None, default_interval_ms: float = 100.0) -> float:
    if not isinstance(source, dict):
        return max(1.0, float(default_interval_ms))
    mode = str(source.get("click_mode", "") or "").strip().lower()
    if mode == TIMING_MODE_FREQUENCY:
        return frequency_to_interval_ms(
            source.get("frequency", {}).get("value", 1),
            source.get("frequency", {}).get("unit", "CPS"),
        )
    if mode == TIMING_MODE_CYCLE:
        return cycle_to_interval_ms(
            source.get("cycle", {}).get("value", default_interval_ms),
            source.get("cycle", {}).get("unit", "ms"),
        )
    legacy_delay = source.get("click_delay_ms", default_interval_ms)
    return max(1.0, _coerce_float(legacy_delay, default_interval_ms))


def normalize_timing_config(target: dict | None, default_interval_ms: float = 100.0, default_mode: str = TIMING_MODE_CYCLE) -> dict:
    if not isinstance(target, dict):
        target = {}

    legacy_delay = max(1.0, _coerce_float(target.get("click_delay_ms", default_interval_ms), default_interval_ms))
    mode = str(target.get("click_mode", default_mode) or default_mode).strip().lower()
    if mode not in (TIMING_MODE_CYCLE, TIMING_MODE_FREQUENCY):
        mode = TIMING_MODE_CYCLE

    target["cycle"] = sanitize_cycle_config(target.get("cycle"), default_interval_ms=legacy_delay)
    target["frequency"] = sanitize_frequency_config(target.get("frequency"), default_interval_ms=legacy_delay)
    target["click_mode"] = mode
    target["click_delay_ms"] = max(1, int(round(interval_ms_from_timing(target, default_interval_ms=legacy_delay))))
    return target


def apply_cycle_timing(target: dict, value: int | float, unit: str) -> dict:
    normalize_timing_config(target)
    target["click_mode"] = TIMING_MODE_CYCLE
    target["cycle"] = sanitize_cycle_config({"value": value, "unit": unit}, default_interval_ms=target.get("click_delay_ms", 100))
    target["click_delay_ms"] = max(1, int(round(interval_ms_from_timing(target, default_interval_ms=100.0))))
    return target


def apply_frequency_timing(target: dict, value: int | float, unit: str) -> dict:
    normalize_timing_config(target)
    target["click_mode"] = TIMING_MODE_FREQUENCY
    target["frequency"] = sanitize_frequency_config({"value": value, "unit": unit}, default_interval_ms=target.get("click_delay_ms", 100))
    target["click_delay_ms"] = max(1, int(round(interval_ms_from_timing(target, default_interval_ms=100.0))))
    return target

