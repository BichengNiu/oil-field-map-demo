"""Reusable plotting utilities for time series visualization.

The main entry point is :func:`plot_series`, which draws an arbitrary number
of series. Styling cycles per series: even-indexed series are drawn as solid
lines with filled circles, odd-indexed series as dashed lines with hollow
circles, with colors from the shared default colour template. The template is
a single source of truth in :mod:`TsPlots.style`; its main colours are
black / dark blue / gray / dark red.

Accepted inputs
---------------
- pandas DataFrame : each column becomes a series. The time axis is the index
  by default, or a column named via ``x``.
- pandas Series    : a single series indexed by its index.
- dict             : ``{label: values}`` for multiple named series.
- 2D array         : each column becomes a series.
- 1D array         : a single series.

Examples
--------
>>> import numpy as np, pandas as pd
>>> from Ts.TsPlots import plot_series
>>> # DataFrame, index as time
>>> df = pd.DataFrame({"a": [1, 2, 3], "b": [3, 2, 1]}, index=[2000, 2001, 2002])
>>> fig, axes = plot_series(df)
>>> # DataFrame, a column as the time variable
>>> df2 = pd.DataFrame({"year": [2000, 2001, 2002], "a": [1, 2, 3], "b": [3, 2, 1]})
>>> fig, axes = plot_series(df2, x="year")
>>> # Overlay named series; large scale gaps automatically create more y-axes
>>> fig, ax = plot_series(
...     {
...         "rate": [1, 2, 3],
...         "level": [1000, 2000, 3000],
...         "population": [1_000_000, 2_000_000, 3_000_000],
...     },
...     facet=False,
... )
>>> right_ax = ax.right_ax
>>> all_right_axes = ax.extra_y_axes
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.ticker import MaxNLocator, MultipleLocator
import numpy as np
import pandas as pd

from .style import (
    _ensure_fonts,
    FigureLifecycle,
    _resolve_colors,
    _validate_label_count,
    _validate_max_ticks,
    _validate_positive_step,
    DEFAULT_PALETTE,
    DEFAULT_LINESTYLES,
    DEFAULT_MARKERS,
    AXIS_GRAY,
    AXIS_TEXT_GRAY,
    WHITE,
    ANNOTATION_FONTSIZE,
    YEAR_RULER_FONTSIZE,
    YEAR_RULER_TICK_PAD,
    PANEL_TITLE_PAD,
    TIGHT_PAD,
    FIGSIZE,
    AXIS_LABEL_FONTSIZE,
    BAR_EDGE_COLOR,
    ZORDER_LINE,
    REFERENCE_LINE_COLOR,
    REFERENCE_LINE_STYLE,
    REFERENCE_LINE_WIDTH,
    SHADE_COLOR,
    SHADE_ALPHA,
    style_axes,
    draw_unit_label,
    place_ylabel_at_top,
    place_left_title_right_of_ylabel,
    draw_note_and_bottom_title,
    draw_suptitle,
    draw_legend,
    draw_shade,
    draw_hlines,
    draw_vlines,
    BottomLegend,
    LEGEND_BELOW_OFFSET,
    LEGEND_BELOW_YEAR_RULER_OFFSET,
)


def _apply_year_ruler_ticks(
    ax,
    x_values,
    max_ticks: int = 12,
    monthly_ticks: bool = False,
) -> None:
    """Draw strict month ticks with a year ruler under the x-axis.

    Only tick months that are multiples of three and that actually occur in
    the data (labels are the bare month like ``3月``, not rotated). Below the
    axis, a horizontal ruler spans each calendar year that appears in the
    data, with the year label centred on the ruler. The x-limits are padded
    ten days on both sides so the first and last bars/lines are not clipped.

    Parameters
    ----------
    ax : matplotlib.axes.Axes
    x_values : array-like
        The x data (datetime-like).
    max_ticks : int
        Upper bound on the number of month ticks. The default interval of
        three months is widened when the data span would exceed this bound.
    monthly_ticks : bool
        Whether to label every month present in the data instead of using the
        default quarterly month ticks.
    """
    periods = (
        pd.PeriodIndex(pd.to_datetime(x_values), freq="M")
        .unique()
        .sort_values()
    )
    if periods.empty:
        return

    if monthly_ticks:
        tick_periods = periods
    else:
        interval = 3 * max(
            1, int(np.ceil(len(periods) / 3 / max_ticks))
        )
        tick_periods = periods[periods.month % interval == 0]
    tick_dates = tick_periods.to_timestamp(how="end").normalize()
    ax.set_xticks(tick_dates)
    ax.set_xticklabels(
        [f"{period.month}月" for period in tick_periods],
        rotation=0,
        ha="center",
        fontsize=YEAR_RULER_FONTSIZE,
    )
    ax.tick_params(axis="x", pad=YEAR_RULER_TICK_PAD)

    year_line_y = -0.18
    cap_height = 0.018
    xaxis_transform = ax.get_xaxis_transform()
    for year in periods.year.unique():
        year_periods = periods[periods.year == year]
        start_date = year_periods[0].to_timestamp(how="end").normalize()
        end_date = year_periods[-1].to_timestamp(how="end").normalize()
        middle_date = start_date + (end_date - start_date) / 2
        ax.hlines(
            year_line_y,
            start_date,
            end_date,
            color=AXIS_GRAY,
            linewidth=0.8,
            transform=xaxis_transform,
            clip_on=False,
        )
        ax.vlines(
            [start_date, end_date],
            year_line_y - cap_height,
            year_line_y + cap_height,
            color=AXIS_GRAY,
            linewidth=0.8,
            transform=xaxis_transform,
            clip_on=False,
        )
        ax.text(
            middle_date,
            year_line_y,
            f" {year}年 ",
            ha="center",
            va="center",
            fontsize=YEAR_RULER_FONTSIZE,
            color=AXIS_TEXT_GRAY,
            backgroundcolor=WHITE,
            transform=xaxis_transform,
            clip_on=False,
        )
    first_date = periods[0].to_timestamp(how="start").normalize()
    last_date = periods[-1].to_timestamp(how="end").normalize()
    margin = timedelta(days=10)
    ax.set_xlim(
        first_date.to_pydatetime() - margin,
        last_date.to_pydatetime() + margin,
    )


def _resolve_bar_width(x_values, bar_width) -> float:
    """Return the bar width; auto-sizes to 60% of the median x spacing."""
    if bar_width is not None:
        return float(bar_width)
    try:
        if np.issubdtype(np.asarray(x_values).dtype, np.datetime64):
            diffs = np.diff(
                np.sort(np.asarray(pd.to_datetime(x_values), dtype="datetime64[ns]"))
            )
            steps = diffs / np.timedelta64(1, "D")
        else:
            diffs = np.diff(np.sort(np.asarray(x_values, dtype=float)))
            steps = diffs
    except (TypeError, ValueError):
        return 1.0
    step = float(np.median(steps)) if steps.size else 1.0
    return 0.6 * max(step, 1e-9)


def _clip_vlines_to_data(vlines, x_values):
    """Drop vline positions that fall outside the plotted data range."""
    if vlines is None:
        return None
    positions = (
        list(vlines)
        if isinstance(vlines, (list, tuple, np.ndarray))
        else [vlines]
    )
    x_array = np.asarray(x_values)
    is_datetime = np.issubdtype(x_array.dtype, np.datetime64) or (
        x_array.size and isinstance(x_array[0], (date, datetime))
    )
    try:
        if is_datetime:
            x_nums = np.asarray(mdates.date2num(x_values), dtype=float)
        else:
            x_nums = np.asarray(x_values, dtype=float)
    except (TypeError, ValueError):
        return positions
    if not np.isfinite(x_nums).any():
        return positions
    data_min, data_max = float(np.nanmin(x_nums)), float(np.nanmax(x_nums))
    clipped = []
    for position in positions:
        # matplotlib 3.11 的 date2num 不接受纯字符串（0-d 数组报错），
        # 先统一转成 Timestamp 再转换。
        if isinstance(position, str):
            try:
                position = pd.to_datetime(position)
            except (ValueError, TypeError):
                clipped.append(position)
                continue
        if isinstance(
            position,
            (date, datetime, np.datetime64),
        ):
            try:
                value = float(mdates.date2num(position))
            except (TypeError, ValueError):
                clipped.append(position)
                continue
        else:
            try:
                value = float(position)
            except (TypeError, ValueError):
                clipped.append(position)
                continue
        if not np.isfinite(value) or data_min <= value <= data_max:
            clipped.append(position)
    return clipped


def _resolve_input(data, x, y) -> tuple[np.ndarray, dict, str]:
    """Normalize supported inputs into (x_values, series_dict, default_xlabel).

    series_dict maps label -> values, preserving order.
    """
    if isinstance(data, pd.DataFrame):
        if x is None:
            x_values = data.index.to_numpy()
            default_xlabel = data.index.name or "Time"
            cols = list(data.columns)
        elif isinstance(x, str):
            if x not in data.columns:
                raise KeyError(f"Column {x!r} not found in DataFrame.")
            x_values = data[x].to_numpy()
            default_xlabel = x
            cols = [c for c in data.columns if c != x]
        else:
            x_values = np.asarray(x)
            default_xlabel = "Time"
            cols = list(data.columns)

        if y is not None:
            cols = [y] if isinstance(y, str) else list(y)

        series = {str(c): data[c].to_numpy() for c in cols}
        return x_values, series, default_xlabel

    if isinstance(data, pd.Series):
        x_values = np.asarray(x) if x is not None else data.index.to_numpy()
        default_xlabel = "Time" if x is not None else (data.index.name or "Time")
        label = data.name if data.name is not None else "Series 1"
        return x_values, {str(label): data.to_numpy()}, default_xlabel

    if isinstance(data, dict):
        series = {str(k): np.asarray(v) for k, v in data.items()}
        first_len = len(next(iter(series.values())))
        x_values = np.asarray(x) if x is not None else np.arange(first_len)
        return x_values, series, "Time"

    arr = np.asarray(data)
    if arr.ndim == 1:
        x_values = np.asarray(x) if x is not None else np.arange(len(arr))
        return x_values, {"Series 1": arr}, "Time"
    if arr.ndim == 2:
        n_rows, n_cols = arr.shape
        x_values = np.asarray(x) if x is not None else np.arange(n_rows)
        series = {f"Series {i + 1}": arr[:, i] for i in range(n_cols)}
        return x_values, series, "Time"

    raise TypeError(f"Unsupported data type: {type(data)!r}")


def _validate_bool(name: str, value) -> bool:
    """Return a real boolean or reject ambiguous truthy/falsy values."""
    from Ts.TsUtils._validation import validate_bool

    return validate_bool(name, value)


def _robust_scale(values) -> float | None:
    """Estimate a series magnitude without being dominated by one outlier."""
    try:
        array = np.asarray(values, dtype=float).reshape(-1)
    except (TypeError, ValueError):
        return None
    finite = array[np.isfinite(array)]
    if finite.size == 0:
        return None
    q05, q95 = np.percentile(finite, [5, 95])
    magnitude = float(np.percentile(np.abs(finite), 95))
    scale = max(magnitude, float(q95 - q05))
    return scale if np.isfinite(scale) and scale > 0 else None


def _manual_axis_groups(
    series: dict,
    axis_groups,
    max_y_axes: int,
) -> list[list[str]]:
    """Validate and order an explicit ``series label -> group id`` mapping."""
    if not isinstance(axis_groups, Mapping):
        raise TypeError("axis_groups must be a mapping")

    series_labels = list(series)
    if set(axis_groups) != set(series_labels):
        missing = sorted(set(series_labels) - set(axis_groups))
        unknown = sorted(set(axis_groups) - set(series_labels))
        raise ValueError(
            "axis_groups labels must exactly match the plotted series; "
            f"missing={missing}, unknown={unknown}"
        )

    grouped: dict[object, list[str]] = {}
    for label in series_labels:
        group_id = axis_groups[label]
        try:
            hash(group_id)
        except TypeError as error:
            raise TypeError("axis_groups values must be hashable") from error
        grouped.setdefault(group_id, []).append(label)

    groups = list(grouped.values())
    if len(groups) > max_y_axes:
        raise ValueError(
            f"axis_groups defines {len(groups)} groups but max_y_axes is {max_y_axes}"
        )
    return groups


def _merge_closest_scale_groups(
    groups: list[dict],
    max_y_axes: int,
) -> list[dict]:
    """Merge neighboring scale groups at their smallest remaining gap."""
    while len(groups) > max_y_axes:
        ratios = [
            groups[index + 1]["scales"][0] / groups[index]["scales"][-1]
            for index in range(len(groups) - 1)
        ]
        merge_index = int(np.argmin(ratios))
        groups[merge_index]["labels"].extend(groups[merge_index + 1]["labels"])
        groups[merge_index]["scales"].extend(groups[merge_index + 1]["scales"])
        del groups[merge_index + 1]
    return groups


def _automatic_axis_groups(
    series: dict,
    threshold: float,
    max_y_axes: int,
) -> list[list[str]]:
    """Group adjacent robust scales, preserving the first series on the left."""
    series_labels = list(series)
    scaled = [
        (label, scale)
        for label, values in series.items()
        if (scale := _robust_scale(values)) is not None
    ]
    if len(scaled) < 2 or max_y_axes == 1:
        return [series_labels]

    scaled.sort(key=lambda item: item[1])
    groups = [{"labels": [scaled[0][0]], "scales": [scaled[0][1]]}]
    for label, scale in scaled[1:]:
        previous_scale = groups[-1]["scales"][-1]
        if scale / previous_scale < threshold:
            groups[-1]["labels"].append(label)
            groups[-1]["scales"].append(scale)
        else:
            groups.append({"labels": [label], "scales": [scale]})

    groups = _merge_closest_scale_groups(groups, max_y_axes)

    scaled_labels = {label for label, _scale in scaled}
    unscaled_labels = [label for label in series_labels if label not in scaled_labels]
    if unscaled_labels:
        groups[0]["labels"].extend(unscaled_labels)

    order = {label: index for index, label in enumerate(series_labels)}
    resolved = [sorted(group["labels"], key=order.get) for group in groups]
    primary_index = next(
        index for index, labels in enumerate(resolved) if series_labels[0] in labels
    )
    return [
        resolved[primary_index],
        *resolved[:primary_index],
        *resolved[primary_index + 1 :],
    ]


def _manual_second_third_groups(
    series: dict,
    *,
    second_axis_vars,
    third_axis_vars,
) -> list[list[str]]:
    """Build explicit first/second/third axis groups.

    ``second_axis_vars`` / ``third_axis_vars`` name the series to draw on
    the second (inner right) and third (outer right) axes; everything else
    stays on the first (left) axis. Empty groups are dropped, so passing
    no variables yields a single-axis plot.
    """
    series_labels = list(series)
    second = list(second_axis_vars or [])
    third = list(third_axis_vars or [])
    for name, labels in (("second_axis_vars", second), ("third_axis_vars", third)):
        unknown = sorted(set(labels) - set(series_labels))
        if unknown:
            raise ValueError(
                f"{name} contains unknown series: {unknown}; "
                f"available: {series_labels}"
            )
    overlap = sorted(set(second) & set(third))
    if overlap:
        raise ValueError(
            f"series cannot be on both the second and third axes: {overlap}"
        )
    first = [label for label in series_labels if label not in second and label not in third]
    groups = [first, second, third]
    return [group for group in groups if group]


def _resolve_axis_groups(
    series: dict,
    *,
    axis_groups,
    auto_dual_y: bool,
    threshold: float,
    max_y_axes: int,
    second_axis_vars=None,
    third_axis_vars=None,
) -> list[list[str]]:
    """Resolve manual groups or automatically group series by robust scale."""
    if axis_groups is not None:
        return _manual_axis_groups(series, axis_groups, max_y_axes)
    if second_axis_vars is not None or third_axis_vars is not None:
        return _manual_second_third_groups(
            series,
            second_axis_vars=second_axis_vars,
            third_axis_vars=third_axis_vars,
        )
    if len(series) < 2 or not auto_dual_y:
        return [list(series)]
    return _automatic_axis_groups(series, threshold, max_y_axes)


def _series_color(colors, index: int) -> str:
    if colors is not None:
        return colors[index]
    return DEFAULT_PALETTE[index % len(DEFAULT_PALETTE)]


def _resolve_series_styles(series_styles, series):
    """Validate and copy optional per-series drawing styles."""
    if series_styles is None:
        return {}
    if not isinstance(series_styles, Mapping):
        raise TypeError(
            "series_styles must map series labels to style mappings"
        )

    available = set(series)
    unknown = sorted(set(series_styles) - available)
    if unknown:
        raise ValueError(
            "series_styles contains unknown series labels: "
            f"{unknown}; available: {list(series)}"
        )

    allowed = {
        "color",
        "linestyle",
        "marker",
        "linewidth",
        "markersize",
        "marker_edge_width",
    }
    resolved = {}
    for label, style in series_styles.items():
        if not isinstance(style, Mapping):
            raise TypeError(
                f"series_styles[{label!r}] must be a mapping of style values"
            )
        invalid = sorted(set(style) - allowed)
        if invalid:
            raise ValueError(
                f"series_styles[{label!r}] contains unsupported styles: "
                f"{invalid}; choose from {sorted(allowed)}"
            )
        resolved[label] = dict(style)
    return resolved


def _plot_one_series(
    ax,
    x_values,
    values,
    label,
    index,
    *,
    colors,
    series_style,
    linewidth,
    markersize,
    marker_edge_width,
    show_values,
    value_decimals,
    is_bar=False,
    bar_width=None,
    bar_edge_color=None,
    bar_edge_linewidth=0.6,
    bar_alpha=1.0,
    bar_face_color=None,
    bar_x_offset=0.0,
):
    """Draw one series, either as a bar chart or as a line.

    Bar series delegate to :func:`TsPlots.bar_plot._draw_bars` — the single
    shared bar-drawing implementation — so the bar cosmetics (edge colour,
    line width, alpha) match :func:`TsPlots.bar_plot.plot_bar` exactly.
    """
    style = series_style or {}
    color = style.get("color", _series_color(colors, index))
    if is_bar:
        from .bar_plot import _draw_bars

        face_color = (
            bar_face_color if bar_face_color is not None else color
        )
        return _draw_bars(
            ax,
            x_values,
            values,
            width=bar_width,
            color=face_color,
            edge_color=bar_edge_color,
            edge_linewidth=bar_edge_linewidth,
            alpha=bar_alpha,
            label=label,
            x_offset=bar_x_offset,
        )

    linestyle = style.get(
        "linestyle", DEFAULT_LINESTYLES[index % len(DEFAULT_LINESTYLES)]
    )
    marker = style.get("marker", DEFAULT_MARKERS[index % len(DEFAULT_MARKERS)])
    effective_linewidth = style.get("linewidth", linewidth)
    effective_markersize = style.get("markersize", markersize)
    effective_marker_edge_width = style.get(
        "marker_edge_width", marker_edge_width
    )
    is_even = index % 2 == 0
    line = ax.plot(
        x_values,
        values,
        linestyle=linestyle,
        linewidth=effective_linewidth,
        marker=marker,
        markersize=effective_markersize,
        color=color,
        markerfacecolor=color if is_even else WHITE,
        markeredgecolor=color,
        markeredgewidth=effective_marker_edge_width,
        label=label,
        # 模板契约：柱线混合图默认线在柱的前面（ZORDER_LINE > ZORDER_BAR）。
        zorder=ZORDER_LINE,
    )[0]

    if not show_values:
        return line

    fmt = f".{value_decimals}f"
    for point_index, (x_value, y_value) in enumerate(
        zip(x_values, values, strict=False)
    ):
        # 相邻标注交替上/下错开：密集数据下避免挤在一起。
        if point_index % 2 == 0:
            y_offset, vertical_alignment = -(effective_markersize + 12), "top"
        else:
            y_offset, vertical_alignment = effective_markersize + 6, "bottom"
        ax.annotate(
            f"{y_value:{fmt}}",
            xy=(x_value, y_value),
            xytext=(0, y_offset),
            textcoords="offset points",
            ha="center",
            va=vertical_alignment,
            fontsize=ANNOTATION_FONTSIZE,
            color=color,
        )
    return line


def _configure_x_axis(
    ax,
    x_values,
    *,
    max_ticks,
    year_ruler=False,
    monthly_ticks=False,
) -> None:
    """Apply datetime or numeric tick selection to one axes."""
    x_array = np.asarray(x_values)
    is_datetime = np.issubdtype(x_array.dtype, np.datetime64) or (
        pd.api.types.is_datetime64_any_dtype(x_array)
    )
    is_numeric = np.issubdtype(x_array.dtype, np.number)

    if is_datetime and year_ruler:
        _apply_year_ruler_ticks(
            ax,
            x_values,
            max_ticks=max_ticks,
            monthly_ticks=monthly_ticks,
        )
    elif is_numeric:
        ax.xaxis.set_major_locator(MaxNLocator(nbins=max_ticks))


def _configure_y_axis(ax, *, ylabel_count=None, ytick_count=None) -> None:
    """Apply y-axis label thinning and minor-tick density.

    ``ylabel_count`` limits the number of tick labels (major ticks are
    kept, labels are thinned evenly). ``ytick_count`` draws that many
    unlabelled minor ticks between two adjacent major ticks (0 or None
    disables minor ticks).
    """
    if ylabel_count is not None:
        ticks = list(ax.yaxis.get_major_locator()())
        if len(ticks) > ylabel_count:
            step = (len(ticks) + ylabel_count - 1) // ylabel_count
            formatter = ax.yaxis.get_major_formatter()
            # 先 set_locs 初始化 formatter（未 draw 时 ScalarFormatter 会返回空串）
            formatter.set_locs(ticks)
            ax.set_yticks(ticks)
            ax.set_yticklabels(
                [formatter(t) if i % step == 0 else "" for i, t in enumerate(ticks)]
            )
    if ytick_count:
        major = list(ax.yaxis.get_major_locator()())
        if len(major) >= 2:
            base = float(np.median(np.diff(major))) / (ytick_count + 1)
            ax.yaxis.set_minor_locator(MultipleLocator(base))


def _apply_x_minor_ticks(ax, *, xtick_count=None) -> None:
    """Draw *xtick_count* unlabelled minor ticks between major x-ticks."""
    if not xtick_count:
        return
    major = list(ax.xaxis.get_major_locator()())
    if len(major) >= 2:
        base = float(np.median(np.diff(major))) / (xtick_count + 1)
        ax.xaxis.set_minor_locator(MultipleLocator(base))


def _thin_x_labels(ax, *, count=None) -> None:
    """Thin x-axis tick labels to at most *count*, keeping every tick."""
    if count is None:
        return
    ticks = list(ax.xaxis.get_major_locator()())
    if len(ticks) <= count:
        return
    step = (len(ticks) + count - 1) // count
    formatter = ax.xaxis.get_major_formatter()
    # 先 set_locs 初始化 formatter（未 draw 时 ScalarFormatter 会返回空串）
    formatter.set_locs(ticks)
    ax.set_xticks(ticks)
    ax.set_xticklabels(
        [formatter(t) if i % step == 0 else "" for i, t in enumerate(ticks)]
    )


def _lift_line_axes_above_bar_axes(ax, right_axes, axis_by_label, bar_series) -> None:
    """柱线混合、柱与线分处不同坐标轴时，把“含线（非柱）”坐标轴垫到柱轴之上。

    模板契约要求线总是渲染在柱的前面。单轴柱线混合作图时这由同一坐标轴内的
    图元 zorder 保证（``ZORDER_BAR=1 < ZORDER_LINE=3``）；但当柱和线被分到
    不同坐标轴（如 ``axis_groups`` 双轴、或 ``second_axis_vars`` 多轴），
    matplotlib 的跨轴叠放**不受图元 zorder 控制**，而是由每根坐标轴的
    ``Axes.zorder``（相同 zorder 时按添加顺序，后添加的 twinx 轴绘制在上）
    决定——如果线所在轴没有垫高，柱轴会整层盖住线。

    这里把「只有线、没有柱」的坐标轴 zorder 统一垫到所有柱轴之上，并把
    被垫高坐标轴的背景 patch 设为透明，避免其白底盖住柱轴的柱形。这样
    双轴/多轴场景同样满足「线在柱前」，且不影响同一坐标轴内的既有次序
    （网格 < 柱 < 线 < 标注线）。

    参数与 ``plot_series`` 绘制阶段同名（均在作用域内）。
    """
    line_axes = {
        axis for label, axis in axis_by_label.items() if label not in bar_series
    }
    bar_axes = {
        axis for label, axis in axis_by_label.items() if label in bar_series
    }
    if not line_axes or not bar_axes:
        return
    # 只垫高“纯线”轴；柱线同轴的场景靠图元 zorder 已正确处理。
    pure_line_axes = line_axes - bar_axes
    if not pure_line_axes:
        return
    top_bar_zorder = max(axis.get_zorder() for axis in bar_axes)
    target_zorder = top_bar_zorder + 1
    for axis in pure_line_axes:
        axis.set_zorder(target_zorder)
        axis.patch.set_visible(False)


@dataclass(frozen=True)
class _SeriesPlotPlan:
    """Immutable rendering inputs resolved from the public plot contract."""

    x_values: np.ndarray
    series: dict
    default_xlabel: str
    colors: list
    series_styles: dict
    facet: bool
    sharex: bool
    sharey: bool
    facet_rows: int | None
    facet_cols: int | None
    auto_dual_y: bool
    scale_ratio_threshold: float
    max_y_axes: int
    year_ruler: bool
    monthly_ticks: bool
    grid_axis: str
    legend_cols: int | None
    grid_linewidth: float
    bar_series: tuple[str, ...]
    units: Mapping[str, str | None] | None
    legend_labels: list | None
    ytitle_position: str
    xtitle_loc: str
    axis_groups: Mapping[str, object] | None
    second_axis_vars: list[str] | None
    third_axis_vars: list[str] | None
    log_vars: list[str] | None
    vlines: object
    resolved_bar_width: float

    def axis_unit(self, axis_labels) -> str | None:
        """Return the single unit shared by an axis, if one is supplied."""
        if self.units is None:
            return None
        axis_units = {
            str(self.units[label]).strip()
            for label in axis_labels
            if label in self.units
            and self.units[label] is not None
            and str(self.units[label]).strip()
        }
        if len(axis_units) > 1:
            raise ValueError(
                "series sharing one y-axis must use the same unit; "
                f"labels={list(axis_labels)}, units={sorted(axis_units)}"
            )
        return next(iter(axis_units), None)


def _resolve_series_plot_plan(data, x, y, options) -> _SeriesPlotPlan:
    """Resolve and validate all input-dependent plot decisions before drawing."""
    if y is not None and not isinstance(data, pd.DataFrame):
        raise TypeError("y requires a DataFrame input; use x for explicit values")
    x_values, series, default_xlabel = _resolve_input(data, x, y)
    colors = _resolve_colors(options["colors"], len(series))
    series_styles = _resolve_series_styles(options["series_styles"], series)
    facet = _validate_bool("facet", options["facet"])
    sharex = _validate_bool("sharex", options["sharex"])
    sharey = _validate_bool("sharey", options["sharey"])
    facet_rows = options["facet_rows"]
    facet_cols = options["facet_cols"]
    if facet_rows is not None and (not isinstance(facet_rows, int) or facet_rows < 1):
        raise ValueError("facet_rows must be a positive integer or None")
    if facet_cols is not None and (not isinstance(facet_cols, int) or facet_cols < 1):
        raise ValueError("facet_cols must be a positive integer or None")
    auto_dual_y = _validate_bool("auto_dual_y", options["auto_dual_y"])
    scale_ratio_threshold = _validate_positive_step(
        "scale_ratio_threshold",
        options["scale_ratio_threshold"],
    )
    max_y_axes = _validate_max_ticks(options["max_y_axes"], name="max_y_axes")
    year_ruler = _validate_bool("year_ruler", options["year_ruler"])
    monthly_ticks = _validate_bool("monthly_ticks", options["monthly_ticks"])
    grid_axis = options["grid_axis"]
    if grid_axis not in ("both", "x", "y"):
        raise ValueError(
            f"grid_axis={grid_axis!r} is not valid. Choose from: 'both', 'x', 'y'"
        )
    legend_cols = options["legend_cols"]
    if legend_cols is not None and (
        not isinstance(legend_cols, int) or legend_cols < 1
    ):
        raise ValueError("legend_cols must be a positive integer or None")
    grid_linewidth = _validate_positive_step(
        "grid_linewidth",
        options["grid_linewidth"],
    )

    raw_bar_series = options["bar_series"]
    if raw_bar_series is None:
        bar_series = []
    else:
        bar_series = (
            [raw_bar_series]
            if isinstance(raw_bar_series, str)
            else list(raw_bar_series)
        )
        unknown = sorted(set(bar_series) - set(series))
        if unknown:
            raise ValueError(
                f"bar_series labels must be plotted series; unknown={unknown}"
            )

    labels = options["labels"]
    if labels is not None:
        labels = _validate_label_count("labels", labels, len(series))
        series = {labels[i]: value for i, value in enumerate(series.values())}

    units = options["units"]
    if units is not None:
        if not isinstance(units, Mapping):
            raise TypeError("units must be a mapping from series labels to units")
        unknown_units = sorted(set(units) - set(series))
        if unknown_units:
            raise ValueError(
                "units contains unknown series labels: "
                f"{unknown_units}; available: {list(series)}"
            )

    legend_labels = _validate_label_count(
        "legend_labels",
        options["legend_labels"],
        len(series),
    )
    ytitle_position = options["ytitle_position"]
    if ytitle_position not in ("top", "side"):
        raise ValueError(
            f"ytitle_position={ytitle_position!r} is not valid. "
            "Choose 'top' or 'side'."
        )
    xtitle_loc = options["xtitle_loc"]
    if xtitle_loc not in ("left", "center", "right"):
        raise ValueError(
            f"xtitle_loc={xtitle_loc!r} is not valid. "
            "Choose 'left', 'center' or 'right'."
        )

    axis_groups = options["axis_groups"]
    if axis_groups is not None and facet and len(series) >= 2:
        raise ValueError("axis_groups requires facet=False for multiple series")
    second_axis_vars = options["second_axis_vars"]
    third_axis_vars = options["third_axis_vars"]
    if (
        facet
        and len(series) >= 2
        and (second_axis_vars is not None or third_axis_vars is not None)
    ):
        raise ValueError(
            "second_axis_vars and third_axis_vars require facet=False "
            "for multiple series"
        )

    log_vars = options["log_vars"]
    if log_vars is not None:
        unknown_log_vars = sorted(set(log_vars) - set(series))
        if unknown_log_vars:
            raise ValueError(
                f"log_vars contains unknown series: {unknown_log_vars}; "
                f"available: {list(series)}"
            )

    return _SeriesPlotPlan(
        x_values=x_values,
        series=series,
        default_xlabel=default_xlabel,
        colors=colors,
        series_styles=series_styles,
        facet=facet,
        sharex=sharex,
        sharey=sharey,
        facet_rows=facet_rows,
        facet_cols=facet_cols,
        auto_dual_y=auto_dual_y,
        scale_ratio_threshold=scale_ratio_threshold,
        max_y_axes=max_y_axes,
        year_ruler=year_ruler,
        monthly_ticks=monthly_ticks,
        grid_axis=grid_axis,
        legend_cols=legend_cols,
        grid_linewidth=grid_linewidth,
        bar_series=tuple(bar_series),
        units=units,
        legend_labels=legend_labels,
        ytitle_position=ytitle_position,
        xtitle_loc=xtitle_loc,
        axis_groups=axis_groups,
        second_axis_vars=second_axis_vars,
        third_axis_vars=third_axis_vars,
        log_vars=log_vars,
        vlines=_clip_vlines_to_data(options["vlines"], x_values),
        resolved_bar_width=_resolve_bar_width(x_values, options["bar_width"]),
    )


def plot_series(
    data,
    x=None,
    y=None,
    *,
    labels=None,
    colors=None,
    title: str | None = None,
    xtitle: str | None = None,
    xtitle_loc: str = "center",
    ytitle: str | None = None,
    ytitle_position: str = "top",
    linewidth: float = 3,
    markersize: float = 7,
    marker_edge_width: float = 2.5,
    series_styles: Mapping[str, Mapping[str, object]] | None = None,
    max_ticks: int = 12,
    year_ruler: bool = False,
    monthly_ticks: bool = False,
    ymin: float | None = None,
    xmin: float | None = None,
    ytick_count: int | None = None,
    ylabel_count: int | None = None,
    xtick_count: int | None = None,
    xlabel_count: int | None = None,
    show_legend: bool = True,
    legend_labels=None,
    legend_loc: str | None = None,
    legend_bbox=None,
    legend_title: str | None = None,
    legend_cols: int | None = None,
    legend_size: float | None = None,
    title_loc: str = "center",
    title_pad: float = 12,
    title_position: str = "top",
    note: str | None = None,
    note_loc: str = "left",
    note_prefix: str | None = None,
    grid: bool = False,
    grid_axis: str = "both",
    grid_linewidth: float = 0.6,
    grid_linestyle: str = "--",
    show_values: bool = False,
    value_decimals: int = 1,
    vlines=None,
    vline_color: str = REFERENCE_LINE_COLOR,
    vline_linestyle: str = REFERENCE_LINE_STYLE,
    vline_linewidth: float = REFERENCE_LINE_WIDTH,
    hlines=None,
    hline_color: str = REFERENCE_LINE_COLOR,
    hline_linestyle: str = REFERENCE_LINE_STYLE,
    hline_linewidth: float = REFERENCE_LINE_WIDTH,
    shade=None,
    shade_color: str = SHADE_COLOR,
    shade_alpha: float = SHADE_ALPHA,
    facet: bool = True,
    sharex: bool = True,
    sharey: bool = False,
    facet_rows: int | None = None,
    facet_cols: int | None = None,
    figsize: tuple[float, float] | None = None,
    auto_dual_y: bool = True,
    scale_ratio_threshold: float = 10.0,
    axis_groups: Mapping[str, object] | None = None,
    second_axis_vars: list[str] | None = None,
    third_axis_vars: list[str] | None = None,
    second_axis_title: str | None = None,
    third_axis_title: str | None = None,
    log_vars: list[str] | None = None,
    max_y_axes: int = 3,
    ax=None,
    unit: str | None = None,
    units: Mapping[str, str | None] | None = None,
    bar_series: str | list[str] | None = None,
    bar_width: float | None = None,
    bar_edge_color: str | None = BAR_EDGE_COLOR,
    bar_edge_linewidth: float = 0.6,
    bar_alpha: float = 1.0,
    bar_face_color: str | None = None,
) -> tuple[plt.Figure, plt.Axes | np.ndarray]:
    """Plot an arbitrary number of time series with cycling styles.

    Styling cycles per series so that each added line differs in color, line
    style, and marker shape, keeping series distinguishable even in grayscale
    or black-and-white print. Even-indexed series use filled markers, odd-
    indexed series use hollow markers.

    Parameters
    ----------
    data : DataFrame, Series, dict, or array-like
        The series to plot. See module docstring for accepted shapes.
    x : str or array-like, optional
        Time variable. For a DataFrame, a string selects a column to use as
        the time axis; otherwise an array-like provides explicit x values.
        If None, the DataFrame/Series index (or a 0-based range) is used.
    y : str or sequence of str, optional
        For a DataFrame, restricts which columns to plot. Only valid for
        DataFrame input; other containers raise a TypeError.
    labels : sequence of str, optional
        Override the legend labels (must match the number of series).
    colors : sequence of str, optional
        Override the per-series colors.
    title : str, optional
        Plot title. Defaults to None (no title).
    xtitle : str, optional
        Label for the x-axis. Defaults to None (detected from data).
        Pass ``""`` to suppress the label entirely.
    xtitle_loc : {"left", "center", "right"}, default "center"
        Horizontal alignment of the x-axis label.
    ytitle : str, optional
        Label for the y-axis. **不传（默认）时轴标题只显示单位**：给出
        ``unit`` 则显示如 ``（单位：％）``，否则不显示 y 轴标题；显式传入
        自定义标题（如变量名）时使用之，有 ``unit`` 时单位仍会追加在末尾。
        该规则同样作用于右侧双轴（默认只显示单位，不再自动拼接变量名）。
    ytitle_position : {"top", "side"}, default "top"
        Placement of the y-axis title. ``"top"`` draws the title
        horizontally at the top end of the axis (T-shaped layout, the
        axis descends from the title); ``"side"`` keeps the traditional
        vertical title beside the axis. Applies to the primary y-axis,
        faceted panels, and extra (twin) y-axes alike.
    linewidth : float
        Width of every line. Defaults to 3.
    markersize : float
        Size of the markers. Defaults to 7.
    marker_edge_width : float
        Width of the marker outlines. Defaults to 2.5.
    series_styles : mapping, optional
        Optional per-series style overrides keyed by plotted series label.
        Each value may contain ``color``, ``linestyle``, ``marker``,
        ``linewidth``, ``markersize`` and ``marker_edge_width``. Missing
        values use the corresponding global argument or default style cycle.
    max_ticks : int
        Upper bound on the number of automatic x ticks. Defaults to 12.
    year_ruler : bool
        When ``True``, draw strict month ticks (only months that are multiples
        of three and that occur in the data, labelled as ``3月`` with no
        rotation) plus a year ruler below the x-axis spanning each calendar
        year in the data. The x-limits are padded ten days on both sides.
        Defaults to ``False``.
    monthly_ticks : bool
        When ``True`` together with ``year_ruler=True``, label every month
        present in the data instead of only quarterly month ticks. Defaults
        to ``False``.
    ymin : float or None
        Lower limit of the y-axis. Defaults to None (automatic); pass a float to set a fixed minimum.
    xmin : float, datetime-like, or None
        Lower limit of the x-axis. Defaults to None (automatic). Accepts a
        float for numeric axes or a datetime/Timestamp for datetime axes.
    ytick_count : int or None
        Number of **minor ticks between two adjacent major (labelled)
        ticks** on the y-axis. Defaults to None (no minor ticks). For
        example ``3`` draws three unlabelled grid lines between each pair
        of labels.
    ylabel_count : int or None
        Maximum number of y-axis tick labels to display. Defaults to None
        (label every tick). When smaller than the tick count, labels are
        thinned evenly.
    xtick_count : int or None
        Number of **minor ticks between two adjacent major (labelled)
        ticks** on the x-axis. Defaults to None (no minor ticks).
    xlabel_count : int or None
        Maximum number of x-axis tick labels to display. Defaults to None
        (label every tick). When smaller than the tick count, labels are
        thinned evenly.
    show_legend : bool
        Whether to display the legend. Defaults to ``True``.
    legend_labels : sequence of str, optional
        Override the text of the legend entries. Must match the number of
        series. **双轴（多轴）叠加图默认图例文字统一为「变量名（左轴/右轴）」
        格式**（单轴图不带括号后缀）；显式传入 ``legend_labels`` 时按原文
        使用、不加后缀。
    legend_loc : str, optional
        图例位置。**不传（默认）时图例绘制在时间轴（x 轴）下方、绘图区外的
        底部边距里**：普通 x 轴时贴在轴标签之下，``year_ruler=True`` 时贴在
        年份标尺标签之下，图注（``note``）再紧跟其下；显式传入任意位置
        （如 ``"upper left"``、``"best"``、``"lower center"``）则图例回到
        绘图区内该位置（旧默认行为）。与 ``legend_bbox`` 同时传入时同样
        按绘图区内处理。
    legend_bbox : tuple, optional
        ``bbox_to_anchor`` for the legend, e.g. ``(1.02, 1)``. Only used when
        ``legend_loc`` is given explicitly.
    legend_title : str, optional
        Title shown above the legend entries; ``None`` hides it.
    legend_cols : int, optional
        Number of columns for the legend entries; ``None`` lets
        matplotlib choose.
    legend_size : float, optional
        Legend font size in points. ``None`` automatically scales the legend
        with the physical figure size.
    title_loc : str
        Title horizontal alignment: ``"center"``, ``"left"``, or ``"right"``.
    title_pad : float
        Padding between the title and the axes. Defaults to 12.
    title_position : str
        ``"top"`` (default) or ``"bottom"``.
    note : str, optional
        Free-text note placed at the lower-left of the figure.
    note_loc : {"left", "center", "right"}
        Horizontal placement of the note. Defaults to ``"left"``.
    note_prefix : str, optional
        Text prepended to the note (e.g. ``"数据来源："``). ``None`` or an
        empty string disables the prefix.
    grid : bool
        Whether to show a grid. Defaults to False.
    grid_axis : {"both", "x", "y"}
        Which grid lines to draw when ``grid`` is True: ``"x"`` draws
        vertical lines at the x-ticks, ``"y"`` horizontal lines at the
        y-ticks, ``"both"`` draws both. Defaults to ``"both"``.
    grid_linewidth : float
        Line width of the grid lines in points. Defaults to ``0.6``.
    grid_linestyle : str
        Line style of the grid lines (any matplotlib linestyle). Defaults
        to ``"--"``.
    show_values : bool
        Annotate each data point with its numeric value. Defaults to False.
        Adjacent labels alternate above/below the line so they stay readable
        on dense data.
    value_decimals : int
        Decimal places for ``show_values`` annotations. Defaults to 1.
    vlines : float or list of float, optional
        X-axis position(s) for vertical reference lines.
    vline_color : str
        Color of vertical lines. Defaults to ``REFERENCE_LINE_COLOR`` (dark red).
    vline_linestyle : str
        Line style of vertical lines. Defaults to ``"--"``.
    vline_linewidth : float
        Width of vertical lines. Defaults to 1.5.
    hlines : float or list of float, optional
        Y-axis position(s) for horizontal reference lines.
    hline_color : str
        Color of horizontal lines. Defaults to the reference-line color.
    hline_linestyle : str
        Line style of horizontal lines. Defaults to ``"--"``.
    hline_linewidth : float
        Width of horizontal lines. Defaults to 1.5.
    shade : tuple or list of tuple, optional
        ``(xmin, xmax)`` interval(s) to shade, e.g. ``[(2008, 2009)]``.
    shade_color : str
        Fill color for shaded regions. Defaults to ``SHADE_COLOR`` (light gray).
    shade_alpha : float
        Opacity of shaded regions (0–1). Defaults to 0.3.
    facet : bool
        For two or more series, draw one vertical panel per series. Defaults
        to ``True``. A single series always uses one axes.
    sharex : bool
        Whether faceted panels share the same x-axis scale. Defaults to
        ``True``.
    sharey : bool
        Whether faceted panels share the same y-axis scale. Defaults to
        ``False``.
    facet_rows : int or None
        Number of rows in the facet grid. When only one of
        ``facet_rows`` / ``facet_cols`` is given the other adapts to fit
        every panel; when both are given unused cells are hidden. Defaults
        to None (one column, one panel per row).
    facet_cols : int or None
        Number of columns in the facet grid. Defaults to None (see
        ``facet_rows``).
    figsize : tuple of float, optional
        Figure size ``(width, height)`` in inches for the single-axes and
        faceted figures. Defaults to the package default (``(10, 5.5)``;
        faceted figures grow their height with the panel count when this
        is not given).
    auto_dual_y : bool
        When ``facet=False`` and ``axis_groups`` is not supplied,
        automatically group similar robust scales and create additional
        y-axes as needed. The name is retained for backward compatibility.
        Defaults to ``True``.
    scale_ratio_threshold : float
        Positive adjacent scale ratio that starts a new automatic axis group.
        Defaults to 10.
    axis_groups : mapping, optional
        Explicit ``{series_label: group_id}`` assignment used when
        ``facet=False``. Series with the same hashable group identifier share
        one y-axis. The mapping must contain every plotted label exactly once
        and overrides ``auto_dual_y``. Defaults to automatic scale grouping.
    second_axis_vars : list of str, optional
        Series labels to draw on the second (inner right) y-axis when
        ``facet=False``. Everything else stays on the first (left) axis.
        When supplied (or ``third_axis_vars`` is), it overrides
        ``auto_dual_y``; empty lists disable the axis. Defaults to None.
    third_axis_vars : list of str, optional
        Series labels to draw on the third (outer right) y-axis when
        ``facet=False``. A series cannot be on both the second and third
        axes. Defaults to None.
    second_axis_title : str, optional
        Custom title for the second y-axis. **不传时轴标题只显示单位**
        （``unit``），不再自动拼接该轴上的变量名；传则使用自定义标题。
        Defaults to None.
    third_axis_title : str, optional
        Custom title for the third y-axis. 语义同 ``second_axis_title``：
        不传时只显示单位。Defaults to None.
    log_vars : list of str, optional
        Series labels whose axis uses a logarithmic y-scale. The scale is
        applied to whichever axis the series is drawn on (first, second or
        third), including the corresponding faceted panel. Defaults to None
        (linear).
    max_y_axes : int
        Maximum total number of y-axes, including the primary left axes.
        Automatic groups beyond this limit are merged by the closest scale
        gap; explicit groups beyond the limit raise an error. Defaults to 3.
    ax : matplotlib.axes.Axes, optional
        Existing axes to draw on. Multi-series faceting requires ``ax=None``;
        pass ``facet=False`` to overlay multiple series on an existing axes.
    unit : str, optional
        Unit label for the y-axis, formatted as ``（单位：XX）``. **默认
        轴标题只显示单位**：不传 ``ytitle`` 时，主 y 轴与所有右侧双轴的
        标题即为 ``（单位：XX）``，不再出现变量名；传了 ``ytitle`` 或
        ``second_axis_title`` / ``third_axis_title`` 时单位追加在其后。
        Defaults to None.
    units : mapping of str to str, optional
        Per-series unit labels read from source metadata. When ``ytitle`` or
        an extra-axis title is omitted, the corresponding axis displays the
        unit of its series as a plain label. Series sharing one axis must have
        the same non-empty unit; omitted values leave that axis title blank.
        Explicit axis-title arguments take precedence. Defaults to None.
    bar_series : str or list of str, optional
        Labels of series to draw as bars instead of lines. Bars inherit their
        face colour from ``colors`` (or the palette) and are drawn on the
        axis assigned by ``axis_groups``/``auto_dual_y``; the containing axes
        is forced to start at zero. Defaults to None (all series are lines).
    bar_width : float, optional
        Bar width in data units. For datetime axes the unit is days. When
        None, the width is 60% of the median spacing between consecutive x
        values. Defaults to None.
    bar_edge_color : str, optional
        Edge colour of the bars. Defaults to ``BAR_EDGE_COLOR`` (浅灰)；
        pass ``None`` to match the bar face colour instead.
    bar_edge_linewidth : float
        Width of the bar edges. Defaults to 0.6.
    bar_alpha : float
        Opacity of the bars (0–1). Defaults to 1.0.
    bar_face_color : str, optional
        Fill colour for every bar. When set, bars use this colour instead of
        their series colour from ``colors`` (or the palette); line series are
        unaffected. Defaults to None (bars inherit their series colour).

    Returns
    -------
    fig : matplotlib.figure.Figure
    ax : matplotlib.axes.Axes or numpy.ndarray
        A single axes for a single series or overlay. Faceting returns a
        one-dimensional array of axes. In multi-axis overlay mode, the first
        secondary axes is available as ``ax.right_ax``. All
        right-side axes are available through ``ax.extra_y_axes`` and all
        axes through ``fig.axes``.

    Examples
    --------
    Plot two columns in separate panels, using the DataFrame index as time.

    >>> import pandas as pd
    >>> from Ts.TsPlots import plot_series
    >>> frame = pd.DataFrame(
    ...     {"output": [100, 104, 109], "prices": [95, 99, 103]},
    ...     index=pd.date_range("2024-01-01", periods=3, freq="YS"),
    ... )
    >>> fig, axes = plot_series(frame, title="Annual indicators")
    >>> len(axes)
    2

    Overlay differently scaled series and assign axes automatically. Manual
    ``axis_groups`` takes precedence when the grouping is substantively known.

    >>> fig, ax = plot_series(
    ...     {"rate": [1, 2, 3], "level": [1000, 2000, 3000]},
    ...     facet=False,
    ... )
    >>> len(ax.extra_y_axes)
    1
    >>> fig, ax = plot_series(
    ...     frame,
    ...     facet=False,
    ...     axis_groups={"output": "real", "prices": "real"},
    ... )
    >>> len(ax.extra_y_axes)
    0
    """
    plan = _resolve_series_plot_plan(data, x, y, locals())
    x_values = plan.x_values
    series = plan.series
    default_xlabel = plan.default_xlabel
    colors = plan.colors
    series_styles = plan.series_styles
    facet = plan.facet
    sharex = plan.sharex
    sharey = plan.sharey
    facet_rows = plan.facet_rows
    facet_cols = plan.facet_cols
    auto_dual_y = plan.auto_dual_y
    scale_ratio_threshold = plan.scale_ratio_threshold
    max_y_axes = plan.max_y_axes
    year_ruler = plan.year_ruler
    monthly_ticks = plan.monthly_ticks
    grid_axis = plan.grid_axis
    legend_cols = plan.legend_cols
    grid_linewidth = plan.grid_linewidth
    bar_series = plan.bar_series
    units = plan.units
    legend_labels = plan.legend_labels
    ytitle_position = plan.ytitle_position
    xtitle_loc = plan.xtitle_loc
    axis_groups = plan.axis_groups
    second_axis_vars = plan.second_axis_vars
    third_axis_vars = plan.third_axis_vars
    log_vars = plan.log_vars
    vlines = plan.vlines
    resolved_bar_width = plan.resolved_bar_width
    _axis_unit = plan.axis_unit

    # 时间序列叠加（非分面）场景：同一时间点上有多根柱（多个 bar_series）
    # 时，把各系列的柱按系列顺序并排错开，整组宽度仍约为一个柱位宽。
    # 单柱或柱线混合（仅一根柱）时完全不偏移，保持原行为。
    _n_bars = len(bar_series) if (not facet) else 0
    _bar_offsets = {}
    if _n_bars > 1:
        _bar_step = resolved_bar_width / _n_bars
        for _i, _lbl in enumerate(bar_series):
            _bar_offsets[_lbl] = (_i - (_n_bars - 1) / 2) * _bar_step

    def _draw_one(target_ax, label, values, index):
        """Draw reference regions and one series on *target_ax*."""
        draw_shade(target_ax, shade, shade_color, shade_alpha)
        draw_vlines(
            target_ax,
            vlines,
            vline_color,
            vline_linestyle,
            vline_linewidth,
        )
        draw_hlines(
            target_ax,
            hlines,
            hline_color,
            hline_linestyle,
            hline_linewidth,
        )
        is_bar = label in bar_series
        return _plot_one_series(
            target_ax,
            x_values,
            values,
            label,
            index,
            colors=colors,
            series_style=series_styles.get(label),
            linewidth=linewidth,
            markersize=markersize,
            marker_edge_width=marker_edge_width,
            show_values=show_values,
            value_decimals=value_decimals,
            is_bar=is_bar,
            bar_width=(
                resolved_bar_width / _n_bars if is_bar and _n_bars > 1
                else resolved_bar_width
            ),
            bar_edge_color=bar_edge_color,
            bar_edge_linewidth=bar_edge_linewidth,
            bar_alpha=bar_alpha,
            bar_face_color=bar_face_color,
            bar_x_offset=_bar_offsets.get(label, 0.0),
        )

    if facet and len(series) >= 2:
        if ax is not None:
            raise ValueError(
                "Multi-series faceting cannot draw on one existing ax; "
                "pass facet=False to overlay the series on that axes."
            )

        _ensure_fonts()
        panel_count = len(series)
        rows, cols = facet_rows, facet_cols
        if rows is None and cols is None:
            rows, cols = panel_count, 1
        elif rows is None:
            rows = -(-panel_count // cols)
        elif cols is None:
            cols = -(-panel_count // rows)
        if rows * cols < panel_count:
            raise ValueError(
                f"facet grid {rows}x{cols} cannot fit {panel_count} series"
            )
        if figsize is None:
            figsize = (FIGSIZE[0], max(FIGSIZE[1], 3.5 * rows))
        fig, grid_axes = plt.subplots(
            rows,
            cols,
            figsize=figsize,
            sharex=sharex,
            sharey=sharey,
            squeeze=False,
        )
        axes = np.asarray(list(grid_axes.ravel())[:panel_count])
        for unused in grid_axes.ravel()[panel_count:]:
            unused.set_visible(False)
        x_label = xtitle if xtitle is not None else default_xlabel
        display_labels = legend_labels or list(series)
        # 默认（未显式传 legend_loc/legend_bbox）时图例统一放到整图底部的
        # 时间轴下方；显式传位置时保留各面板内的图例。
        explicit_legend = legend_loc is not None or legend_bbox is not None
        facet_lines = []

        for index, ((label, values), panel_ax) in enumerate(
            zip(series.items(), axes, strict=True)
        ):
            facet_lines.append(_draw_one(panel_ax, label, values, index))
            if label in bar_series:
                panel_ax.set_ylim(bottom=0)
            if log_vars and label in log_vars:
                panel_ax.set_yscale("log")
            panel_ax.set_title(
                display_labels[index],
                fontsize=AXIS_LABEL_FONTSIZE,
                loc="center",
                pad=PANEL_TITLE_PAD,
            )
            # 轴标题默认只显示单位（分面各面板同理）。
            panel_unit = _axis_unit((label,))
            if ytitle is not None:
                panel_ax.set_ylabel(ytitle, fontsize=AXIS_LABEL_FONTSIZE)
                panel_unit = unit
            else:
                panel_ax.set_ylabel(
                    panel_unit
                    if panel_unit is not None
                    else f"（单位：{unit}）" if unit is not None else "",
                    fontsize=AXIS_LABEL_FONTSIZE,
                )
                panel_unit = None
            if ytitle_position == "top":
                place_ylabel_at_top(panel_ax)
            if panel_unit is not None:
                draw_unit_label(panel_ax, panel_unit, axis="y")
            if not sharex or index == len(axes) - 1:
                panel_ax.set_xlabel(
                    x_label,
                    fontsize=AXIS_LABEL_FONTSIZE,
                    loc=xtitle_loc,
                )
            _configure_x_axis(
                panel_ax,
                x_values,
                max_ticks=max_ticks,
                year_ruler=year_ruler,
                monthly_ticks=monthly_ticks,
            )
            _thin_x_labels(panel_ax, count=xlabel_count)
            _configure_y_axis(
                panel_ax,
                ylabel_count=ylabel_count,
                ytick_count=ytick_count,
            )
            _apply_x_minor_ticks(panel_ax, xtick_count=xtick_count)
            if xmin is not None:
                panel_ax.set_xlim(left=xmin)
            if ymin is not None:
                panel_ax.set_ylim(bottom=ymin)
            style_axes(
                panel_ax,
                grid=grid,
                grid_axis=grid_axis,
                grid_linewidth=grid_linewidth,
                grid_linestyle=grid_linestyle,
            )
            if show_legend and explicit_legend:
                draw_legend(
                    panel_ax,
                    legend_labels=[display_labels[index]],
                    legend_loc=legend_loc or "best",
                    legend_bbox=legend_bbox,
                    legend_title=legend_title,
                    legend_cols=legend_cols,
                    legend_size=legend_size,
                )

        if title and title_position == "top":
            title_positions = {
                "left": (0.01, "left"),
                "center": (0.5, "center"),
                "right": (0.99, "right"),
            }
            if title_loc not in title_positions:
                raise ValueError("title_loc must be 'left', 'center', or 'right'")
            title_x, title_alignment = title_positions[title_loc]
            draw_suptitle(fig, title, x=title_x, ha=title_alignment)
        tight_rect = (0, 0, 1, 0.97) if title and title_position == "top" else None
        fig.tight_layout(pad=TIGHT_PAD, rect=tight_rect)
        bottom_legend = None
        if show_legend and not explicit_legend and facet_lines:
            bottom_legend = BottomLegend(
                facet_lines,
                display_labels,
                legend_title=legend_title,
                ncol=legend_cols,
                legend_size=legend_size,
                below_offset=(
                    LEGEND_BELOW_YEAR_RULER_OFFSET if year_ruler else LEGEND_BELOW_OFFSET
                ),
            )
        if (
            bottom_legend is not None
            or note
            or (title and title_position == "bottom")
        ):
            draw_note_and_bottom_title(
                fig,
                note=note,
                title=title,
                title_position=title_position,
                note_loc=note_loc,
                note_prefix=note_prefix,
                legend=bottom_legend,
            )
        return fig, axes

    _ensure_fonts()
    ctx = FigureLifecycle(ax=ax, figsize=figsize)
    fig, ax = ctx.fig, ctx.ax

    resolved_groups = _resolve_axis_groups(
        series,
        axis_groups=axis_groups,
        auto_dual_y=auto_dual_y,
        threshold=scale_ratio_threshold,
        max_y_axes=max_y_axes,
        second_axis_vars=second_axis_vars,
        third_axis_vars=third_axis_vars,
    )
    right_axes = []
    for group_index in range(1, len(resolved_groups)):
        right_axis = ax.twinx()
        right_axis.spines["right"].set_position(
            ("axes", 1.0 + 0.12 * (group_index - 1))
        )
        right_axes.append(right_axis)

    ax.extra_y_axes = right_axes
    if right_axes:
        ax.right_ax = right_axes[0]

    axis_by_label = {
        label: ([ax, *right_axes][group_index])
        for group_index, group_labels in enumerate(resolved_groups)
        for label in group_labels
    }

    lines = []
    for index, (label, values) in enumerate(series.items()):
        target_ax = axis_by_label[label]
        lines.append(_draw_one(target_ax, label, values, index))

    if log_vars:
        for label in log_vars:
            axis_by_label[label].set_yscale("log")

    for label in bar_series:
        axis_by_label[label].set_ylim(bottom=0)

    ax.set_xlabel(
        xtitle if xtitle is not None else default_xlabel,
        fontsize=AXIS_LABEL_FONTSIZE,
        loc=xtitle_loc,
    )
    axis_units = [_axis_unit(group_labels) for group_labels in resolved_groups]
    # 轴标题默认只显示单位：不传 ytitle 时给出 unit 则标题为「（单位：XX）」，
    # 否则不显示；显式 ytitle 时保留并让 finalize 追加单位。
    if ytitle is not None:
        ax.set_ylabel(ytitle, fontsize=AXIS_LABEL_FONTSIZE)
        yunit_applied = unit
    else:
        ax.set_ylabel(
            axis_units[0]
            if axis_units[0] is not None
            else f"（单位：{unit}）" if unit is not None else "",
            fontsize=AXIS_LABEL_FONTSIZE,
        )
        yunit_applied = None  # 默认标题已含单位，避免 finalize 重复追加
    if ytitle_position == "top":
        place_ylabel_at_top(ax)

    _configure_x_axis(
        ax,
        x_values,
        max_ticks=max_ticks,
        year_ruler=year_ruler,
        monthly_ticks=monthly_ticks,
    )
    _thin_x_labels(ax, count=xlabel_count)
    _configure_y_axis(
        ax,
        ylabel_count=ylabel_count,
        ytick_count=ytick_count,
    )
    _apply_x_minor_ticks(ax, xtick_count=xtick_count)

    if xmin is not None:
        ax.set_xlim(left=xmin)

    if ymin is not None:
        for y_axis in [ax, *right_axes]:
            y_axis.set_ylim(bottom=ymin)

    # 双轴（多轴）叠加图：图例文字统一为「变量名（左轴/右轴）」。
    multi_axis = len(resolved_groups) >= 2
    axis_role = {0: "左轴", 1: "右轴", 2: "右轴2", 3: "右轴3"}
    role_by_label = {
        label: axis_role.get(group_index, f"右轴{group_index}")
        for group_index, group_labels in enumerate(resolved_groups)
        for label in group_labels
    }
    if legend_labels is not None:
        display_labels = list(legend_labels)  # 显式覆盖，不加（左轴/右轴）后缀
    elif multi_axis:
        display_labels = [f"{name}（{role_by_label[name]}）" for name in series]
    else:
        display_labels = list(series)

    right_axis_titles = {1: second_axis_title, 2: third_axis_title}
    for group_index, (_group_labels, right_axis) in enumerate(
        zip(resolved_groups[1:], right_axes, strict=True),
        start=1,
    ):
        override = right_axis_titles.get(group_index)
        if override is not None:
            right_axis.set_ylabel(override, fontsize=AXIS_LABEL_FONTSIZE)
        elif axis_units[group_index] is not None:
            right_axis.set_ylabel(
                axis_units[group_index],
                fontsize=AXIS_LABEL_FONTSIZE,
            )
        elif unit is not None:
            # 轴标题只显示单位，不再自动拼接该轴上的变量名。
            right_axis.set_ylabel(f"（单位：{unit}）", fontsize=AXIS_LABEL_FONTSIZE)
        else:
            right_axis.set_ylabel("", fontsize=AXIS_LABEL_FONTSIZE)
        if ytitle_position == "top":
            place_ylabel_at_top(right_axis)
        if override is not None and unit is not None:
            draw_unit_label(right_axis, unit, axis="y")
        style_axes(right_axis, grid=False)
        right_axis.spines["right"].set_visible(True)
        right_axis.yaxis.set_label_position("right")
        right_axis.yaxis.tick_right()

    bottom_legend = None
    # 单序列且未显式自定义图例（legend_labels）时，默认不显示图例——
    # 只有一条数据线/柱时图例冗余。多序列或显式给出图例文字则照常显示。
    single_series_plain = len(series) == 1 and legend_labels is None
    if show_legend and lines and not single_series_plain:
        if legend_loc is None and legend_bbox is None:
            # 默认：图例放在时间轴/年份标签下方（绘图区外），由
            # draw_note_and_bottom_title 在图注上方统一排版。
            bottom_legend = BottomLegend(
                lines,
                display_labels,
                legend_title=legend_title,
                ncol=legend_cols,
                legend_size=legend_size,
                below_offset=(
                    LEGEND_BELOW_YEAR_RULER_OFFSET if year_ruler else LEGEND_BELOW_OFFSET
                ),
            )
        else:
            draw_legend(
                ax,
                handles=lines,
                legend_labels=display_labels,
                legend_loc=legend_loc or "best",
                legend_bbox=legend_bbox,
                legend_title=legend_title,
                legend_cols=legend_cols,
                legend_size=legend_size,
            )

    ctx.finalize(
        title=title,
        title_position=title_position,
        title_loc=title_loc,
        title_pad=title_pad,
        note=note,
        note_loc=note_loc,
        note_prefix=note_prefix,
        grid=grid,
        grid_axis=grid_axis,
        grid_linewidth=grid_linewidth,
        grid_linestyle=grid_linestyle,
        show_legend=False,
        unit=yunit_applied,
        bottom_legend=bottom_legend,
    )

    if (
        ytitle_position == "top"
        and title
        and title_position == "top"
        and title_loc == "left"
    ):
        # 图标题靠左 + y 标题置顶：y 标题保持正对轴心，图标题移到
        # 其右侧并留出间隙，避免二者重叠。
        place_left_title_right_of_ylabel(ax, pad_points=8)

    if len(right_axes) >= 2:
        right_margin = max(0.5, 0.88 - 0.10 * (len(right_axes) - 1))
        fig.subplots_adjust(right=right_margin)

    _lift_line_axes_above_bar_axes(ax, right_axes, axis_by_label, bar_series)
    return fig, ax
