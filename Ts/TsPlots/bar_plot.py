"""Categorical / grouped bar charts sharing the TsPlots style contract.

The main entry point is :func:`plot_bar`, which draws one or more series of
bars against a set of discrete categories. Typography, palette, and axes
styling are shared with :mod:`TsPlots.ts_plot` and :mod:`TsPlots.sc_plot`
through :mod:`TsPlots.style`; boolean validation reuses
:func:`TsPlots.ts_plot._validate_bool` (which lazily delegates to
:mod:`Ts.TsUtils._validation`, keeping package import cycle-free exactly like
the other TsPlots modules).

Unlike :func:`TsPlots.ts_plot.plot_series` (whose ``bar_series`` option draws
at most one bar series per axis), :func:`plot_bar` is a dedicated bar chart:
it supports several series side by side within each category slot
(分组柱状图), stacked bars (堆叠柱状图), horizontal bars (横向柱状图),
per-bar value labels, and category tick thinning.

The bar cosmetics themselves live in the single implementation
:func:`_draw_bars` below, which both :func:`plot_bar` and
:func:`TsPlots.ts_plot.plot_series` (``bar_series``) delegate to, so the bar
style contract (edge colour, line width, alpha) stays identical everywhere.

Accepted inputs
---------------
- pandas Series    : index becomes the category labels, values become one bar
                     series (the Series name or ``"Series 1"`` labels it).
- pandas DataFrame : wide form — index = categories, each remaining column is
                     one bar series; ``x`` names a column used as category
                     labels instead of the index; ``y`` (str or list) selects
                     a subset of series columns.
                     long form — pass ``group=`` plus the category column
                     ``x=`` and the value column ``y=``; every distinct group
                     value becomes one bar series.
- dict             : ``{series_label: value_array}``; categories default to
                     0 .. n-1 unless ``x`` is given as an array of labels.
- 1D array         : single series, categories 0 .. n-1.
- 2D array         : each column is one series, categories 0 .. n-1.

Grouped layout
--------------
With ``n`` series each bar is ``bar_width / n`` wide so the whole group spans
``bar_width`` of the category slot; a single series draws bars ``bar_width``
wide (default ``0.6``, matching the 60 % auto width of
:func:`TsPlots.ts_plot.plot_series`).

Examples
--------
>>> import numpy as np, pandas as pd
>>> from Ts.TsPlots import plot_bar
>>> # Single series from a Series (index = categories)
>>> s = pd.Series([120, 150, 90], index=["东部", "中部", "西部"], name="产量")
>>> fig, ax = plot_bar(s, title="分地区产量", ytitle="产量", y_unit="万吨")
>>> # Grouped bars from a wide DataFrame
>>> df = pd.DataFrame(
...     {"2023": [120, 90, 150], "2024": [135, 95, 160]},
...     index=["东部", "中部", "西部"],
... )
>>> fig, ax = plot_bar(df, title="分年份分地区产量", grid=True)
>>> # Long form with a group column
>>> long = pd.DataFrame({
...     "地区": ["东部", "东部", "中部", "中部"],
...     "年份": ["2023", "2024", "2023", "2024"],
...     "产量": [120, 135, 90, 95],
... })
>>> fig, ax = plot_bar(long, x="地区", y="产量", group="年份")
>>> # Horizontal grouped bars with per-bar value labels
>>> fig, ax = plot_bar(df, horizontal=True, show_values=True)
>>> # Stacked bars
>>> fig, ax = plot_bar(df, stacked=True, ytitle="产量", y_unit="万吨")
"""

from __future__ import annotations

import math
from collections.abc import Mapping

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
    ANNOTATION_FONTSIZE,
    TITLE_PAD,
    AXIS_LABEL_FONTSIZE,
    BAR_EDGE_COLOR,
    ZORDER_BAR,
    REFERENCE_LINE_COLOR,
    REFERENCE_LINE_STYLE,
    REFERENCE_LINE_WIDTH,
    SHADE_COLOR,
    SHADE_ALPHA,
    draw_shade,
    draw_vlines,
    draw_hlines,
    BottomLegend,
    LEGEND_BELOW_OFFSET,
)
from .ts_plot import _validate_bool


