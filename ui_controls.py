"""Selection controls shared by the sidebar and download page."""

from __future__ import annotations

import streamlit as st

ALL_SELECTION = "全选"


def selection_changed(key: str) -> None:
    """Keep 全选 exclusive while allowing an empty selection to mean none."""
    previous_key = f"_selection_previous_{key}"
    selected = list(st.session_state.get(key, []))
    previous = list(st.session_state.get(previous_key, []))
    newly_added = [value for value in selected if value not in previous]
    if ALL_SELECTION in newly_added:
        selected = [ALL_SELECTION]
    elif ALL_SELECTION in selected:
        selected = [value for value in selected if value != ALL_SELECTION]
    st.session_state[key] = selected
    st.session_state[previous_key] = list(selected)


def multiselect_with_all(
    label: str,
    options: list,
    *,
    key: str,
    default_all: bool = True,
    default: list | None = None,
    format_func=None,
    **kwargs,
) -> list:
    """Add an exclusive 全选 option; an empty selection stays empty."""
    options = list(options)
    valid_options = set(options)
    previous_key = f"_selection_previous_{key}"
    if key not in st.session_state:
        selected = [ALL_SELECTION] if default_all else list(default or [])
    else:
        current = st.session_state.get(key, [])
        selected = list(current) if isinstance(current, (list, tuple)) else [current]
        # Migrate an old empty selection once; new empty selections remain empty.
        if not selected and default_all and previous_key not in st.session_state:
            selected = [ALL_SELECTION]
        selected = [value for value in selected if value == ALL_SELECTION or value in valid_options]
        if ALL_SELECTION in selected and len(selected) > 1:
            previous = list(st.session_state.get(previous_key, []))
            newly_added = [value for value in selected if value not in previous]
            if ALL_SELECTION in newly_added:
                selected = [ALL_SELECTION]
            else:
                selected = [value for value in selected if value != ALL_SELECTION]
    st.session_state[key] = selected
    st.session_state[previous_key] = list(selected)

    def display(value):
        if value == ALL_SELECTION:
            return ALL_SELECTION
        return format_func(value) if format_func else str(value)

    return st.multiselect(
        label,
        [ALL_SELECTION, *options],
        key=key,
        format_func=display,
        on_change=selection_changed,
        args=(key,),
        **kwargs,
    )


def selected_values(selection: list, options: list) -> list:
    """Expand explicit 全选; keep [] as an empty filter."""
    return list(options) if ALL_SELECTION in selection else list(selection)
