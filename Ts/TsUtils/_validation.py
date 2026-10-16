"""Shared validation and normalisation helpers.

These helpers are reused across sub-packages (TsModels, TsMetrics, TsSims,
TsTests) so that scalar and small-array validation stays in one place.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from inspect import Parameter, signature
from numbers import Real

import numpy as np


def validate_int(name, value, *, minimum=0):
    """Return an integer after rejecting booleans and values below *minimum*.

    This is the shared integer validator across sub-packages. The default
    ``minimum=0`` covers non-negative integers; pass ``minimum=1`` for a
    strictly positive integer.
    """
    if isinstance(value, (bool, np.bool_)) or not isinstance(
        value,
        (int, np.integer),
    ):
        raise TypeError(f"{name} must be an integer >= {minimum}")
    value = int(value)
    if value < minimum:
        raise ValueError(f"{name} must be >= {minimum}, got {value}")
    return value


def validate_positive_int(name, value, minimum=1):
    """Return an integer argument after rejecting booleans and small values."""
    return validate_int(name, value, minimum=minimum)


def validate_bool(name, value):
    """Return a genuine boolean flag after rejecting non-Boolean inputs."""
    if not isinstance(value, (bool, np.bool_)):
        raise TypeError(f"{name} must be a boolean")
    return bool(value)


def validate_real(
    name: str,
    value: object,
    *,
    positive: bool = False,
    nonnegative: bool = False,
) -> float:
    """Return a finite float and optionally enforce its sign."""
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be a real number, got {type(value).__name__}")
    result = float(value)
    if not np.isfinite(result):
        raise ValueError(f"{name} must be finite, got {result}")
    if positive and result <= 0:
        raise ValueError(f"{name} must be > 0, got {result}")
    if nonnegative and result < 0:
        raise ValueError(f"{name} must be >= 0, got {result}")
    return result


def validate_choice(name: str, value: object, choices: tuple[str, ...]) -> str:
    """Return a string that is one of *choices*."""
    if not isinstance(value, str) or value not in choices:
        allowed = ", ".join(repr(choice) for choice in choices)
        raise ValueError(f"{name} must be one of {allowed}, got {value!r}")
    return value


def validate_sample(n: object, burn: object = 0) -> tuple[int, int]:
    """Validate requested and burn-in sample sizes."""
    return (
        validate_int("n", n, minimum=1),
        validate_int("burn", burn, minimum=0),
    )


def validate_order(name: str, value: object, *, length: int) -> tuple[int, ...]:
    """Validate a fixed-length tuple of nonnegative integer model orders."""
    if not isinstance(value, tuple) or len(value) != length:
        raise ValueError(f"{name} must be a tuple of length {length}, got {value!r}")
    return tuple(
        validate_int(f"{name}[{index}]", item, minimum=0)
        for index, item in enumerate(value)
    )


def normalize_coefficients(
    name: str,
    value: Real | Iterable[Real] | None,
    *,
    length: int | None = None,
    default: float | None = None,
    nonnegative: bool = False,
) -> list[float]:
    """Normalize scalar/iterable coefficients and validate shape and values."""
    if value is None:
        values = [] if length is None or default is None else [default] * length
    elif isinstance(value, bool):
        raise TypeError(f"{name} coefficients must be real numbers")
    elif isinstance(value, Real):
        values = [float(value)]
    else:
        try:
            values = list(value)
        except TypeError as exc:
            raise TypeError(f"{name} must be a real number or iterable") from exc

    if length is not None and len(values) != length:
        raise ValueError(
            f"{name} must contain exactly {length} coefficient(s), got {len(values)}"
        )

    return [
        validate_real(f"{name}[{index}]", item, nonnegative=nonnegative)
        for index, item in enumerate(values)
    ]


def validate_alpha(alpha):
    """Return a finite significance level strictly between zero and one."""
    try:
        alpha = float(alpha)
    except (TypeError, ValueError) as error:
        raise ValueError("alpha must be between 0 and 1") from error
    if not np.isfinite(alpha) or not 0.0 < alpha < 1.0:
        raise ValueError(f"alpha must be between 0 and 1, got {alpha}")
    return alpha


def optional_array(values):
    """Return a copied float array while preserving ``None``."""
    if values is None:
        return None
    return np.array(values, dtype=float, copy=True)


def validate_fit_kwargs(
    model,
    fit_kwargs,
    *,
    model_name=None,
    validate_signature=True,
):
    """Copy fit keywords and optionally validate a model ``fit`` signature."""
    if fit_kwargs is None:
        return {}
    if not isinstance(fit_kwargs, Mapping):
        raise TypeError("fit_kwargs must be a mapping or None")
    if not all(isinstance(name, str) and name for name in fit_kwargs):
        raise TypeError("fit_kwargs names must be non-empty strings")
    if not validate_signature:
        return dict(fit_kwargs)
    fit = getattr(model, "fit", None)
    if not callable(fit):
        raise TypeError("model must provide fit()")
    try:
        parameters = signature(fit).parameters.values()
    except (TypeError, ValueError) as error:
        label = type(model).__name__ if model_name is None else repr(model_name)
        raise TypeError(
            f"model {label} does not expose an inspectable fit() supporting method"
        ) from error

    parameters = tuple(parameters)
    accepts_kwargs = any(
        parameter.kind == Parameter.VAR_KEYWORD for parameter in parameters
    )
    accepted_names = {parameter.name for parameter in parameters}
    unsupported = [
        name for name in fit_kwargs if name not in accepted_names and not accepts_kwargs
    ]
    if unsupported:
        label = type(model).__name__ if model_name is None else repr(model_name)
        names = ", ".join(repr(name) for name in unsupported)
        raise TypeError(f"model {label} does not support fit keyword(s): {names}")
    return dict(fit_kwargs)


def as_1d_float(data, *, name="data"):
    """Convert input to a 1-D float array without silently flattening it."""
    values = np.asarray(data, dtype=float)
    if values.ndim != 1:
        raise ValueError(f"{name} must be 1-D, got shape {values.shape}")
    return values


def significance_stars(pvalue):
    """Return the shared significance star code for a p-value.

    ``**`` p<0.01, ``*`` p<0.05, ``.`` p<0.10, ``" "`` otherwise.
    Non-significant results return a single space so callers can append the
    code directly to a line without changing column alignment.
    """
    if pvalue < 0.01:
        return "**"
    if pvalue < 0.05:
        return "*"
    if pvalue < 0.10:
        return "."
    return " "


def _resolve_missing_rows(finite_rows, missing, *, name="data"):
    """Validate a missing-value policy and return dropped row positions."""
    if missing not in {"raise", "drop"}:
        raise ValueError("missing must be 'raise' or 'drop'")

    finite_rows = np.asarray(finite_rows, dtype=bool)
    if finite_rows.ndim != 1:
        raise ValueError("finite_rows must be one-dimensional")

    dropped_positions = tuple(
        int(position) for position in np.flatnonzero(~finite_rows)
    )
    if dropped_positions and missing == "raise":
        positions = ", ".join(str(position) for position in dropped_positions)
        raise ValueError(
            f"{name} contains non-finite values at row positions: {positions}"
        )
    return dropped_positions
