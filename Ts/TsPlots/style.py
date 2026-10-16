"""Shared styling configuration for the TsPlots package.

This module is the single source of truth for typography, colour palette,
marker/line-style cycles, and the small cosmetic helpers shared by
:mod:`TsPlots.ts_plot` and :mod:`TsPlots.sc_plot`. Importing it configures
matplotlib so **all** text — titles, axis labels, legends, tick labels,
notes, annotations — uses one unified font family: Times New Roman for Latin
glyphs plus a single CJK family (黑体族：微软雅黑 / 黑体).

Contents
--------
Constants
    ``LATIN_FONT``, ``CHINESE_FONT_CANDIDATES``, ``HEITI_FONT_CANDIDATES``,
    palette template colours ``BLACK``, ``DARK_BLUE``, ``GRAY``, ``DARK_RED``,
    ``EXTENDED_PALETTE``, the default cycle ``DEFAULT_PALETTE``, cosmetic
    roles (``INK``, ``WHITE``, ``AXIS_GRAY``, ``AXIS_TEXT_GRAY``,
    ``GRID_GRAY``, ``ANNOTATION_EDGE``, ``REFERENCE_LINE_COLOR``,
    ``SHADE_COLOR``, ``BAND_COLOR``, ``BAR_EDGE_COLOR``),
    ``DEFAULT_LINESTYLES``, ``DEFAULT_MARKERS`` plus cosmetic size constants
    (figure size, font sizes, unit colour) and the data-stacking z-order
    contract (``ZORDER_BACKGROUND`` / ``ZORDER_GRID`` / ``ZORDER_BAR`` /
    ``ZORDER_FIT`` / ``ZORDER_LINE`` / ``ZORDER_REFERENCE`` /
    ``ZORDER_HIGHLIGHT``).
Functions
    ``apply_fonts``, ``style_axes``, ``draw_shade``, ``draw_vlines``,
    ``draw_hlines``, ``draw_legend``, ``draw_unit_label``,
    ``draw_note_and_bottom_title``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import math

import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.colors import is_color_like
from matplotlib.ticker import FuncFormatter, MaxNLocator
import numpy as np

# --- Fonts -----------------------------------------------------------------
# 全包统一字体族：Latin 用 Times New Roman，CJK 用黑体族（微软雅黑 / 黑体）。
# matplotlib (>=3.6) 通过字体列表逐字形回退，Latin 走 Times、中文走黑体族；
# 图标题、轴标题、图例、刻度、图注、数值标注一律共用此字体族，仅字号按角色
# 区分。曾经「正文仿宋 / 标题黑体」的双字体族设计已废弃——业务方要求所有
# 文字字体完全一致。
LATIN_FONT = "Times New Roman"
# 优先微软雅黑（自带粗体字形，图表可读性最好），回退 SimHei。
CHINESE_FONT_CANDIDATES = ["Microsoft YaHei", "SimHei"]
# 兼容别名：旧接口名指向同一列表，避免下游按旧语义分别引用两个字体族。
HEITI_FONT_CANDIDATES = CHINESE_FONT_CANDIDATES


def apply_fonts(latin=LATIN_FONT, chinese_candidates=CHINESE_FONT_CANDIDATES):
    """Configure matplotlib so all text uses one unified font family.

    Latin glyphs render in *latin* (Times New Roman) and CJK glyphs fall back
    to the first installed family in *chinese_candidates*（黑体族：微软雅黑 /
    黑体）。图标题、轴标题、图例、刻度、图注等所有文字共用此字体族。

    Parameters
    ----------
    latin : str
        Font family used for Latin glyphs. Defaults to ``"Times New Roman"``.
    chinese_candidates : sequence of str
        Candidate CJK font family names, tried in order; the first one that is
        installed is used, otherwise the last entry is used as a fallback.

    Returns
    -------
    str
        The Chinese font family name that was actually selected.

    Examples
    --------
    >>> from Ts.TsPlots.style import apply_fonts
    >>> selected_font = apply_fonts()
    >>> isinstance(selected_font, str)
    True
    """
    available = {f.name for f in font_manager.fontManager.ttflist}
    chinese = next(
        (name for name in chinese_candidates if name in available),
        chinese_candidates[-1],
    )
    # Family fallback list: Latin first, CJK second.
    plt.rcParams["font.family"] = [latin, chinese]
    plt.rcParams["axes.unicode_minus"] = False
    # Math text in a matching serif style.
    plt.rcParams["mathtext.fontset"] = "stix"
    return chinese


# --- Lazy font initialisation ------------------------------------------------
# Fonts are not loaded at import time — _ensure_fonts() is called at the top of
# every public plotting function. This avoids front-loading the font-scan cost
# (scanning ~1800 TTF files on Windows) when all the user wants is a constant.
_fonts_initialized = False
SELECTED_CHINESE_FONT = "Microsoft YaHei"  # placeholder; replaced after first _ensure_fonts()
SELECTED_HEITI_FONT = SELECTED_CHINESE_FONT  # 同一字体族的兼容别名


def _ensure_fonts():
    """Lazy-load fonts on first call; no-op afterwards.

    Call this at the top of every public plotting function that creates or
    styles a figure (plot_series, plot_scatter, plot_acf, plot_pacf).
    """
    global _fonts_initialized, SELECTED_CHINESE_FONT, SELECTED_HEITI_FONT
    if not _fonts_initialized:
        SELECTED_CHINESE_FONT = apply_fonts(LATIN_FONT, CHINESE_FONT_CANDIDATES)
        # 单一字体族：正文与标题共用同一 CJK 家族（兼容别名同步）。
        SELECTED_HEITI_FONT = SELECTED_CHINESE_FONT
        _fonts_initialized = True


def _body_font_family():
    """Return the unified Latin/CJK font fallback used for body text.

    TsPlots 规定所有文字（含标题）共用同一字体族，仅字号区分角色；此函数
    与 :func:`_title_font_family` 返回相同列表。
    """
    _ensure_fonts()
    return [LATIN_FONT, SELECTED_CHINESE_FONT]


def _title_font_family():
    """Return the unified Latin/CJK font fallback used for titles.

    TsPlots 规定所有文字（含正文、图例、刻度）共用同一字体族，仅字号区分
    角色；此函数与 :func:`_body_font_family` 返回相同列表。
    """
    _ensure_fonts()
    return [LATIN_FONT, SELECTED_HEITI_FONT]


# --- Default colour template (single source of truth) ----------------------
# All colours used anywhere in TsPlots — and by the TsModels / TsTests /
# TsSims plot methods that reuse this style contract — must be referenced
# through the named roles below.  No bare colour literal (hex or named) is
# allowed in plotting code outside this module.
#
# Four main colours lead the default cycle: 黑 / 深蓝 / 灰 / 深红.
BLACK = "#141414"  # 黑（主色 1）
DARK_BLUE = "#1f4e79"  # 深蓝（主色 2）
GRAY = "#888888"  # 灰（主色 3）
DARK_RED = "#8b1a1a"  # 深红（主色 4）

# Derived extension colours keep the cycle at 8 entries (matching the 8-line
# / 8-marker cycles) so that five or more series stay distinguishable.  They
# were chosen to maximise the minimum pairwise colour distance against the
# four main colours.
EXTENDED_PALETTE = [
    "#4a76a8",  # steel blue / 中钢蓝
    "#b9b9b9",  # silver gray / 银灰
    "#8b5a2b",  # copper brown / 铜棕
    "#b08c44",  # golden brown / 琥珀棕
]

DEFAULT_PALETTE = [BLACK, DARK_BLUE, GRAY, DARK_RED, *EXTENDED_PALETTE]

# Cosmetic (non-series) colour roles, all derived from the template.
INK = "#000000"  # text: titles, notes, annotation labels, heatmap low-contrast text
WHITE = "#ffffff"  # hollow marker faces, annotation backgrounds, heatmap high-contrast text
AXIS_GRAY = "#555555"  # year-ruler tick lines
AXIS_TEXT_GRAY = "#333333"  # year-ruler labels
GRID_GRAY = "#999999"  # grid / zero reference lines
ANNOTATION_EDGE = "#cccccc"  # annotation-box borders
ZERO_LINE_COLOR = INK  # thin zero baseline on correlograms / response plots
REFERENCE_LINE_COLOR = DARK_RED  # reference/critical lines & key markers
SHADE_COLOR = "#d0d0d0"  # shaded regions (gray family)
BAND_COLOR = SHADE_COLOR  # confidence-band fill alias
# 柱默认边框（浅灰族）：与阴影/置信带同一灰阶，柱边默认不再与柱同色。
BAR_EDGE_COLOR = SHADE_COLOR  # default bar edge (light gray family)

# --- Z-order contract (data stacking) --------------------------------------
# 全包统一的分层角色常量：绘图模块**禁止出现裸数字 zorder**，一律引用本组
# 常量，保证任一图表（柱线混合、ACF、脉冲响应、散点、单位根、根分布）的
# 堆叠层级一致。阶梯自底向上：
#   ZORDER_BACKGROUND=0  <  ZORDER_GRID=0.5  <  ZORDER_BAR=1
#   <  ZORDER_FIT=2  <  ZORDER_LINE=3  <  ZORDER_REFERENCE=4
#   <  ZORDER_HIGHLIGHT=5
# 语义：背景填充（阴影/置信带）→ 网格线 → 柱 → 拟合/次级数据线 → 数据线/
# 散点 → 标注/临界参考线 → 最显眼的关键点高亮（如检验统计量、特征根）。
ZORDER_BACKGROUND = 0  # 阴影 / 置信带等背景填充
ZORDER_GRID = 0.5  # 网格线永远在数据（柱/线）之后
ZORDER_BAR = 1
ZORDER_FIT = 2  # 拟合线 / 次级数据线（在数据标记之下）
ZORDER_LINE = 3  # 数据线与数据散点
ZORDER_REFERENCE = 4  # 参考/标注线（vlines / hlines / 临界线 / 零值基准线）
ZORDER_HIGHLIGHT = 5  # 关键点高亮（检验统计量、特征根位置等）

# Distinct line styles so series remain distinguishable in grayscale / B&W print
DEFAULT_LINESTYLES = [
    "-",  # solid
    "--",  # dashed
    "-.",  # dash-dot
    ":",  # dotted
    (0, (3, 1, 1, 1)),  # dash-dot-dot
    (0, (5, 1)),  # long dash
    (0, (1, 1)),  # dense dots
    (0, (3, 1, 1, 1, 1, 1)),  # dash-dot-dot-dot
]

# Distinct marker shapes to reinforce B&W distinction
DEFAULT_MARKERS = ["o", "s", "^", "D", "v", "P", "X", "*"]

# Shared reference-line and shading cosmetics (single source of truth).
REFERENCE_LINE_STYLE = "--"
REFERENCE_LINE_WIDTH = 1.5
SHADE_ALPHA = 0.3
BAND_ALPHA = 0.4

# --- Cosmetic size constants ----------------------------------------------
FIGSIZE = (10, 5.5)
TITLE_FONTSIZE = 14
AXIS_LABEL_FONTSIZE = 15
TICK_LABELSIZE = 14
LEGEND_FONTSIZE = 15
# 图注与刻度/标题同字号，避免与图内其他文字比例失调。
NOTE_FONTSIZE = TICK_LABELSIZE
TIGHT_PAD = 1.5
# 标题距坐标区顶部的留白（points）。
TITLE_PAD = 12
# 分面（facet）面板标题的留白：网格内紧凑排版，故意小于整图标题留白。
PANEL_TITLE_PAD = 6
# 图内数值/点标注字号（show_values 等）。
ANNOTATION_FONTSIZE = 11
# 年度标尺（year_ruler）的刻度与年份标签字号；紧凑排版故意小于正文。
YEAR_RULER_FONTSIZE = 9
# 年度标尺月份刻度与 x 轴的间距。
YEAR_RULER_TICK_PAD = 5
#: Figure rectangle reserved for facet grids with a figure-level suptitle.
FACET_RECT = (0.0, 0.0, 1.0, 0.96)

# --- Bottom-margin legend placement -----------------------------------------
# 图例默认绘制在时间轴（x 轴）下方、绘图区外的底部边距里。锚点为图例顶部
# 相对轴坐标系原点（x 轴在 y=0）的偏移：普通 x 轴需避开刻度与轴标签（下缘
# 约 -0.13），year_ruler 还需避开年份标尺标签（下缘约 -0.195）。
LEGEND_BELOW_OFFSET = -0.17
LEGEND_BELOW_YEAR_RULER_OFFSET = -0.24


def resolve_legend_fontsize(figure, legend_size=None) -> float:
    """Resolve an explicit or figure-size-aware legend font size.

    Parameters
    ----------
    figure : matplotlib.figure.Figure
        Figure whose physical dimensions determine the automatic size.
    legend_size : float, optional
        Explicit legend font size in points. ``None`` scales the standard
        legend size with the figure area. Defaults to ``None``.
    """
    if legend_size is not None:
        try:
            resolved = float(legend_size)
        except (TypeError, ValueError) as exc:
            raise ValueError("legend_size must be a positive number or None") from exc
        if not math.isfinite(resolved) or resolved <= 0:
            raise ValueError("legend_size must be a positive number or None")
        return resolved

    width, height = figure.get_size_inches()
    reference_area = FIGSIZE[0] * FIGSIZE[1]
    figure_area = max(float(width) * float(height), 0.01)
    scale = math.sqrt(figure_area / reference_area)
    return max(8.0, min(24.0, LEGEND_FONTSIZE * scale))


class BottomLegend:
    """Describes a legend drawn in the bottom figure margin under the time axis.

    ``draw_note_and_bottom_title`` anchors the legend just below the x-axis /
    year-ruler labels, then stacks any bottom title and the note beneath it,
    reserving exactly enough bottom margin so nothing is clipped.

    Parameters
    ----------
    handles : sequence of Artist
        Legend handles.
    labels : sequence of str
        Legend entry texts (one per handle).
    legend_title : str, optional
        Title shown above the legend entries; ``None`` hides it.
    ncol : int, optional
        Number of columns. ``None`` auto-balances the entries into a
        near-square grid (``ceil(sqrt(n))`` columns)：例如 4 条 → 2×2、9 条
        → 3×3，避免条目文字过长时排成过宽的单行。
    legend_size : float, optional
        Legend font size in points. ``None`` automatically scales with the
        physical figure size.
    below_offset : float
        Anchor offset (axes fraction, negative) for the legend top edge below
        the x-axis. Defaults to ``LEGEND_BELOW_OFFSET``.
    """

    def __init__(
        self,
        handles,
        labels,
        *,
        legend_title=None,
        ncol=None,
        legend_size=None,
        below_offset=LEGEND_BELOW_OFFSET,
    ):
        self.handles = list(handles)
        self.labels = list(labels)
        self.legend_title = legend_title
        self.ncol = ncol
        self.legend_size = legend_size
        self.below_offset = below_offset


def _resolve_colors(colors, series_count):
    """Return one color per series or reject an ambiguous override."""
    if colors is None:
        return None
    return _validate_label_count("colors", colors, series_count)


def _resolve_bar_colors(color, count):
    """Return one color per response from ``None``, a single color, or a list."""
    if color is None:
        return [DEFAULT_PALETTE[index % len(DEFAULT_PALETTE)] for index in range(count)]
    if is_color_like(color):
        return [color] * count
    colors = list(color)
    if len(colors) != count:
        raise ValueError("color must contain one value per response")
    return colors


def _validate_label_count(name, values, count):
    """Return *values* as a list after enforcing one entry per series."""
    if values is None:
        return None
    if isinstance(values, str):
        raise TypeError(f"{name} must be a sequence, not a single string")
    resolved = list(values)
    if len(resolved) != count:
        raise ValueError(
            f"{name} has {len(resolved)} entries but there are {count} series"
        )
    return resolved


def _as_position_list(values):
    """Return a list of positions from a scalar, sequence, or ``None``."""
    if values is None:
        return None
    return [values] if np.isscalar(values) else list(values)


def _validate_max_ticks(value, name="max_ticks"):
    """Return *value* as int after rejecting non-positive integers."""
    if (
        isinstance(value, (bool, np.bool_))
        or not isinstance(value, (int, np.integer))
    ):
        raise TypeError(f"{name} must be an integer")
    if int(value) < 1:
        raise ValueError(f"{name} must be at least 1")
    return int(value)


def _set_lag_ticks(ax, lags, max_ticks):
    """Show every lag when there are few enough, otherwise thin to integers."""
    if len(lags) <= max_ticks:
        ax.set_xticks(lags)
    else:
        ax.xaxis.set_major_locator(MaxNLocator(nbins=max_ticks, integer=True))


def _validate_positive_step(name, value, *, integer=False):
    """Validate an optional positive tick step."""
    if value is None:
        return None
    if isinstance(value, (bool, np.bool_)):
        raise TypeError(f"{name} must be a positive number")
    if integer and not isinstance(value, (int, np.integer)):
        raise TypeError(f"{name} must be a positive integer")
    try:
        numeric = float(value)
    except (TypeError, ValueError) as error:
        raise TypeError(f"{name} must be a positive number") from error
    if not np.isfinite(numeric) or numeric <= 0:
        raise ValueError(f"{name} must be positive")
    return int(value) if integer else numeric


def style_axes(
    ax,
    *,
    grid=False,
    grid_axis="both",
    grid_linewidth=0.6,
    grid_linestyle="--",
    tick_labelsize=TICK_LABELSIZE,
):
    """Apply the shared axes cosmetics: hide the top and right spines, set the
    tick label size, and optionally draw a dashed grid on one or both axes.

    Parameters
    ----------
    ax : matplotlib.axes.Axes
        Axes to style.
    grid : bool
        Whether to show a grid. Defaults to ``False``.
    grid_axis : {"both", "x", "y"}
        Which grid lines to draw: ``"x"`` draws vertical lines at the
        x-ticks (纵网格), ``"y"`` horizontal lines at the y-ticks
        (横网格), ``"both"`` draws both. Only used when ``grid`` is
        ``True``. Defaults to ``"both"``.
    grid_linewidth : float
        Line width of the grid lines, in points. Defaults to ``0.6``.
    grid_linestyle : str
        Line style of the grid lines (any matplotlib linestyle, e.g.
        ``"--"``, ``":"``, ``"-."``, ``"-"``). Defaults to ``"--"``.
    tick_labelsize : float
        Font size of the tick labels. Defaults to ``14``.

    Returns
    -------
    None

    Examples
    --------
    >>> import matplotlib.pyplot as plt
    >>> from Ts.TsPlots.style import style_axes
    >>> fig, ax = plt.subplots()
    >>> style_axes(ax, grid=True)
    >>> ax.spines["top"].get_visible()
    False
    """
    body_family = _body_font_family()
    title_family = _title_font_family()

    # Axes may have been created before TsPlots initialised its fonts (for
    # example, the three-panel model diagnostics figure).  Updating rcParams
    # alone does not retrofit those existing Text artists, so apply the
    # resolved families explicitly.
    ax.xaxis.label.set_fontfamily(body_family)
    ax.yaxis.label.set_fontfamily(body_family)
    for label in (*ax.get_xticklabels(), *ax.get_yticklabels()):
        label.set_fontfamily(body_family)
    for title in (
        ax.title,
        getattr(ax, "_left_title", None),
        getattr(ax, "_right_title", None),
    ):
        if title is not None:
            title.set_fontfamily(title_family)

    if grid:
        ax.grid(
            axis=grid_axis,
            alpha=0.4,
            linestyle=grid_linestyle,
            linewidth=grid_linewidth,
            # 模板契约：网格永远在数据（柱/线）之后（ZORDER_GRID < ZORDER_BAR）。
            zorder=ZORDER_GRID,
        )
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(axis="both", labelsize=tick_labelsize)


def draw_shade(ax, shade, color, alpha):
    """Draw one or more shaded vertical regions behind the data.

    Parameters
    ----------
    ax : matplotlib.axes.Axes
    shade : tuple or list of tuple
        A single ``(xmin, xmax)`` interval or a list of such intervals.
    color : str
        Fill colour of the shaded regions.
    alpha : float
        Opacity of the shaded regions (0–1).
    """
    if shade is None:
        return
    regions = [shade] if isinstance(shade, tuple) else list(shade)
    for xmin, xmax in regions:
        ax.axvspan(
            xmin,
            xmax,
            color=color,
            alpha=alpha,
            linewidth=0,
            zorder=ZORDER_BACKGROUND,
        )


def draw_vlines(ax, vlines, color, linestyle, linewidth):
    """Draw one or more vertical reference lines.

    Parameters
    ----------
    ax : matplotlib.axes.Axes
    vlines : float or list of float
        One or more x-axis positions at which to draw a vertical line.
    color : str
        Colour of the vertical lines.
    linestyle : str
        Line style of the vertical lines.
    linewidth : float
        Width of the vertical lines.
    """
    positions = _as_position_list(vlines)
    if positions is None:
        return
    for xpos in positions:
        ax.axvline(
            xpos,
            color=color,
            linestyle=linestyle,
            linewidth=linewidth,
            zorder=ZORDER_REFERENCE,
        )


def draw_hlines(ax, hlines, color, linestyle, linewidth):
    """Draw one or more horizontal reference lines.

    Parameters
    ----------
    ax : matplotlib.axes.Axes
    hlines : float or list of float
        One or more y-axis positions at which to draw a horizontal line.
    color : str
        Colour of the horizontal lines.
    linestyle : str
        Line style of the horizontal lines.
    linewidth : float
        Width of the horizontal lines.
    """
    positions = _as_position_list(hlines)
    if positions is None:
        return
    for ypos in positions:
        ax.axhline(
            ypos,
            color=color,
            linestyle=linestyle,
            linewidth=linewidth,
            zorder=ZORDER_REFERENCE,
        )


def draw_legend(
    ax,
    *,
    show_legend=True,
    handles=None,
    legend_labels=None,
    legend_loc="best",
    legend_bbox=None,
    fontsize=LEGEND_FONTSIZE,
    legend_title=None,
    legend_cols=None,
    legend_size=None,
):
    """Draw a frameless legend, optionally overriding the entry text.

    Parameters
    ----------
    ax : matplotlib.axes.Axes
    show_legend : bool
        Whether to display the legend at all. Defaults to ``True``.
    handles : sequence of Artist, optional
        Explicit legend handles. Defaults to the labelled artists on *ax*.
    legend_labels : sequence of str, optional
        Override the text of the legend entries. Must match the number of
        plotted handles.
    legend_loc : str
        Legend location passed to ``ax.legend(loc=...)``.
    legend_bbox : tuple, optional
        ``bbox_to_anchor`` for the legend.
    fontsize : float
        Legend font size. Defaults to ``15``（与轴标题字号一致）。
    legend_title : str, optional
        Title shown above the legend entries; ``None`` hides it.
    legend_cols : int, optional
        Number of columns for the legend entries; ``None`` lets
        matplotlib choose.
    legend_size : float, optional
        Legend font size in points. ``None`` automatically scales the legend
        with the physical figure size.
    """
    if not show_legend:
        return
    if handles is None:
        handles, auto_labels = ax.get_legend_handles_labels()
    else:
        handles = list(handles)
        # Derive labels from the artists' own ``label`` (matching matplotlib's
        # default for explicit handles) when no override is supplied.
        auto_labels = [handle.get_label() for handle in handles]
    final_labels = (
        _validate_label_count("legend_labels", legend_labels, len(handles))
        if legend_labels is not None
        else auto_labels
    )
    fontsize = resolve_legend_fontsize(ax.figure, legend_size)
    scale = fontsize / LEGEND_FONTSIZE
    ax.legend(
        handles,
        final_labels,
        frameon=False,
        fontsize=fontsize,
        markerscale=1.6 * scale,
        handlelength=2.6 * scale,
        loc=legend_loc,
        bbox_to_anchor=legend_bbox,
        title=legend_title or None,
        title_fontsize=fontsize,
        ncol=legend_cols or 1,
    )


def draw_unit_label(ax, unit, *, axis="y"):
    """Place a Chinese unit label ``（单位：XX）`` next to an axis.

    Parameters
    ----------
    ax : matplotlib.axes.Axes
    unit : str or None
        The unit text. If ``None``, nothing is drawn.
    axis : str
        ``"y"`` (default) appends the label to the existing y-axis label text.
        ``"x"`` appends it to the x-axis label text.
    """
    if unit is None:
        return
    text = f"（单位：{unit}）"
    if axis == "y":
        current = ax.get_ylabel()
        ax.set_ylabel(f"{current}{text}" if current else text)
    elif axis == "x":
        current = ax.get_xlabel()
        ax.set_xlabel(f"{current}{text}" if current else text)
    else:
        raise ValueError(f"axis={axis!r} is not valid. Choose 'x' or 'y'.")


def format_compact_y_axis(
    axis,
    *,
    unit: str | None = None,
    rules: Mapping[str, Sequence[tuple[float, float, str]]] | None = None,
) -> None:
    """Apply caller-provided compact units to a numeric y-axis.

    Parameters
    ----------
    axis : matplotlib.axes.Axes
        The y-axis to format.
    unit : str, optional
        The input unit used to select a rule. When omitted, the current
        y-axis label is used.
    rules : mapping, optional
        Mapping from input unit to descending ``(threshold, divisor,
        output_unit)`` rules. The first rule whose threshold is no greater
        than the largest absolute y-limit is selected. Tick values are
        divided by ``divisor`` and the axis label is replaced by
        ``output_unit``.

    Notes
    -----
    TsPlots does not prescribe domain-specific units. Callers can therefore
    provide rules such as ``{"笔": ((1000, 10000, "万笔"), (0, 1, "笔"))}``
    while keeping the tick formatter and axis-label update in one reusable
    implementation.
    """

    if rules is None:
        return
    input_unit = str(unit if unit is not None else axis.get_ylabel()).strip()
    candidates = rules.get(input_unit)
    if not candidates:
        return

    lower, upper = axis.get_ylim()
    maximum = max(abs(float(lower)), abs(float(upper)))
    selected = next(
        (
            (float(threshold), float(divisor), str(output_unit))
            for threshold, divisor, output_unit in candidates
            if maximum >= float(threshold)
        ),
        None,
    )
    if selected is None:
        return
    _, divisor, output_unit = selected
    if divisor <= 0:
        raise ValueError("compact y-axis divisor must be positive")

    def _format_tick(value: float, _position: int) -> str:
        scaled = value / divisor
        if abs(scaled) < 1e-12:
            scaled = 0
        return f"{scaled:.4g}"

    axis.yaxis.set_major_formatter(FuncFormatter(_format_tick))
    axis.set_ylabel(output_unit)
    axis._ts_compact_y_axis = True


def place_ylabel_at_top(ax):
    """将 y 轴标题置于轴的上端点、横排显示，并正对 y 轴（丁字布局）。

    标题横排居中在轴顶端上方：左轴正对轴心（x=0），右侧双轴正对右轴
    轴心（x=1）；轴线的顶端落在标题横笔正中，形成「丁」字。

    Parameters
    ----------
    ax : matplotlib.axes.Axes
        要调整的坐标轴；右侧双轴（twinx）同样适用。

    Notes
    -----
    仅当该轴已有 y 轴标题文本时生效；无标题的轴不做任何改动。
    """
    label = ax.yaxis.get_label()
    if not label.get_text():
        return
    label.set_rotation(0)
    label.set_verticalalignment("bottom")
    label.set_horizontalalignment("center")
    side = ax.yaxis.get_label_position()
    x = 0.0 if side == "left" else 1.0
    ax.yaxis.set_label_coords(x, 1.05)


def _draw_renderer(fig):
    """Draw with a concrete canvas before measuring text and legend extents."""
    if not callable(getattr(fig.canvas, "get_renderer", None)):
        FigureCanvasAgg(fig)
    fig.canvas.draw()
    return fig.canvas.get_renderer()


def place_left_title_right_of_ylabel(ax, *, pad_points=8):
    """把左上角图标题移到 y 轴标题（置顶横排）右侧，避免二者重叠。

    y 轴标题保持正对轴心不动；图标题左缘移动到 y 标题右缘 + 间隙
    （points）。无图标题或无 y 标题时不做任何改动。

    Parameters
    ----------
    ax : matplotlib.axes.Axes
        要调整的坐标轴（图标题已以 ``loc="left"`` 绘制在左上角）。
    pad_points : float, default 8
        图标题左缘与 y 标题右缘之间的最小间隙（points）。
    """
    title = ax._left_title
    label = ax.yaxis.get_label()
    if not title.get_text() or not label.get_text():
        return
    renderer = _draw_renderer(ax.figure)
    label_bbox = label.get_window_extent(renderer)
    gap = pad_points * ax.figure.dpi / 72
    x = ax.transAxes.inverted().transform((label_bbox.x1 + gap, 0))[0]
    title.set_position((x, title.get_position()[1]))


def draw_suptitle(
    fig,
    title,
    *,
    x=None,
    ha=None,
    fontsize=TITLE_FONTSIZE,
    fontweight="normal",
):
    """Place a figure-level title with the shared unified font family.

    TsPlots 规定所有文字共用同一字体族（Times New Roman + 黑体族，见
    :func:`_title_font_family`，与正文/图例/刻度完全一致，仅字号区分角色）。
    统一入口保证图级标题不会意外落到别的字体族。TsPlots 及其消费方
    （TsModels / TsTests / TsSims / TsUtils）的所有 ``fig.suptitle`` 调用
    都必须经由本函数。

    Parameters
    ----------
    fig : matplotlib.figure.Figure
    title : str
        Suptitle text.
    x, ha : float / str, optional
        Horizontal anchor passed through to ``fig.suptitle``.
    fontsize : float
        Title font size. Defaults to ``TITLE_FONTSIZE``.
    fontweight : str
        Title weight. 图标题统一不加粗，默认 ``"normal"``。
    """
    _ensure_fonts()
    kwargs = {}
    if x is not None:
        kwargs["x"] = x
    if ha is not None:
        kwargs["ha"] = ha
    fig.suptitle(
        title,
        fontsize=fontsize,
        fontweight=fontweight,
        fontfamily=_title_font_family(),
        **kwargs,
    )


def draw_note_and_bottom_title(
    fig,
    *,
    note=None,
    title=None,
    title_position="top",
    note_loc="left",
    note_prefix=None,
    legend=None,
):
    """Place a bottom title and/or a lower-left note in figure coordinates.

    This must be called after ``fig.tight_layout()`` because it reserves extra
    bottom margin and positions text relative to the figure.

    Parameters
    ----------
    fig : matplotlib.figure.Figure
    note : str, optional
        Free-text note placed at the lower-left of the figure. When a bottom
        title is also present the note is positioned below it; otherwise it
        sits just below the x-axis area.
    title : str, optional
        Title text. Only used here when ``title_position == "bottom"``.
    title_position : str
        ``"top"`` (default) or ``"bottom"``. Only ``"bottom"`` draws a title.
    note_loc : {"left", "center", "right"}
        Horizontal placement of the note. Defaults to ``"left"``.
    note_prefix : str, optional
        Text prepended to the note (e.g. ``"数据来源："``). ``None`` or an
        empty string disables the prefix.
    legend : BottomLegend or None
        When given, a frameless legend is drawn in the bottom margin, just
        below the time axis / year-ruler labels, and any bottom title / note
        stack beneath it (图例在时间轴下方、图注紧跟其下). ``None`` keeps the
        legendless layout.
    """
    bottom_title = title is not None and title_position == "bottom"
    if not (bottom_title or note is not None or legend is not None):
        return

    if legend is None:
        # Reserve just enough extra space below the subplot for the note.
        # The free band from 0 → extra (figure coordinates) sits below the
        # x-axis label area; the note is anchored near the *top* of that band
        # so it appears close to the axis rather than at the very bottom.
        has_both = bottom_title and note is not None
        extra = 0.06 + (0.05 if has_both else 0.0)
        fig.subplots_adjust(bottom=fig.subplotpars.bottom + extra)

        if bottom_title:
            # Place directly below the x-axis label (centered), just above
            # the note; positioned closer to the x-axis than the note.
            y_title = extra + 0.012
            fig.text(
                0.5,
                y_title,
                title,
                fontsize=TITLE_FONTSIZE,
                color=INK,
                ha="center",
                va="top",
                family=_title_font_family(),
            )

        if note is not None:
            if note_loc not in ("left", "center", "right"):
                raise ValueError(
                    f"note_loc={note_loc!r} is not valid. Choose 'left', 'center', or 'right'."
                )
            note_x, note_ha = {
                "left": (0.04, "left"),
                "center": (0.5, "center"),
                "right": (0.96, "right"),
            }[note_loc]
            # When a bottom title is present, the note sits below it.
            # Otherwise the note appears just below the xlabel, near the top
            # of the reserved band.
            y_note = (extra - 0.045) if bottom_title else (extra - 0.005)
            display_note = f"{note_prefix}{note}" if note_prefix else note
            fig.text(
                note_x,
                y_note,
                display_note,
                fontsize=NOTE_FONTSIZE,
                color=INK,
                ha=note_ha,
                va="top",
                family=_title_font_family(),
            )
        return

    # --- Legend (and optional bottom title / note) in the bottom margin -----
    # 版面自下而上：note → [bottom title] → legend；图例下缘贴着时间轴下方。
    visible = [axes for axes in fig.axes if axes.get_visible()]
    if not visible:
        return
    ref_ax = min(visible, key=lambda axes: axes.get_position().y0)

    count = len(legend.labels)
    # 近方形自动排布：ceil(sqrt(n)) 列（4 条 → 2×2），长文字时避免过宽单行。
    ncol = legend.ncol or (math.ceil(math.sqrt(count)) if count else 1)
    fontsize = resolve_legend_fontsize(fig, legend.legend_size)
    scale = fontsize / LEGEND_FONTSIZE
    legend_artist = ref_ax.legend(
        legend.handles,
        legend.labels,
        loc="upper center",
        bbox_to_anchor=(0.5, legend.below_offset),
        frameon=False,
        fontsize=fontsize,
        markerscale=1.6 * scale,
        handlelength=2.6 * scale,
        title=legend.legend_title or None,
        title_fontsize=fontsize,
        ncol=ncol,
    )

    # 测量图例实际高度，再把底部边距撑到刚好容纳 图例→(标题)→图注 的堆叠。
    renderer = _draw_renderer(fig)
    extent = legend_artist.get_window_extent(renderer)
    inv = fig.transFigure.inverted()
    legend_bottom_frac = inv.transform((extent.x0, extent.y0))[1]
    text_h = NOTE_FONTSIZE * 1.3 / 72 / fig.get_size_inches()[1]
    gap = 0.012
    # 图例底部之下所需内容高度：note（有底部标题时再加一段标题与间隔）+
    # 底部余量。
    required_bottom = gap + text_h + 0.006
    if bottom_title:
        required_bottom = gap + text_h + gap + text_h + 0.006
    offset_abs = -legend.below_offset
    # 抬高轴底边距 m 时，图例（锚在轴坐标系）随轴同步上移 (1+offset_abs)·m，
    # 因此一次性算出所需抬高量即可精确落在目标位置。
    raise_by = max(0.0, (required_bottom - legend_bottom_frac) / (1 + offset_abs))
    if raise_by > 0:
        fig.subplots_adjust(bottom=fig.subplotpars.bottom + raise_by)
    legend_bottom_frac += raise_by * (1 + offset_abs)

    if bottom_title:
        y_title = legend_bottom_frac - gap
        fig.text(
            0.5,
            y_title,
            title,
            fontsize=TITLE_FONTSIZE,
            color=INK,
            ha="center",
            va="top",
            family=_title_font_family(),
        )
        note_y = y_title - text_h - gap
    else:
        note_y = legend_bottom_frac - gap

    if note is not None:
        if note_loc not in ("left", "center", "right"):
            raise ValueError(
                f"note_loc={note_loc!r} is not valid. Choose 'left', 'center', or 'right'."
            )
        note_x, note_ha = {
            "left": (0.04, "left"),
            "center": (0.5, "center"),
            "right": (0.96, "right"),
        }[note_loc]
        display_note = f"{note_prefix}{note}" if note_prefix else note
        fig.text(
            note_x,
            note_y,
            display_note,
            fontsize=NOTE_FONTSIZE,
            color=INK,
            ha=note_ha,
            va="top",
            family=_title_font_family(),
        )


def _fig_axes(ax=None, figsize=None):
    """Return ``(fig, ax)`` by reusing *ax*'s figure or creating a new one."""
    if ax is None:
        return plt.subplots(figsize=figsize or FIGSIZE)
    return ax.figure, ax