def _draw_bars(
    ax,
    positions,
    heights,
    *,
    width,
    color,
    edge_color=BAR_EDGE_COLOR,
    edge_linewidth=0.6,
    alpha=1.0,
    label=None,
    horizontal=False,
    bottom=None,
    left=None,
    zorder=ZORDER_BAR,
    x_offset=0.0,
):
    """Draw one bar series with the single shared TsPlots bar cosmetics.

    柱绘制的唯一实现：:func:`plot_bar` 与
    :func:`TsPlots.ts_plot.plot_series` 的 ``bar_series`` 选项都经由本函数，
    保证边框、透明度、线宽等柱样式契约一致。边框默认使用浅灰
    ``BAR_EDGE_COLOR``；显式传 ``edge_color=None`` 时与柱同色。

    Parameters
    ----------
    ax : matplotlib.axes.Axes
        Target axes.
    positions : array-like
        Category positions of the bars.
    heights : array-like
        Bar lengths (heights when vertical, widths when horizontal).
    width : float
        Bar width in data units (bar height for horizontal bars).
    color : str
        Bar face colour (a named role from :mod:`TsPlots.style`).
    edge_color : str, optional
        Edge colour. Defaults to ``BAR_EDGE_COLOR`` (浅灰)；pass ``None`` to
        use the face colour instead.
    edge_linewidth : float
        Edge line width. Defaults to 0.6.
    alpha : float
        Bar opacity (0–1). Defaults to 1.0.
    label : str, optional
        Artist label used for legends.
    horizontal : bool
        Draw horizontal bars (``ax.barh``). Defaults to False.
    bottom : array-like, optional
        Vertical stack baseline (``ax.bar`` bottom).
    left : array-like, optional
        Horizontal stack baseline (``ax.barh`` left).
    zorder : float
        Artist z-order. Defaults to ``ZORDER_BAR`` so that lines drawn with
        ``ZORDER_LINE`` render in front of bars in bar-line mixed charts.
    x_offset : float
        Shift every bar along x by this amount (data units). ``plot_series``
        uses it to side-by-side several bar series at the same timestamp;
        category :func:`plot_bar` passes its own grouping and leaves it 0.

    Returns
    -------
    matplotlib.patches.Rectangle
        The first bar of the series, matching the ``plot_series`` caller
        contract of one artist per series.
    """
    edge = edge_color if edge_color is not None else color
    positions = np.asarray(positions)
    # x_offset 按“数据单位”平移柱位置。时间序列下 positions 是 datetime64，
    # x_offset 以“天”计（见 _resolve_bar_width）；分类/日期数值直接用数值偏移。
    if not x_offset:
        draw_positions = positions
    elif np.issubdtype(positions.dtype, np.datetime64):
        draw_positions = positions + np.timedelta64(round(x_offset), "D")
    else:
        draw_positions = positions.astype(float) + x_offset
    if horizontal:
        container = ax.barh(
            draw_positions,
            heights,
            height=width,
            left=left,
            color=color,
            edgecolor=edge,
            linewidth=edge_linewidth,
            alpha=alpha,
            label=label,
            zorder=zorder,
        )
    else:
        container = ax.bar(
            draw_positions,
            heights,
            width=width,
            bottom=bottom,
            color=color,
            edgecolor=edge,
            linewidth=edge_linewidth,
            alpha=alpha,
            label=label,
            zorder=zorder,
        )
    return container[0]


def _require_columns(frame, names):
    """Raise KeyError with the first missing column name, if any."""
    missing = [name for name in names if name not in frame.columns]
    if missing:
        raise KeyError(f"Column {missing[0]!r} not found in DataFrame.")


