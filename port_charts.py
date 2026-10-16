"""Port daily charts using the pinned Ts plot_series public API."""
from __future__ import annotations

import io
import threading

import streamlit as st
from portwatch_records import SHIP_TYPE_LABELS

_PLOT_LOCK = threading.RLock()


@st.cache_data(max_entries=12, show_spinner=False)
def chart_images(rows: tuple, first_day) -> tuple[bytes, ...]:
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

    fields = ["portcalls", *(f"portcalls_{kind}" for kind in SHIP_TYPE_LABELS)]
    frame = pd.DataFrame(rows, columns=["date", *fields]).set_index("date")
    frame.index = pd.to_datetime(frame.index)
    frame = frame.loc[str(first_day):].astype(float)
    frame = frame.rename(columns={"portcalls": "每日进港艘次", **{
        f"portcalls_{kind}": label for kind, label in SHIP_TYPE_LABELS.items()
    }})
    images = []
    span = (frame.index[-1] - frame.index[0]).days
    year_ruler = 60 <= span <= 550
    # Matplotlib's font state is global; serialize rendering across sessions.
    with _PLOT_LOCK, plt.rc_context():
        _ensure_fonts()
        chinese_font = apply_fonts(latin="DejaVu Sans", chinese_candidates=["Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "Noto Sans CJK JP"])
        style.LATIN_FONT = "DejaVu Sans"
        style.SELECTED_CHINESE_FONT = chinese_font
        style.SELECTED_HEITI_FONT = chinese_font
        for label in ["每日进港艘次", *SHIP_TYPE_LABELS.values()]:
            fig = None
            try:
                fig, ax = plot_series(
                    frame[[label]], facet=False, auto_dual_y=False,
                    figsize=(6.2, 4.3), xtitle="", ytitle="艘次",
                    ytitle_position="side", ymin=0, grid=False,
                    year_ruler=year_ruler, monthly_ticks=span <= 100,
                    linewidth=1.5, markersize=0, show_legend=False, max_ticks=6,
                    note=None,
                )
                if not year_ruler:
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
                ax.set_title(label if label == "每日进港艘次" else f"{label}每日进港艘次",
                             fontsize=18, fontfamily=[chinese_font], pad=12)
                # Ts lays out its template before this application font pass.
                # Reserve room again for the readable type and the year ruler.
                fig.subplots_adjust(left=0.16, right=0.97, top=0.86, bottom=0.25 if year_ruler else 0.17)
                buffer = io.BytesIO()
                fig.savefig(buffer, format="png", dpi=140, facecolor="white")
                images.append(buffer.getvalue())
            finally:
                if fig is not None:
                    plt.close(fig)
    return tuple(images)