def _facet_grid(count, figsize=None):
    """Create a facet figure with one panel per response.

    Panels are arranged in at most two columns; height grows with the row
    count, and unused grid cells are hidden.  Returns ``(fig, axes)`` with
    *axes* a flat list of the first *count* axes.
    """
    ncols = min(2, count)
    nrows = math.ceil(count / ncols)
    if figsize is None:
        figsize = (FIGSIZE[0], FIGSIZE[1] * nrows)
    fig, grid_axes = plt.subplots(nrows, ncols, figsize=figsize, squeeze=False)
    flattened = list(grid_axes.ravel())
    axes = flattened[:count]
    for unused in flattened[count:]:
        unused.set_visible(False)
    return fig, axes


def _finalize_facet_figure(
    fig,
    *,
    title=None,
    note=None,
    title_position="top",
    note_loc="left",
    note_prefix=None,
):
    """Apply the shared facet layout: suptitle, tight layout, and bottom note."""
    if title is not None and title_position == "top":
        draw_suptitle(fig, title)
        fig.tight_layout(rect=FACET_RECT, pad=TIGHT_PAD)
    else:
        fig.tight_layout(pad=TIGHT_PAD)
    draw_note_and_bottom_title(
        fig,
        note=note,
        title=title,
        title_position=title_position,
        note_loc=note_loc,
        note_prefix=note_prefix,
    )