def _align_series(series, x):
    """Align named series against category labels.

    When ``x`` is given it defines the categories; otherwise all series must
    share one length and the categories default to 0 .. n-1.
    """
    if x is not None:
        categories = list(x)
        expected = len(categories)
    else:
        lengths = {len(values) for _, values in series}
        if len(lengths) != 1:
            raise ValueError(
                "All series must have the same length; pass x=... to define "
                "the category labels explicitly."
            )
        expected = next(iter(lengths))
        categories = list(range(expected))
    for label, values in series:
        if len(values) != expected:
            raise ValueError(
                f"Series {label!r} has {len(values)} values but there are "
                f"{expected} categories."
            )
    return categories, series


def _resolve_bar_input(data, x, y, group):
    """Normalize supported inputs into ``(categories, series, xlabel, ylabel)``.

    ``series`` is a list of ``(label, values_array)`` tuples preserving order.
    """
    if isinstance(data, pd.DataFrame):
        if group is not None:
            if not isinstance(x, str) or not isinstance(y, str):
                raise ValueError(
                    "For a long-form DataFrame (group=...), pass x and y as "
                    "column-name strings."
                )
            _require_columns(data, [x, y, group])
            try:
                pivoted = data.pivot(index=x, columns=group, values=y)
            except ValueError as error:
                raise ValueError(
                    f"Column {x!r} contains duplicate entries for the same "
                    "group; add a unique key or aggregate first."
                ) from error
            # Preserve first-appearance order for both groups and categories.
            group_order = list(dict.fromkeys(data[group].tolist()))
            category_order = list(dict.fromkeys(data[x].tolist()))
            pivoted = pivoted.reindex(category_order)
            series = [
                (str(g), pivoted[g].to_numpy(dtype=float))
                for g in group_order
                if g in pivoted.columns
            ]
            return category_order, series, x, y

        if x is not None:
            if not isinstance(x, str):
                raise TypeError(
                    "For a DataFrame, x must be a column-name string."
                )
            _require_columns(data, [x])
            categories = list(data[x])
            default_xlabel = x
        else:
            categories = list(data.index)
            default_xlabel = "Category"

        if y is not None:
            columns = [y] if isinstance(y, str) else list(y)
            _require_columns(data, columns)
        else:
            columns = list(data.columns)
        columns = [column for column in columns if column != x]
        if not columns:
            raise ValueError("No series columns remain to plot.")
        series = [
            (str(column), data[column].to_numpy(dtype=float))
            for column in columns
        ]
        return categories, series, default_xlabel, "Value"

    if group is not None:
        raise ValueError("group requires a DataFrame.")

    if isinstance(data, pd.Series):
        categories = list(x) if x is not None else list(data.index)
        values = data.to_numpy(dtype=float)
        if len(values) != len(categories):
            raise ValueError(
                f"There are {len(values)} values but {len(categories)} categories."
            )
        name = str(data.name) if data.name is not None else ""
        label = name if name else "Series 1"
        return categories, [(label, values)], "Category", "Value"

    if isinstance(data, Mapping):
        if y is not None:
            raise TypeError("y requires a DataFrame.")
        series = [
            (str(label), np.asarray(values, dtype=float))
            for label, values in data.items()
        ]
        if not series:
            raise ValueError("The dict contains no series to plot.")
        return (*_align_series(series, x), "Category", "Value")

    if y is not None:
        raise TypeError("y requires a DataFrame.")

    arr = np.asarray(data)
    if arr.ndim == 1:
        series = [("Series 1", arr.astype(float))]
    elif arr.ndim == 2:
        series = [
            (f"Series {i + 1}", arr[:, i].astype(float))
            for i in range(arr.shape[1])
        ]
    else:
        raise TypeError(
            f"Unsupported data type/shape: {type(data)!r}. Pass a Series, a "
            "DataFrame, a dict of series, or a 1D/2D array."
        )
    return (*_align_series(series, x), "Category", "Value")


