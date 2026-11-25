"""Read a Zotero collection into the catalogue using the version 3 API."""

import json
import os
import re
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from dotenv import dotenv_values

from shacl_py.bibliography import from_csl, merge_bibliography
from shacl_py.sources import zotero_item_id

LOCAL_API = "http://127.0.0.1:23119/api/users/0"
WEB_API = "https://api.zotero.org"
KEY = re.compile(r"[A-Z0-9]{8}")
PAGE_SIZE = 100


def _pages(base, path, *, params=None, api_key=None):
    start = 0
    version = None
    seen = set()
    while True:
        query = urlencode(
            {**(params or {}), "start": start, "limit": PAGE_SIZE}, doseq=True
        )
        request = Request(
            f"{base}/{path}?{query}",
            headers={"Zotero-API-Version": "3", "Accept": "application/json"},
        )
        if api_key:
            request.add_unredirected_header("Zotero-API-Key", api_key)
        try:
            with urlopen(request, timeout=30) as response:
                page = json.load(response)
                total = response.headers.get("Total-Results")
                current = response.headers.get("Last-Modified-Version")
                backoff = response.headers.get("Backoff")
        except HTTPError as error:
            if error.code == 403 and base == LOCAL_API:
                raise ValueError(
                    "Enable local API access in Zotero Settings → Advanced."
                ) from error
            if error.code in (401, 403):
                raise ValueError(
                    "Zotero denied read access. Check the library ID and ZOTERO_API_KEY permissions."
                ) from error
            if error.code in (429, 503):
                delay = error.headers.get("Retry-After")
                raise ValueError(
                    f"Zotero is busy. Retry {'in ' + delay + ' seconds' if delay and delay.isdigit() else 'later'}."
                ) from error
            raise ValueError(
                f"Zotero returned HTTP {error.code} for {path}."
            ) from error
        except (URLError, TimeoutError) as error:
            if base == LOCAL_API:
                raise ValueError(
                    "Cannot reach Zotero Desktop. Open Zotero and enable local API access in Settings → Advanced."
                ) from error
            raise ValueError(
                f"Cannot reach the Zotero Web API: {error.reason if isinstance(error, URLError) else error}"
            ) from error
        if backoff and backoff.isdigit() and int(backoff):
            raise ValueError(f"Zotero requested a pause. Retry in {backoff} seconds.")
        if not isinstance(page, list):
            raise TypeError(f"Expected a Zotero list for {path}.")
        if start and current != version:
            raise ValueError(
                "The Zotero library changed during import. Run the command again."
            )
        version = current
        for row in page:
            key = row.get("key") if isinstance(row, dict) else None
            if not isinstance(key, str) or not KEY.fullmatch(key) or key in seen:
                raise ValueError(
                    f"Missing, invalid or repeated Zotero key in {path}. Retry the import."
                )
            seen.add(key)
            yield row
        start += len(page)
        if total is not None:
            if start == int(total):
                return
            if start > int(total) or not page:
                raise ValueError(
                    f"Incomplete Zotero response for {path}. Retry the import."
                )
        elif len(page) < PAGE_SIZE:
            return


def _entry(item, requested):
    data = item.get("data")
    if not isinstance(data, dict):
        raise TypeError(f"Missing Zotero item data for {item['key']}.")
    if data.get("itemType") in ("attachment", "note", "annotation"):
        return None
    csl = item.get("csljson")
    # Desktop returns the CSL exporter output as text. The Web API returns an object.
    if isinstance(csl, str):
        csl = json.loads(csl)
    if isinstance(csl, list) and len(csl) == 1:
        csl = csl[0]
    if not isinstance(csl, dict):
        raise TypeError(f"Missing CSL citation for Zotero item {item['key']}.")
    library = item.get("library") or {}
    kind, number = library.get("type"), library.get("id")
    if kind not in ("user", "group") or not str(number).isdigit():
        raise ValueError(f"Missing Zotero library identity for {item['key']}.")
    scope = f"{kind}s/{number}"
    if (requested and scope != requested) or (not requested and kind != "user"):
        raise ValueError(f"Unexpected Zotero library {scope}.")
    ident = f"{scope}/items/{item['key']}"
    if scope == "users/0":
        local_id = zotero_item_id(csl.get("id"))
        if (
            local_id
            and local_id.startswith("users/local/")
            and local_id.endswith("/" + item["key"])
        ):
            ident = local_id
    if not zotero_item_id(ident):
        raise ValueError(f"Invalid Zotero item identifier {ident}.")
    tags = [
        t["tag"] for t in data.get("tags", []) if isinstance(t, dict) and t.get("tag")
    ]
    entry = from_csl({**csl, "keyword": tags or csl.get("keyword")})
    return {**entry, "key": item["key"], "zotero_item": ident}


def import_zotero(root, collection=None, *, into=None, web_library=None, dry_run=False):
    """Import direct members of one collection, identified by exact name or key."""
    settings = {}
    path = Path(root) / "configuration.env"
    if path.exists():
        with path.open(encoding="utf-8-sig") as stream:
            settings = dotenv_values(stream=stream, interpolate=False)
    if collection is None:
        collection = os.environ.get(
            "ZOTERO_COLLECTION", settings.get("ZOTERO_COLLECTION")
        )
    if web_library is None:
        web_library = os.environ.get(
            "ZOTERO_WEB_LIBRARY", settings.get("ZOTERO_WEB_LIBRARY")
        )
    collection = (collection or "").strip()
    web_library = (web_library or "").strip() or None
    if not collection:
        raise ValueError(
            "Set ZOTERO_COLLECTION in the project's configuration.env or pass --collection."
        )
    base, api_key = LOCAL_API, None
    if web_library is not None:
        if not re.fullmatch(r"(?:users|groups)/[1-9][0-9]*", web_library):
            raise ValueError(
                "Use users/ID or groups/ID for --web-library, with a numeric Zotero ID."
            )
        base = f"{WEB_API}/{web_library}"
        api_key = os.environ.get("ZOTERO_API_KEY", settings.get("ZOTERO_API_KEY"))
    collections = list(_pages(base, "collections", api_key=api_key))
    matches = [row for row in collections if row["key"] == collection]
    if not matches:
        matches = [
            row
            for row in collections
            if str((row.get("data") or {}).get("name", "")).casefold()
            == collection.casefold()
        ]
    if not matches:
        raise ValueError(f"No Zotero collection named {collection!r} in this library.")
    if len(matches) > 1:
        raise ValueError(
            f"Several Zotero collections are named {collection!r}. Use a collection key: "
            + ", ".join(row["key"] for row in matches)
        )
    path = f"collections/{matches[0]['key']}/items/top"
    # Web accepts one item-type expression. Desktop combines repeated filters.
    omit = (
        "-attachment || note || annotation"
        if web_library
        else ["-attachment", "-note", "-annotation"]
    )
    params = {"itemType": omit, "include": "data,csljson"}
    entries = (
        _entry(row, web_library)
        for row in _pages(base, path, params=params, api_key=api_key)
    )
    return merge_bibliography(
        root,
        [entry for entry in entries if entry is not None],
        into=into,
        dry_run=dry_run,
    )