class FigureLifecycle:
    """Own figure creation, styling, and final layout for one public plot.

    Plot implementations add marks and axis-specific behavior, then call
    :meth:`finalize` exactly once.  Keeping this lifecycle in one object makes
    the returned ``(fig, ax)`` contract and layout ordering consistent across
    the plotting package and result plots.
    """

    def __init__(self, ax=None, figsize=None):
        self.fig, self.ax = _fig_axes(ax, figsize=figsize)

    def finalize(
        self,
        *,
        title=None,
        xtitle=None,
        ytitle=None,
        title_position="top",
        title_loc="center",
        title_pad=TITLE_PAD,
        note=None,
        note_loc="left",
        note_prefix=None,
        grid=False,
        grid_axis="both",
        grid_linewidth=0.6,
        grid_linestyle="--",
        show_legend=True,
        legend_labels=None,
        legend_loc="best",
        legend_bbox=None,
        legend_title=None,
        legend_cols=None,
        legend_size=None,
        unit=None,
        x_unit=None,
        bottom_legend=None,
    ):
        """Apply common post-plot styling."""
        _ensure_fonts()

        if title and title_position == "top":
            self.ax.set_title(
                title,
                fontsize=TITLE_FONTSIZE,
                fontweight="normal",
                loc=title_loc,
                pad=title_pad,
            )

        if xtitle:
            self.ax.set_xlabel(xtitle, fontsize=AXIS_LABEL_FONTSIZE)
        if ytitle:
            self.ax.set_ylabel(ytitle, fontsize=AXIS_LABEL_FONTSIZE)

        style_axes(
            self.ax,
            grid=grid,
            grid_axis=grid_axis,
            grid_linewidth=grid_linewidth,
            grid_linestyle=grid_linestyle,
            tick_labelsize=TICK_LABELSIZE,
        )

        if show_legend and bottom_legend is None:
            draw_legend(
                self.ax,
                show_legend=show_legend,
                legend_labels=legend_labels,
                legend_loc=legend_loc,
                legend_bbox=legend_bbox,
                legend_title=legend_title,
                legend_cols=legend_cols,
                legend_size=legend_size,
            )

        if unit is not None:
            draw_unit_label(self.ax, unit, axis="y")
        if x_unit is not None:
            draw_unit_label(self.ax, x_unit, axis="x")

        self.fig.tight_layout(pad=TIGHT_PAD)

        if (
            bottom_legend is not None
            or note
            or (title and title_position == "bottom")
        ):
            draw_note_and_bottom_title(
                self.fig,
                note=note,
                title=title,
                title_position=title_position,
                note_loc=note_loc,
                note_prefix=note_prefix,
                legend=bottom_legend,
            )
