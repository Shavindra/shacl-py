"""Minimal local project catalogue."""

import os
from pathlib import Path

import streamlit as st

from shacl_py.records import list_files, load_records

st.set_page_config(page_title="shacl-py", layout="wide")
st.title("shacl-py")
root = Path(os.environ.get("SHACL_PY_ROOT", ".")).resolve()
try:
    records, errors = load_records(root)
except (OSError, ValueError) as error:
    st.error(str(error))
    st.stop()
for error in errors:
    st.error(error)
query = st.text_input("Search projects").casefold().strip()
selected = st.query_params.get("project")
if selected:
    matches = [record for record in records if record.data["pid"] == selected]
    if st.button("All projects"):
        st.query_params.clear()
        st.rerun()
    if not matches:
        st.warning("Project not found.")
    else:
        record = matches[0]
        st.header(record.data["display_label"])
        st.write(record.data["description"])
        st.caption(record.data["review_status"])
        st.link_button("DOI / source", record.data["source_url"])
        with st.expander("Metadata"):
            st.json(record.data)
            st.text(str(record.metadata.relative_to(root)))
        for section in ("notebooks", "data/raw", "data/output"):
            st.subheader(section + "/")
            rows = list_files(record.folder, section)
            if rows:
                st.dataframe(rows, hide_index=True, use_container_width=True)
            else:
                st.caption("No local entries.")
else:
    shown = 0
    for record in records:
        data = record.data
        if query and query not in " ".join(str(v) for v in data.values()).casefold():
            continue
        shown += 1
        with st.container(border=True):
            st.subheader(data["display_label"])
            st.write(data["description"])
            st.caption(data["review_status"])
            if st.button("Open project", key=data["pid"]):
                st.query_params["project"] = data["pid"]
                st.rerun()
    if not shown:
        st.info("No matching projects.")
