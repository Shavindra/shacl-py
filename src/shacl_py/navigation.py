"""Synchronise the viewer with the browser's URL fragment."""

from pathlib import Path
from urllib.parse import parse_qsl, urlencode

import streamlit as st

router = st.components.v2.component(
    "shacl_py_navigation",
    js=(Path(__file__).with_name("templates") / "navigation.js").read_text(),
)


def current_route():
    fragment = router(key="viewer_navigation", on_route_change=None).get("route")
    if fragment is None:
        return None  # The browser has not sent the initial URL yet.
    return dict(parse_qsl(fragment, keep_blank_values=True))


def url(route, **updates):
    return "#" + urlencode(
        {k: v for k, v in (route | updates).items() if v is not None}
    )
