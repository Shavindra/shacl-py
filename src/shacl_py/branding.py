"""Viewer branding from the served project's .shacl-py/config.yaml."""

import base64
from mimetypes import guess_type
from urllib.parse import urlsplit

import yaml

from shacl_py.files import read_metadata, scoped_path


def branding(base):
    config_path = scoped_path(base, ".shacl-py/config.yaml")
    config = {}
    if config_path.is_file():
        try:
            config = yaml.safe_load(read_metadata(config_path))
        except yaml.YAMLError as exc:
            raise ValueError(f"{config_path}: {exc}") from exc
        if config is None:
            config = {}
    if not isinstance(config, dict) or not isinstance(
        config.get("app_theme", {}), dict
    ):
        raise TypeError(f"{config_path}: expected a mapping for config and app_theme")
    values = {}
    for key, value in (
        ("app_name", config.get("app_name", "")),
        ("page_title", config.get("page_title", "")),
        ("logo", config.get("app_theme", {}).get("logo", "")),
    ):
        if not isinstance(value, str):
            raise TypeError(f"{config_path}: {key} must be text")
        values[key] = value.strip()
    values["app_name"] = values["app_name"] or "shaclpy"
    values["page_title"] = values["page_title"] or values["app_name"]
    if logo := values["logo"]:
        url = urlsplit(logo)
        if url.scheme or url.netloc:
            if url.scheme not in ("http", "https") or not url.hostname:
                raise ValueError(
                    "app_theme.logo requires an HTTP(S) URL or a relative file path"
                )
        else:
            path = scoped_path(config_path.parent, logo)
            mime = guess_type(path.name)[0] or ""
            if not mime.startswith("image/") or path.is_symlink() or not path.is_file():
                raise ValueError(f"app_theme.logo requires a local image file: {path}")
            data = base64.b64encode(path.read_bytes()).decode("ascii")
            values["logo"] = f"data:{mime};base64,{data}"
    return values
