"""Port call aggregation and charts using the pinned Ts public API."""
from __future__ import annotations

import io
import threading
from collections import defaultdict
from datetime import date, timedelta
import calendar
import math

import streamlit as st
from portwatch_records import SHIP_TYPE_LABELS

_PLOT_LOCK = threading.RLock()
AGGREGATIONS = {"日度": "每日", "周度": "每周", "月度": "每月", "年度": "年度"}


def series_labels(aggregation="日度") -> dict[str, str]:
    prefix = AGGREGATIONS[aggregation]
    return {"portcalls": f"{prefix}进港艘次", **{
        f"portcalls_{kind}": f"{label}{prefix}进港艘次" for kind, label in SHIP_TYPE_LABELS.items()
    }}


def aggregate_rows(rows: tuple, first_day: date, aggregation="日度") -> list[dict]:
    """Sum the selected date window; missing days/values remain unknown."""
    if aggregation not in AGGREGATIONS:
        raise ValueError("未知聚合方式")
    selected = sorted((row for row in rows if row[0] >= first_day), key=lambda row: row[0])
    if not selected:
        return []
    if len({row[0] for row in selected}) != len(selected):
        raise ValueError("每日进港统计存在重复日期")
    first, last = selected[0][0], selected[-1][0]
    fields = tuple(series_labels(aggregation))
    groups = defaultdict(list)
    for row in selected:
        day = row[0]
        start = (day - timedelta(days=day.weekday()) if aggregation == "周度" else
                 day.replace(day=1) if aggregation == "月度" else
                 day.replace(month=1, day=1) if aggregation == "年度" else day)
        groups[start].append(row)
    result = []
    for start, group in groups.items():
        end = (start+timedelta(days=6) if aggregation == "周度" else
               start.replace(day=calendar.monthrange(start.year, start.month)[1]) if aggregation == "月度" else
               start.replace(month=12, day=31) if aggregation == "年度" else start)
        actual_start, actual_end = max(start, first), min(end, last)
        complete = len(group) == (actual_end-actual_start).days+1
        record = {"date": start, "period_start": actual_start, "period_end": actual_end}
        for index, field in enumerate(fields, 1):
            values = [row[index] for row in group]
            record[field] = (sum(values) if complete and all(
                value is not None and math.isfinite(value) and value >= 0 for value in values
            ) else None)
        result.append(record)
    return result


@st.cache_data(max_entries=12, show_spinner=False)
def chart_images(rows: tuple, first_day, aggregation="日度") -> tuple[bytes, ...]:
    # Lazy import: opening the map never imports matplotlib or scans its fonts.
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import pandas as pd
    from Ts.TsPlots import plot_series
    from Ts.TsPlots.style import apply_fonts, _ensure_fonts
    from Ts.TsPlots import style
    from matplotlib.dates import AutoDateLocator, ConciseDateFormatter, DateFormatter
    from matplotlib.ticker import MaxNLocator

    aggregated = aggregate_rows(rows, first_day, aggregation)
    labels = series_labels(aggregation)
    frame = pd.DataFrame(aggregated).set_index("date")[list(labels)].astype(float)
    frame.index = pd.to_datetime(frame.index)
    frame = frame.rename(columns=labels)
    images = []
    span = (frame.index[-1] - frame.index[0]).days
    annual = aggregation == "年度"
    year_ruler = not annual and 60 <= span <= 550
    if annual:
        frame.index = frame.index.strftime("%Y")
    # Matplotlib's font state is global; serialize rendering across sessions.
    with _PLOT_LOCK, plt.rc_context():
        _ensure_fonts()
        chinese_font = apply_fonts(latin="DejaVu Sans", chinese_candidates=["Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "Noto Sans CJK JP"])
        style.LATIN_FONT = "DejaVu Sans"
        style.SELECTED_CHINESE_FONT = chinese_font
        style.SELECTED_HEITI_FONT = chinese_font
        for label in labels.values():
            fig = None
            try:
                fig, ax = plot_series(
                    frame[[label]], facet=False, auto_dual_y=False,
                    figsize=(6.2, 4.6), xtitle="", ytitle="艘次",
                    ytitle_position="side", ymin=0, grid=False,
                    year_ruler=year_ruler, monthly_ticks=span <= 100,
                    linewidth=1.5, markersize=4 if len(frame) == 1 and not annual else 0,
                    bar_series=[label] if annual else None,
                    show_legend=False, max_ticks=6,
                    note=None,
                )
                if annual:
                    ax.set_xlabel(f"{aggregated[0]['period_start']:%Y-%m-%d}—{aggregated[-1]['period_end']:%Y-%m-%d}")
                elif not year_ruler:
                    if span > 550:
                        first_year, last_year = frame.index[0].year, frame.index[-1].year
                        step = max(1, (last_year-first_year+4)//5)
                        years = list(range(first_year, last_year+1, step))
                        if years[-1] != last_year:
                            years.append(last_year)
                        ax.set_xticks([pd.Timestamp(year=year, month=1, day=1) for year in years])
                        ax.xaxis.set_major_formatter(DateFormatter("%Y"))
                    else:
                        locator = AutoDateLocator(minticks=2, maxticks=3)
                        ax.xaxis.set_major_locator(locator)
                        ax.xaxis.set_major_formatter(ConciseDateFormatter(locator))
                    ax.tick_params(axis="x", rotation=0)
                ax.yaxis.set_major_locator(MaxNLocator(nbins=4, integer=True))
                # Keep chart labels readable and use the installed CJK family.
                from matplotlib.text import Text
                for text in fig.findobj(Text):
                    text.set_fontfamily([chinese_font])
                    text.set_fontsize(16)
                ax.set_title(label,
                             fontsize=18, fontfamily=[chinese_font], pad=12)
                # Ts lays out its template before this application font pass.
                # Reserve room again for the readable type and the year ruler.
                fig.subplots_adjust(left=0.21 if annual else 0.16, right=0.97, top=0.86,
                                    bottom=0.30 if year_ruler else 0.17)
                if year_ruler:
                    # Measure the final fonts, including the year label's white
                    # background, before separating both rows. Move the ruler
                    # and its labels together; leave the vendored Ts unchanged.
                    from matplotlib.transforms import ScaledTranslation
                    fig.canvas.draw()
                    renderer = fig.canvas.get_renderer()
                    years = [text for text in ax.texts if text.get_text().strip().removesuffix("年").isdigit()
                             and text.get_text().strip().endswith("年")]
                    months = [text for text in ax.get_xticklabels() if text.get_visible() and text.get_text()]
                    if years and months:
                        year_top = max(text.get_bbox_patch().get_window_extent(renderer).y1 for text in years)
                        month_bottom = min(text.get_window_extent(renderer).y0 for text in months)
                        shift_pixels = max(0, year_top-month_bottom+8*fig.dpi/72)
                        shift = ScaledTranslation(0, -shift_pixels/fig.dpi, fig.dpi_scale_trans)
                        for text in years:
                            text.set_transform(text.get_transform()+shift)
                        for collection in ax.collections:
                            if not collection.get_clip_on() and collection.get_transform() == ax.get_xaxis_transform():
                                collection.set_transform(collection.get_transform()+shift)
                buffer = io.BytesIO()
                fig.savefig(buffer, format="png", dpi=140, facecolor="white")
                images.append(buffer.getvalue())
            finally:
                if fig is not None:
                    plt.close(fig)
    return tuple(images)
