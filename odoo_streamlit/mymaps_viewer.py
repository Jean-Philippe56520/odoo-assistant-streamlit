"""Visionneuse de carte responsive, alimentée par les calques My Maps ABM."""

import json
from pathlib import Path

_TEMPLATE = Path(__file__).with_name("mymaps_viewer_template.html")


def build_viewer_html(map_data: dict, selected_point=None) -> str:
    """Transmet les données sans autoriser l'exécution de HTML provenant du KML."""
    data_json = json.dumps(map_data, ensure_ascii=False, separators=(",", ":"))
    data_json = (
        data_json.replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )
    point_json = json.dumps(selected_point, ensure_ascii=False)
    return (
        _TEMPLATE.read_text(encoding="utf-8")
        .replace("__ABM_MAP_DATA__", data_json)
        .replace("__ABM_MAP_FOCUS__", point_json)
    )
