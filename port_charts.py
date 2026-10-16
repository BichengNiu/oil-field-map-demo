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

    fields = ["portcalls", *(f"portcalls_{kind}" for kind in SHIP_TYPE_LABELS)]
    frame = pd.DataFrame(rows, columns=["date", *fields]).set_index("date")
    frame.index = pd.to_datetime(frame.index)
    frame = frame.loc[str(first_day):].astype(float)
    frame = frame.rename(columns={"portcalls": "每日进港艘次", **{
        f"portcalls_{kind}": label for kind, label in SHIP_TYPE_LABELS.items()
    }})
    images = []
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
                    figsize=(4.2, 2.8), xtitle="日期", ytitle="进港艘次", ymin=0, grid=True,
                    linewidth=1.5, markersize=0, show_legend=False, max_ticks=4,
                    legend_cols=5, legend_size=12, note=None,
                )
                # Keep chart labels readable and use the installed CJK family.
                from matplotlib.text import Text
                for text in fig.findobj(Text):
                    text.set_fontfamily(["DejaVu Sans", chinese_font])
                    text.set_fontsize(max(12, text.get_fontsize()))
                ax.yaxis.get_major_locator().set_params(integer=True)
                buffer = io.BytesIO()
                fig.savefig(buffer, format="png", dpi=140, bbox_inches="tight", facecolor="white")
                images.append(buffer.getvalue())
            finally:
                if fig is not None:
                    plt.close(fig)
    return tuple(images)
