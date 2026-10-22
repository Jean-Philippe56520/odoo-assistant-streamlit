"""Import d'une carte My Maps en calques GeoJSON pour l'affichage ABM."""
import re
import html
import urllib.request
import xml.etree.ElementTree as ET

MAX_BYTES = 35_000_000

class MapImportError(Exception):
    pass

def _tag(e):
    return e.tag.rsplit("}", 1)[-1]

def _children(e, key):
    return [x for x in e if _tag(x) == key] if e is not None else []

def _child(e, key):
    return next(iter(_children(e, key)), None)

def _text(e, key, default=""):
    x = _child(e, key)
    return (x.text or "").strip() if x is not None else default

def _color(value):
    value = value.strip().lstrip("#")
    if re.fullmatch("[0-9a-fA-F]{8}", value):
        return "#" + value[6:8] + value[4:6] + value[2:4], round(int(value[:2], 16) / 255, 2)
    return "#1b6491", 0.7

def _style(e):
    style = {}
    if e is None:
        return style
    for tag, prefix in (("LineStyle", "line"), ("PolyStyle", "poly"), ("IconStyle", "icon")):
        section = _child(e, tag)
        if section is not None:
            style[prefix + "Color"], style[prefix + "Opacity"] = _color(_text(section, "color"))
            if tag == "LineStyle":
                try:
                    style["weight"] = min(8, max(1, float(_text(section, "width", "2"))))
                except ValueError:
                    pass
    return style

def _coords(s):
    result = []
    for token in re.split(r"\s+", s.strip()):
        bits = token.split(",")
        if len(bits) < 2:
            continue
        try:
            a,b = float(bits[0]),float(bits[1])
        except ValueError:
            continue
        if -180 <= a <= 180 and -90 <= b <= 90:
            result.append([round(a, 6), round(b, 6)])
    return result

def _geo(e):
    kind = _tag(e)
    if kind == "Point":
        coords = _coords(_text(e, "coordinates"))
        return {"type":"Point", "coordinates":coords[0]} if coords else None
    if kind == "LineString":
        coords = _coords(_text(e, "coordinates"))
        return {"type":"LineString", "coordinates":coords} if len(coords)>1 else None
    if kind == "Polygon":
        rings = []
        for boundary in ("outerBoundaryIs", "innerBoundaryIs"):
            for e2 in _children(e, boundary):
                ring = _child(e2, "LinearRing")
                coords = _coords(_text(ring, "coordinates"))
                if len(coords)>=3:
                    if coords[0]!=coords[-1]:
                        coords.append(coords[0])
                    rings.append(coords)
        return {"type":"Polygon","coordinates":rings} if rings else None
    if kind == "MultiGeometry":
        geoms=[x for child in e if (x:=_geo(child)) is not None]
        return {"type":"GeometryCollection","geometries":geoms} if geoms else None
    return None

def _description(s):
    s=re.sub(r"<\s*br\s*/?>","\n",s,flags=re.I)
    s=re.sub(r"<[^>]*>"," ",s)
    return html.unescape(s).strip()[:2000]

def load_map(mid):
    if not re.fullmatch(r"[A-Za-z0-9_-]{10,128}", mid or ""):
        raise MapImportError("Identifiant de carte invalide.")
    url=f"https://www.google.com/maps/d/kml?mid={mid}&forcekml=1"
    request=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0"})
    try:
        with urllib.request.urlopen(request,timeout=25) as response:
            data=response.read(MAX_BYTES+1)
        if len(data)>MAX_BYTES:
            raise MapImportError("Export KML trop volumineux.")
        root=ET.fromstring(data)
    except (OSError,ET.ParseError) as exc:
        raise MapImportError("Impossible de charger les calques depuis My Maps.") from exc
    doc=next((x for x in root.iter() if _tag(x)=="Document"),root)
    styles={}
    normal={}
    for e in root.iter():
        id=e.attrib.get("id")
        if id and _tag(e)=="Style":
            styles[id]=_style(e)
        if id and _tag(e)=="StyleMap":
            for pair in _children(e,"Pair"):
                if _text(pair,"key")=="normal":
                    normal[id]=_text(pair,"styleUrl").lstrip("#")
    layers=[]
    features=[]
    def add_layer(label, marks):
        layer_id=str(len(layers))
        count=0
        color="#1b6491"
        for mark in marks:
            geo=next((_geo(child) for child in mark if _tag(child) in ("Point","LineString","Polygon","MultiGeometry")),None)
            if not geo:
                continue
            key=_text(mark,"styleUrl").lstrip("#")
            key=normal.get(key,key)
            style={**styles.get(key,{}), **_style(_child(mark,"Style"))}
            color=style.get("polyColor") or style.get("iconColor") or style.get("lineColor") or color
            features.append({"layer":layer_id,"name":_text(mark,"name","Sans nom")[:250],
                             "description":_description(_text(mark,"description")),
                             "geometry":geo,"style":style})
            count+=1
            if len(features)>15000:
                raise MapImportError("Trop d'objets géographiques.")
        if count:
            layers.append({"id":layer_id,"name":label[:180],"count":count,"color":color})
    folders=_children(doc,"Folder")
    for folder in folders:
        add_layer(_text(folder,"name","Calque"),[e for e in folder.iter() if _tag(e)=="Placemark"])
    direct=_children(doc,"Placemark")
    if direct: add_layer("Autres éléments",direct)
    if not folders and not direct:
        add_layer(_text(doc,"name","Carte ABM"),[e for e in doc.iter() if _tag(e)=="Placemark"])
    if not features:
        raise MapImportError("Aucun élément exploitable dans le KML.")
    return {"title":_text(doc,"name","Carte ABM"),"layers":layers,"features":features}