def _category_tick_labels(categories, max_ticks):
    """Return one label per category, thinning to at most *max_ticks*."""
    count = len(categories)
    if count <= max_ticks:
        return [str(category) for category in categories]
    step = math.ceil(count / max_ticks)
    return [
        str(category) if index % step == 0 else ""
        for index, category in enumerate(categories)
    ]


def plot_bar(
    data,
    x=None,
    y=None,
    *,
    group=None,
    horizontal=False,
    stacked=False,
    labels=None,
    colors=None,
    title=None,
    xtitle=None,
    ytitle=None,
    bar_width=0.6,
    bar_edge_color=BAR_EDGE_COLOR,
    bar_edge_linewidth=0.6,
    bar_alpha=1.0,
    grid=False,
    grid_axis="y",
    ymin=None,
    show_legend=True,
    legend_labels=None,
    legend_loc=None,
    legend_bbox=None,
    legend_title=None,
    legend_cols=None,
    show_values=False,
    value_decimals=1,
    max_ticks=12,
    tick_rotation=0,
    title_loc="center",
    title_pad=TITLE_PAD,
    title_position="top",
    note=None,
    note_loc="left",
    note_prefix=None,
    hlines=None,
    hline_color=REFERENCE_LINE_COLOR,
    hline_linestyle=REFERENCE_LINE_STYLE,
    hline_linewidth=REFERENCE_LINE_WIDTH,
    vlines=None,
    vline_color=REFERENCE_LINE_COLOR,
    vline_linestyle=REFERENCE_LINE_STYLE,
    vline_linewidth=REFERENCE_LINE_WIDTH,
    shade=None,
    shade_color=SHADE_COLOR,
    shade_alpha=SHADE_ALPHA,
    x_unit=None,
    y_unit=None,
    ax=None,
):
    """Draw a categorical bar chart with the shared TsPlots styling.

    Supports one or several series of bars. Multiple series are drawn side by
    side within each category slot (grouped), stacked on top of each other
    (``stacked=True``), or laid out horizontally (``horizontal=True``) with the
    categories on the y-axis.

    Parameters
    ----------
    data : Series, DataFrame, dict, or array-like
        The data to plot. See the module docstring for the accepted shapes.
    x : str or array-like, optional
        For a DataFrame, the column name whose values become the category
        labels (overriding the index). For all other inputs, an array of
        category labels.
    y : str or list of str, optional
        For a DataFrame, the series column(s) to plot. For the long-form
        layout (``group=...``), ``y`` must name the value column.
    group : str, optional
        For a DataFrame, the column whose distinct values split the data into
        one bar series each (long form); requires ``x`` and ``y`` column names.
    horizontal : bool
        Draw horizontal bars (categories on the y-axis). Defaults to False.
    stacked : bool
        Stack the series on top of each other instead of side by side.
        Defaults to False.
    labels : sequence of str, optional
        Override the series labels (must match the number of series).
    colors : sequence of str, optional
        Override the per-series colors.
    title : str, optional
        Plot title. Defaults to None (no title).
    xtitle : str, optional
        Label for the category axis. Defaults to a data-detected label.
    ytitle : str, optional
        Label for the value axis. Defaults to a data-detected label.
    bar_width : float
        Width of the bars in category units. Defaults to 0.6 (= 60 % of a
        category slot). With ``n`` grouped series each bar is
        ``bar_width / n`` wide, so the whole group spans ``bar_width``.
    bar_edge_color : str, optional
        Bar edge colour. Defaults to ``BAR_EDGE_COLOR`` (浅灰)；pass ``None``
        to match the bar face colour.
    bar_edge_linewidth : float
        Width of the bar edges. Defaults to 0.6.
    bar_alpha : float
        Opacity of the bars (0–1). Defaults to 1.0.
    grid : bool
        Whether to show a dashed grid. Defaults to False.
    grid_axis : {"both", "x", "y"}
        Grid direction; defaults to ``"y"`` (horizontal lines) since vertical
        grid lines add little to bar charts.
    ymin : float or None
        Lower limit of the value axis (the y-axis, or the x-axis for
        ``horizontal=True``). Defaults to None (automatic, from zero).
    show_legend : bool
        Whether to display the legend. Defaults to True.
    legend_labels : sequence of str, optional
        Override the text of the legend entries.
    legend_loc : str, optional
        图例位置。**不传（默认）时图例绘制在类别轴下方、绘图区外的底部
        边距里**（与 ``plot_series`` / ``plot_scatter`` 默认一致），图注
        （``note``）紧跟其下；显式传入任意位置（如 ``"best"``、
        ``"upper left"``）则图例回到绘图区内该位置。
    legend_bbox : tuple, optional
        ``bbox_to_anchor`` for the legend, e.g. ``(1.02, 1)``. Only used when
        ``legend_loc`` is given explicitly.
    legend_title : str, optional
        Title shown above the legend entries.
    legend_cols : int, optional
        Number of columns for the legend entries.
    show_values : bool
        Annotate each bar with its value. Defaults to False.
    value_decimals : int
        Decimal places for ``show_values`` annotations. Defaults to 1.
    max_ticks : int
        Upper bound on category tick labels; denser category axes are thinned
        evenly while every bar stays drawn. Defaults to 12.
    tick_rotation : float
        Rotation (degrees) of the category tick labels. Defaults to 0.
    title_loc : str
        Title horizontal alignment: ``"center"``, ``"left"``, or ``"right"``.
    title_pad : float
        Padding between the title and the axes. Defaults to 12.
    title_position : str
        ``"top"`` (default) or ``"bottom"``.
    note : str, optional
        Free-text note placed to the figure's lower-left.
    note_loc : str
        ``"left"`` (default), ``"center"``, or ``"right"``.
    note_prefix : str, optional
        Text prepended to the note (e.g. ``"数据来源："``).
    hlines : float or list of float, optional
        Value-axis position(s) for reference lines across the value axis
        (horizontal lines in the default mode, vertical lines for
        ``horizontal=True``).
    hline_color : str, optional
        Color of the value-axis reference lines. Defaults to
        ``REFERENCE_LINE_COLOR`` (dark red).
    hline_linestyle : str, optional
        Line style of the value-axis reference lines. Defaults to ``"--"``.
    hline_linewidth : float, optional
        Width of the value-axis reference lines. Defaults to 1.5.
    vlines : float or list of float, optional
        Category-position(s) for reference lines across the category axis
        (``0`` is the first category; vertical lines in the default mode,
        horizontal lines for ``horizontal=True``).
    vline_color : str, optional
        Color of the category-axis reference lines. Defaults to
        ``REFERENCE_LINE_COLOR`` (dark red).
    vline_linestyle : str, optional
        Line style of the category-axis reference lines. Defaults to ``"--"``.
    vline_linewidth : float, optional
        Width of the category-axis reference lines. Defaults to 1.5.
    shade : tuple or list of tuple, optional
        ``(xmin, xmax)`` category-position interval(s) to shade. Only
        meaningful in the vertical (default) mode; ignored when
        ``horizontal=True``.
    shade_color : str, optional
        Fill color for shaded regions. Defaults to ``SHADE_COLOR``.
    shade_alpha : float, optional
        Opacity of shaded regions. Defaults to 0.3.
    x_unit : str, optional
        Unit label appended to the category-axis label, ``（单位：XX）``.
    y_unit : str, optional
        Unit label appended to the value-axis label, ``（单位：XX）``.
    ax : matplotlib.axes.Axes, optional
        Existing axes to draw on. If None, a new figure and axes are created.

    Returns
    -------
    fig : matplotlib.figure.Figure
    ax : matplotlib.axes.Axes

    Examples
    --------
    >>> import pandas as pd
    >>> from Ts.TsPlots import plot_bar
    >>> df = pd.DataFrame(
    ...     {"2023": [120, 90, 150], "2024": [135, 95, 160]},
    ...     index=["东部", "中部", "西部"],
    ... )
    >>> fig, ax = plot_bar(df, title="产量", grid=True)
    >>> len(ax.patches)
    6
    >>> fig, ax = plot_bar(df, stacked=True, show_values=True)
    >>> fig, ax = plot_bar(df, horizontal=True, show_legend=True)
    """
    horizontal = _validate_bool("horizontal", horizontal)
    stacked = _validate_bool("stacked", stacked)
    grid = _validate_bool("grid", grid)
    show_legend = _validate_bool("show_legend", show_legend)
    show_values = _validate_bool("show_values", show_values)
    bar_width = _validate_positive_step("bar_width", bar_width)
    max_ticks = _validate_max_ticks(max_ticks)

    categories, series, default_xlabel, default_ylabel = _resolve_bar_input(
        data, x, y, group
    )
    if not categories:
        raise ValueError("No categories to plot.")
    colors = _resolve_colors(colors, len(series))
    if labels is not None:
        labels = _validate_label_count("labels", labels, len(series))
        series = [
            (labels[i], values) for i, (_, values) in enumerate(series)
        ]

    _ensure_fonts()
    ctx = FigureLifecycle(ax=ax)
    fig, ax = ctx.fig, ctx.ax

    # Category-position reference shading (vertical mode only).
    if not horizontal:
        draw_shade(ax, shade, shade_color, shade_alpha)
    # Reference lines: hlines sits on the value axis, vlines on the category
    # axis; the helper names follow the vertical orientation, so swap the
    # helpers in horizontal mode.
    if horizontal:
        draw_vlines(ax, hlines, hline_color, hline_linestyle, hline_linewidth)
        draw_hlines(ax, vlines, vline_color, vline_linestyle, vline_linewidth)
    else:
        draw_hlines(ax, hlines, hline_color, hline_linestyle, hline_linewidth)
        draw_vlines(ax, vlines, vline_color, vline_linestyle, vline_linewidth)

    n_categories = len(categories)
    n_series = len(series)
    positions = np.arange(n_categories, dtype=float)
    width = bar_width if stacked else bar_width / n_series
    offsets = (
        np.zeros(n_series)
        if stacked
        else (np.arange(n_series) - (n_series - 1) / 2.0) * width
    )

    bottoms = np.zeros(n_categories)  # cumulative stack height
    annotations = []
    for index, (label, values) in enumerate(series):
        color = (
            colors[index]
            if colors is not None
            else DEFAULT_PALETTE[index % len(DEFAULT_PALETTE)]
        )
        finite = np.nan_to_num(values, nan=0.0)
        anchor = positions + offsets[index]
        if horizontal:
            if stacked:
                _draw_bars(
                    ax,
                    anchor,
                    finite,
                    width=width,
                    color=color,
                    edge_color=bar_edge_color,
                    edge_linewidth=bar_edge_linewidth,
                    alpha=bar_alpha,
                    label=label,
                    horizontal=True,
                    left=bottoms.copy(),
                    zorder=ZORDER_BAR,
                )
            else:
                _draw_bars(
                    ax,
                    anchor,
                    finite,
                    width=width,
                    color=color,
                    edge_color=bar_edge_color,
                    edge_linewidth=bar_edge_linewidth,
                    alpha=bar_alpha,
                    label=label,
                    horizontal=True,
                    zorder=ZORDER_BAR,
                )
            if show_values:
                ends = bottoms + finite
                for j, value in enumerate(values):
                    if np.isfinite(value):
                        annotations.append(
                            (anchor[j], ends[j], value, color)
                        )
        else:
            if stacked:
                _draw_bars(
                    ax,
                    anchor,
                    finite,
                    width=width,
                    color=color,
                    edge_color=bar_edge_color,
                    edge_linewidth=bar_edge_linewidth,
                    alpha=bar_alpha,
                    label=label,
                    bottom=bottoms.copy(),
                    zorder=ZORDER_BAR,
                )
            else:
                _draw_bars(
                    ax,
                    anchor,
                    finite,
                    width=width,
                    color=color,
                    edge_color=bar_edge_color,
                    edge_linewidth=bar_edge_linewidth,
                    alpha=bar_alpha,
                    label=label,
                    zorder=ZORDER_BAR,
                )
            if show_values:
                tops = bottoms + finite
                for j, value in enumerate(values):
                    if np.isfinite(value):
                        annotations.append(
                            (anchor[j], tops[j], value, color)
                        )
        if stacked:
            bottoms = bottoms + finite

    # Category tick labels, thinned when there are too many of them.
    tick_labels = _category_tick_labels(categories, max_ticks)
    if horizontal:
        ax.set_yticks(positions)
        ax.set_yticklabels(tick_labels)
        for label in ax.get_yticklabels():
            label.set_rotation(tick_rotation)
    else:
        ax.set_xticks(positions)
        ax.set_xticklabels(tick_labels)
        for label in ax.get_xticklabels():
            label.set_rotation(tick_rotation)

    # Keep the first and last bars inside the plot even for wide bars.
    pad = max(0.5, bar_width / 2 + 0.05)
    if horizontal:
        ax.set_ylim(-pad, n_categories - 1 + pad)
        if ymin is not None:
            ax.set_xlim(left=ymin)
    else:
        ax.set_xlim(-pad, n_categories - 1 + pad)
        if ymin is not None:
            ax.set_ylim(bottom=ymin)

    if show_values:
        fmt = f".{int(value_decimals)}f"
        for cat_position, value_end, value, color in annotations:
            if horizontal:
                ax.annotate(
                    f"{value:{fmt}}",
                    xy=(value_end, cat_position),
                    xytext=(6, 0) if value >= 0 else (-6, 0),
                    textcoords="offset points",
                    ha="left" if value >= 0 else "right",
                    va="center",
                    fontsize=ANNOTATION_FONTSIZE,
                    color=color,
                )
            else:
                ax.annotate(
                    f"{value:{fmt}}",
                    xy=(cat_position, value_end),
                    xytext=(0, 6) if value >= 0 else (0, -6),
                    textcoords="offset points",
                    ha="center",
                    va="bottom" if value >= 0 else "top",
                    fontsize=ANNOTATION_FONTSIZE,
                    color=color,
                )

    ax.set_xlabel(
        xtitle if xtitle is not None else default_xlabel,
        fontsize=AXIS_LABEL_FONTSIZE,
    )
    ax.set_ylabel(
        ytitle if ytitle is not None else default_ylabel,
        fontsize=AXIS_LABEL_FONTSIZE,
    )

    bottom_legend = None
    if show_legend and legend_loc is None and legend_bbox is None:
        handles, auto_labels = ax.get_legend_handles_labels()
        if handles:
            legend_texts = (
                _validate_label_count(
                    "legend_labels", legend_labels, len(handles)
                )
                if legend_labels is not None
                else auto_labels
            )
            bottom_legend = BottomLegend(
                handles,
                legend_texts,
                below_offset=LEGEND_BELOW_OFFSET,
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
        show_legend=show_legend,
        legend_labels=legend_labels,
        legend_loc=legend_loc or "best",
        legend_bbox=legend_bbox,
        legend_title=legend_title,
        legend_cols=legend_cols,
        unit=y_unit,
        x_unit=x_unit,
        bottom_legend=bottom_legend,
    )

    return fig, ax
