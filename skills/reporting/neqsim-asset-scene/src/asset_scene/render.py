"""Renderers: binary glTF (GLB), offline interactive HTML viewer and PNG figures.

All three use the same triangulation (``scene_parts``) so a GLB opened in a CAD
viewer, the HTML viewer and the report PNG show identical geometry and colours.
The HTML viewer is self-contained (inline JavaScript, no network access).
"""

from __future__ import annotations

import json
import statistics
import struct
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .mesh import Mesh, geometry_mesh, scale_z, tube_mesh
from .routing import ROUTE_WORDS, route_connections, route_length, routing_summary
from .schema import AssetScene, geometry_anchor, geometry_bounds
from .style import STATE_LABELS, ColorBy, hex_color, object_color

INFO_ATTRIBUTE_LIMIT = 12


def _fmt(value: Any) -> str:
    if isinstance(value, dict):
        val = value.get("value")
        unit = value.get("unit", "")
        stamp = value.get("timestamp")
        text = f"{_fmt(val)} {unit}".strip()
        return f"{text} @ {stamp}" if stamp else text
    if isinstance(value, float):
        return f"{value:.4g}"
    return str(value)


def _info(obj: dict[str, Any]) -> dict[str, Any]:
    info: dict[str, Any] = {
        "Tag": obj.get("tag") or "-",
        "Name": obj.get("name"),
        "Kind": obj.get("kind"),
        "State": obj.get("state"),
        "Geometry": f"{obj['source'].get('quality')} ({obj['source'].get('geometry')})",
    }
    for key, val in list(obj.get("attributes", {}).items())[:INFO_ATTRIBUTE_LIMIT]:
        info[key] = _fmt(val)
    for key, val in obj.get("results", {}).items():
        info[f"NeqSim {key}"] = _fmt(val)
    for key, val in obj.get("live", {}).items():
        info[f"Live {key}"] = _fmt(val)
    if obj.get("media"):
        info["Pictures"] = ", ".join(
            str(m.get("caption") or m.get("path")) for m in obj["media"]
        )
    return info


def _default_connection_diameter(scene: AssetScene) -> float:
    sizes = []
    for obj in scene.objects:
        b = geometry_bounds(obj["geometry"])
        sizes.append(max(b[3] - b[0], b[4] - b[1], b[5] - b[2]))
    if not sizes:
        return 0.1
    return max(0.05, 0.04 * statistics.median(sizes))


def _enlarged(geometry: dict[str, Any], min_feature: float) -> dict[str, Any]:
    """Copy of a geometry scaled up to ``min_feature`` (display only, for field-scale views)."""
    geo = dict(geometry)
    shape = geo["shape"]
    if shape == "polyline":
        geo["diameter"] = max(geo["diameter"], 0.25 * min_feature)
        return geo
    b = geometry_bounds(geometry)
    largest = max(b[3] - b[0], b[4] - b[1], b[5] - b[2])
    if largest >= min_feature or largest <= 0:
        return geo
    k = min_feature / largest
    if shape == "box":
        geo["size"] = [v * k for v in geo["size"]]
    elif shape == "cylinder":
        geo["diameter"] *= k
        geo["length"] *= k
    elif shape == "sphere":
        geo["diameter"] *= k
    else:
        geo["size"] = geo.get("size", 1.0) * k
    return geo


def auto_min_feature(
    scene: AssetScene, fraction: float = 0.015, threshold_m: float = 500.0
) -> float | None:
    """Display size floor for field-scale scenes (None when the scene is plant-scale)."""
    b = scene.bounds()
    span = max(b[3] - b[0], b[4] - b[1])
    return fraction * span if span > threshold_m else None


def scene_parts(
    scene: AssetScene,
    color_by: ColorBy | None = None,
    vertical_exaggeration: float = 1.0,
    min_feature: float | None = None,
    routing: str = "auto",
) -> list[dict[str, Any]]:
    """Triangulated, coloured parts (objects first, then routed connections).

    ``min_feature`` enlarges objects smaller than that size (metres) so
    templates and manifolds stay visible on a kilometre-scale field view.
    ``routing`` is ``auto`` (pipe rack at plant scale, seabed at field scale),
    ``orthogonal``, ``seabed`` or ``straight``; a connection with its own
    ``route`` always uses it.
    """
    if color_by is not None:
        color_by.fit(scene.objects)
    parts: list[dict[str, Any]] = []
    for obj in scene.objects:
        geo = (
            _enlarged(obj["geometry"], min_feature) if min_feature else obj["geometry"]
        )
        b = geometry_bounds(geo)
        top = list(geometry_anchor(geo))
        if geo["shape"] != "polyline":
            top[2] = b[5]
        parts.append(
            {
                "id": obj["id"],
                "label": obj.get("tag") or obj.get("name") or obj["id"],
                "state": obj["state"],
                "group": obj["group"],
                "kind": obj["kind"],
                "color": object_color(obj, color_by),
                "mesh": scale_z(geometry_mesh(geo), vertical_exaggeration),
                "info": _info(obj),
                "anchor": top,
            }
        )
    default_d = _default_connection_diameter(scene)
    if min_feature:
        default_d = max(default_d, 0.25 * min_feature)
    routes = route_connections(scene, default_d, routing)
    for conn in scene.connections:
        a = scene.get(conn["from"])
        b = scene.get(conn["to"])
        if a is None or b is None or conn["id"] not in routes:
            continue
        route = routes[conn["id"]]
        radius = (conn.get("diameter") or default_d) / 2.0
        mesh: Mesh = ([], [])
        for p, q in zip(route["points"][:-1], route["points"][1:]):
            seg = tube_mesh(p, q, radius, 8)
            offset = len(mesh[0])
            mesh[0].extend(seg[0])
            mesh[1].extend((i + offset, j + offset, k + offset) for i, j, k in seg[1])
        quality = (
            "verified"
            if route["mode"] == "supplied"
            else conn.get("source", {}).get("quality")
        )
        probe = {"state": conn["state"], "group": a["group"]}
        parts.append(
            {
                "id": conn["id"],
                "label": conn.get("line_number") or conn["id"],
                "state": conn["state"],
                "group": a["group"],
                "kind": "connection",
                "color": object_color(probe),
                "mesh": scale_z(mesh, vertical_exaggeration),
                "info": {
                    "Connection": f"{a.get('tag') or a['id']} -> {b.get('tag') or b['id']}",
                    "Line": conn.get("line_number") or "-",
                    "Kind": conn.get("kind"),
                    "State": conn["state"],
                    "Route": f"{ROUTE_WORDS[route['mode']]}, {route_length(route['points']):.1f} m",
                    "Connectivity": f"{conn.get('source', {}).get('quality')} ({conn.get('source', {}).get('reference') or '-'})",
                },
                "anchor": route["points"][len(route["points"]) // 2],
                "route": route,
                "geometry_quality": quality,
            }
        )
    return parts


# ------------------------------------------------------------------------- GLB
def _pad(data: bytes, fill: bytes) -> bytes:
    return data + fill * ((4 - len(data) % 4) % 4)


def write_glb(
    scene: AssetScene,
    path: Any,
    color_by: ColorBy | None = None,
    vertical_exaggeration: float = 1.0,
    routing: str = "auto",
) -> Path:
    """Write a GLB 2.0 file (metres, glTF Y-up: scene (x, y, z) -> (x, z, -y)).

    Every object becomes one named node whose ``extras`` carry id, tag, kind,
    state, geometry quality and the info table, so a viewer can show provenance.
    Routed connections carry their route points (scene frame) and routing mode.
    Coordinates are shifted so the scene centre is at the origin; the offset is
    stored in ``asset.extras.origin_offset_m``.
    """
    parts = [
        p
        for p in scene_parts(scene, color_by, vertical_exaggeration, routing=routing)
        if p["mesh"][0]
    ]
    b = scene.bounds()
    origin = [(b[0] + b[3]) / 2.0, (b[1] + b[4]) / 2.0, 0.0]
    buffer = bytearray()
    views: list[dict[str, Any]] = []
    accessors: list[dict[str, Any]] = []
    meshes: list[dict[str, Any]] = []
    materials: list[dict[str, Any]] = []
    nodes: list[dict[str, Any]] = []
    for part in parts:
        verts, faces = part["mesh"]
        gl = [(x - origin[0], z - origin[2], -(y - origin[1])) for x, y, z in verts]
        pos = b"".join(struct.pack("<3f", *v) for v in gl)
        idx = b"".join(struct.pack("<3I", *f) for f in faces)
        for data, target, comp, count, typ in (
            (pos, 34962, 5126, len(gl), "VEC3"),
            (idx, 34963, 5125, len(faces) * 3, "SCALAR"),
        ):
            offset = len(buffer)
            buffer.extend(_pad(data, b"\x00"))
            views.append(
                {
                    "buffer": 0,
                    "byteOffset": offset,
                    "byteLength": len(data),
                    "target": target,
                }
            )
            acc = {
                "bufferView": len(views) - 1,
                "componentType": comp,
                "count": count,
                "type": typ,
            }
            if typ == "VEC3":
                acc["min"] = [min(v[i] for v in gl) for i in range(3)]
                acc["max"] = [max(v[i] for v in gl) for i in range(3)]
            accessors.append(acc)
        rgba = list(part["color"])
        material = {
            "name": f"{part['state']}:{part['id']}",
            "pbrMetallicRoughness": {
                "baseColorFactor": rgba,
                "metallicFactor": 0.1,
                "roughnessFactor": 0.8,
            },
            "doubleSided": True,
        }
        if rgba[3] < 1.0:
            material["alphaMode"] = "BLEND"
        materials.append(material)
        meshes.append(
            {
                "name": part["label"],
                "primitives": [
                    {
                        "attributes": {"POSITION": len(accessors) - 2},
                        "indices": len(accessors) - 1,
                        "material": len(materials) - 1,
                    }
                ],
            }
        )
        extras = {
            "id": part["id"],
            "state": part["state"],
            "kind": part["kind"],
            "info": part["info"],
        }
        if part.get("route"):
            extras["route_mode"] = part["route"]["mode"]
            extras["route_points_m"] = [
                [round(c, 3) for c in p] for p in part["route"]["points"]
            ]
        nodes.append(
            {
                "name": part["label"],
                "mesh": len(meshes) - 1,
                "extras": extras,
            }
        )
    document = {
        "asset": {
            "version": "2.0",
            "generator": "neqsim-asset-scene",
            "extras": {
                "scene": scene.name,
                "classification": scene.classification,
                "crs": scene.frame.get("crs"),
                "origin_offset_m": origin,
                "vertical_exaggeration": vertical_exaggeration,
                "axes": "glTF Y-up; scene (x, y, z) maps to (x, z, -y)",
            },
        },
        "scene": 0,
        "scenes": [{"name": scene.name, "nodes": list(range(len(nodes)))}],
        "nodes": nodes,
        "meshes": meshes,
        "materials": materials,
        "accessors": accessors,
        "bufferViews": views,
        "buffers": [{"byteLength": len(buffer)}],
    }
    json_chunk = _pad(json.dumps(document, separators=(",", ":")).encode("utf-8"), b" ")
    bin_chunk = bytes(buffer)
    total = 12 + 8 + len(json_chunk) + 8 + len(bin_chunk)
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("wb") as fh:
        fh.write(struct.pack("<4sII", b"glTF", 2, total))
        fh.write(struct.pack("<I4s", len(json_chunk), b"JSON"))
        fh.write(json_chunk)
        fh.write(struct.pack("<I4s", len(bin_chunk), b"BIN\x00"))
        fh.write(bin_chunk)
    return out


def read_glb_json(path: Any) -> dict[str, Any]:
    """Return the JSON chunk of a GLB (used for verification)."""
    data = Path(path).read_bytes()
    magic, version, length = struct.unpack_from("<4sII", data, 0)
    if magic != b"glTF" or version != 2 or length != len(data):
        raise ValueError("not a valid GLB 2.0 file")
    chunk_len, chunk_type = struct.unpack_from("<I4s", data, 12)
    if chunk_type != b"JSON":
        raise ValueError("GLB has no JSON chunk")
    return json.loads(data[20 : 20 + chunk_len].decode("utf-8"))


# ------------------------------------------------------------------------ HTML
_HTML = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>__TITLE__</title>
<style>
body{margin:0;font-family:Segoe UI,Arial,sans-serif;background:#f4f5f7;color:#222}
#bar{padding:6px 10px;background:#243447;color:#fff;display:flex;gap:14px;align-items:center;flex-wrap:wrap;font-size:13px}
#bar b{font-size:15px}#cls{background:#b00020;color:#fff;padding:2px 8px;border-radius:3px;font-weight:600}
#wrap{position:relative}canvas{display:block;width:100%;height:72vh;background:#fff;cursor:grab}
#tip{position:absolute;pointer-events:none;background:rgba(255,255,255,.96);border:1px solid #999;border-radius:4px;padding:6px 8px;font-size:12px;display:none;max-width:420px;box-shadow:0 2px 6px rgba(0,0,0,.2)}
#tip table{border-collapse:collapse}#tip td{padding:1px 6px;vertical-align:top}#tip td:first-child{color:#555}
#legend{padding:6px 10px;font-size:12px;display:flex;gap:12px;flex-wrap:wrap}.sw{display:inline-block;width:12px;height:12px;margin-right:4px;vertical-align:middle;border:1px solid #666}
#cap{padding:4px 10px 12px;font-size:12px;color:#333;max-width:1100px}
button{font-size:12px}label{cursor:pointer}
</style></head><body>
<div id="bar"><b>__TITLE__</b>__CLASS__
<span>View: <button data-v="iso">Iso</button> <button data-v="plan">Plan</button> <button data-v="side">Side</button></span>
<span>Vertical x<input id="vx" type="range" min="1" max="20" step="1" value="__VX__" style="width:90px;vertical-align:middle"><span id="vxv">__VX__</span></span>
<span id="filters"></span></div>
<div id="wrap"><canvas id="c"></canvas><div id="tip"></div></div>
<div id="legend"></div><div id="cap">__CAPTION__</div>
<script>
const D=__DATA__;
const cv=document.getElementById('c'),ctx=cv.getContext('2d'),tip=document.getElementById('tip');
let yaw=-0.8,pitch=0.55,zoom=1,panX=0,panY=0,vx=__VX__,drawn=[],hidden={};
const keys=['state','group'];
function filters(){const f=document.getElementById('filters');let h='';for(const k of keys){const vals=[...new Set(D.parts.map(p=>p[k]))];for(const v of vals){h+='<label><input type="checkbox" checked data-k="'+k+'" data-v="'+v+'"> '+v+'</label> ';}}f.innerHTML=h;f.querySelectorAll('input').forEach(i=>i.onchange=()=>{hidden[i.dataset.k+':'+i.dataset.v]=!i.checked;draw();});}
function legend(){let h='';for(const l of D.legend){h+='<span><span class="sw" style="background:'+l[1]+'"></span>'+l[0]+'</span>';}document.getElementById('legend').innerHTML=h;}
function proj(p){const c=Math.cos(yaw),s=Math.sin(yaw);const x1=p[0]*c-p[1]*s,y1=p[0]*s+p[1]*c,z=p[2]*vx;const cp=Math.cos(pitch),sp=Math.sin(pitch);return[x1,-(y1*sp+z*cp),y1*cp-z*sp];}
function draw(){const w=cv.clientWidth,h=cv.clientHeight;cv.width=w*devicePixelRatio;cv.height=h*devicePixelRatio;ctx.setTransform(devicePixelRatio,0,0,devicePixelRatio,0,0);ctx.clearRect(0,0,w,h);
const tris=[];let mnx=1e30,mxx=-1e30,mny=1e30,mxy=-1e30;
D.parts.forEach((p,pi)=>{if(hidden['state:'+p.state]||hidden['group:'+p.group])return;const t=p.t;for(let i=0;i<t.length;i+=9){const a=proj([t[i],t[i+1],t[i+2]]),b=proj([t[i+3],t[i+4],t[i+5]]),c=proj([t[i+6],t[i+7],t[i+8]]);
const ux=b[0]-a[0],uy=b[1]-a[1],uz=b[2]-a[2],wx=c[0]-a[0],wy=c[1]-a[1],wz=c[2]-a[2];const nx=uy*wz-uz*wy,ny=uz*wx-ux*wz,nz=ux*wy-uy*wx;const nl=Math.hypot(nx,ny,nz)||1;
const sh=0.55+0.45*Math.abs((0.3*nx-0.5*ny-0.8*nz)/nl);tris.push([a,b,c,(a[2]+b[2]+c[2])/3,pi,sh]);for(const q of [a,b,c]){mnx=Math.min(mnx,q[0]);mxx=Math.max(mxx,q[0]);mny=Math.min(mny,q[1]);mxy=Math.max(mxy,q[1]);}}});
if(!tris.length)return;const sc=0.9*Math.min(w/(mxx-mnx||1),h/(mxy-mny||1))*zoom,ox=w/2-sc*(mnx+mxx)/2+panX,oy=h/2-sc*(mny+mxy)/2+panY;
tris.sort((p,q)=>q[3]-p[3]);drawn=[];for(const t of tris){const p=D.parts[t[4]],c=p.c;const P=[t[0],t[1],t[2]].map(q=>[ox+sc*q[0],oy+sc*q[1]]);
ctx.fillStyle='rgba('+Math.round(c[0]*255*t[5])+','+Math.round(c[1]*255*t[5])+','+Math.round(c[2]*255*t[5])+','+c[3]+')';ctx.beginPath();ctx.moveTo(P[0][0],P[0][1]);ctx.lineTo(P[1][0],P[1][1]);ctx.lineTo(P[2][0],P[2][1]);ctx.closePath();ctx.fill();if(c[3]>=1){ctx.strokeStyle=ctx.fillStyle;ctx.lineWidth=0.5;ctx.stroke();}drawn.push([P,t[4]]);}
ctx.fillStyle='#111';ctx.font='11px Segoe UI,Arial';for(const p of D.parts){if(!p.lbl||hidden['state:'+p.state]||hidden['group:'+p.group])continue;const q=proj(p.a);ctx.fillText(p.label,ox+sc*q[0]+4,oy+sc*q[1]-4);}}
function inside(pt,P){const s=(a,b,c)=>(a[0]-c[0])*(b[1]-c[1])-(b[0]-c[0])*(a[1]-c[1]);const d1=s(pt,P[0],P[1]),d2=s(pt,P[1],P[2]),d3=s(pt,P[2],P[0]);return !(((d1<0)||(d2<0)||(d3<0))&&((d1>0)||(d2>0)||(d3>0)));}
let drag=null;cv.onmousedown=e=>{drag=[e.clientX,e.clientY,e.shiftKey];cv.style.cursor='grabbing';};window.onmouseup=()=>{drag=null;cv.style.cursor='grab';};
cv.onmousemove=e=>{const r=cv.getBoundingClientRect();if(drag){const dx=e.clientX-drag[0],dy=e.clientY-drag[1];if(drag[2]){panX+=dx;panY+=dy;}else{yaw+=dx*0.01;pitch=Math.max(-0.05,Math.min(Math.PI/2,pitch+dy*0.01));}drag=[e.clientX,e.clientY,drag[2]];draw();return;}
const pt=[e.clientX-r.left,e.clientY-r.top];for(let i=drawn.length-1;i>=0;i--){if(inside(pt,drawn[i][0])){const p=D.parts[drawn[i][1]];let h='<table>';for(const k in p.info){h+='<tr><td>'+k+'</td><td>'+String(p.info[k]).replace(/</g,'&lt;')+'</td></tr>';}tip.innerHTML=h+'</table>';tip.style.left=(pt[0]+14)+'px';tip.style.top=(pt[1]+14)+'px';tip.style.display='block';return;}}tip.style.display='none';};
cv.onwheel=e=>{e.preventDefault();zoom*=e.deltaY<0?1.1:1/1.1;draw();};
document.querySelectorAll('button[data-v]').forEach(b=>b.onclick=()=>{const v=b.dataset.v;if(v==='plan'){yaw=0;pitch=Math.PI/2;}else if(v==='side'){yaw=0;pitch=0;}else{yaw=-0.8;pitch=0.55;}panX=panY=0;zoom=1;draw();});
document.getElementById('vx').oninput=e=>{vx=+e.target.value;document.getElementById('vxv').textContent=vx;draw();};
window.onresize=draw;filters();legend();draw();
</script></body></html>
"""


def _legend_entries(scene: AssetScene, color_by: ColorBy | None) -> list[list[str]]:
    if color_by is not None:
        unit = f" {color_by.unit}" if color_by.unit and color_by.unit != "-" else ""
        return [
            [f"{v:.3g}{unit}", hex_color(c)] for v, c in color_by.legend_stops()
        ] + [["no value", "#d9d9d9"]]
    states = [s for s in STATE_LABELS if any(o["state"] == s for o in scene.objects)]
    return [
        [STATE_LABELS[s], hex_color(object_color({"state": s, "group": "facility"}))]
        for s in states
    ]


LABEL_KINDS = (
    "vessel",
    "column",
    "compressor",
    "pump",
    "heat_exchanger",
    "host",
    "template",
    "manifold",
    "plem",
    "plet",
    "well",
    "equipment",
)


def write_html(
    scene: AssetScene,
    path: Any,
    color_by: ColorBy | None = None,
    vertical_exaggeration: float = 1.0,
    caption: str | None = None,
    label_kinds: Sequence[str] = LABEL_KINDS,
    min_feature: float | None = None,
    routing: str = "auto",
) -> Path:
    """Write the offline interactive viewer (rotate, pan with Shift, zoom, hover for provenance).

    Small objects on a field-scale scene are enlarged for display (``min_feature``,
    automatic by default); the hover table and GLB keep true sizes.
    """
    from .report import scene_caption

    floor = min_feature if min_feature is not None else auto_min_feature(scene)
    parts = scene_parts(scene, color_by, 1.0, floor, routing)
    b = scene.bounds()
    origin = [(b[0] + b[3]) / 2.0, (b[1] + b[4]) / 2.0, (b[2] + b[5]) / 2.0]
    payload_parts = []
    for part in parts:
        verts, faces = part["mesh"]
        flat: list[float] = []
        for f in faces:
            for i in f:
                v = verts[i]
                flat.extend(round(v[k] - origin[k], 3) for k in range(3))
        payload_parts.append(
            {
                "id": part["id"],
                "label": part["label"],
                "state": part["state"],
                "group": part["group"],
                "c": [round(c, 3) for c in part["color"]],
                "t": flat,
                "info": part["info"],
                "a": [round(part["anchor"][k] - origin[k], 3) for k in range(3)],
                "lbl": part["kind"] in label_kinds,
            }
        )
    data = json.dumps(
        {"parts": payload_parts, "legend": _legend_entries(scene, color_by)},
        separators=(",", ":"),
    )
    data = data.replace("</", "<\\/")
    text = caption or scene_caption(
        scene,
        color_by=color_by,
        view="interactive",
        vertical_exaggeration=vertical_exaggeration,
        enlarged=bool(floor),
        routing=routing_summary({p["id"]: p["route"] for p in parts if p.get("route")}),
    )
    cls = (
        f' <span id="cls">{_escape(scene.classification)}</span>'
        if scene.classification
        else ""
    )
    html = (
        _HTML.replace("__DATA__", data)
        .replace("__TITLE__", _escape(scene.name))
        .replace("__CLASS__", cls)
        .replace("__CAPTION__", _escape(text))
        .replace("__VX__", str(int(max(1, round(vertical_exaggeration)))))
    )
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return out


def _escape(text: Any) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ------------------------------------------------------------------------- PNG
VIEWS = {"iso": (25.0, -60.0), "plan": (90.0, -90.0), "elevation": (0.0, -90.0)}


def render_png(
    scene: AssetScene,
    path: Any,
    view: str = "iso",
    color_by: ColorBy | None = None,
    vertical_exaggeration: float = 1.0,
    max_labels: int = 25,
    title: str | None = None,
    dpi: int = 160,
    min_feature: float | None = None,
    label_kinds: Sequence[str] = LABEL_KINDS,
    routing: str = "auto",
) -> dict[str, Any]:
    """Render a PNG with legend and classification mark; returns ``{"path", "caption"}``.

    Needs matplotlib (optional dependency). Small objects on field-scale scenes
    are enlarged for display (stated in the caption).
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LinearSegmentedColormap, Normalize
    from matplotlib.patches import Patch
    from matplotlib.ticker import MaxNLocator
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    from .report import scene_caption

    if view not in VIEWS:
        raise ValueError(f"view must be one of {tuple(VIEWS)}")
    floor = min_feature if min_feature is not None else auto_min_feature(scene)
    parts = scene_parts(scene, color_by, vertical_exaggeration, floor, routing)
    fig = plt.figure(figsize=(10, 7.5))
    ax = fig.add_subplot(111, projection="3d")
    all_v: list[Sequence[float]] = []
    for part in parts:
        verts, faces = part["mesh"]
        if not faces:
            continue
        polys = [[verts[i] for i in f] for f in faces]
        coll = Poly3DCollection(
            polys, facecolors=[part["color"]], edgecolors="none", linewidths=0
        )
        coll.set_alpha(part["color"][3])
        ax.add_collection3d(coll)
        all_v.extend(verts)
    if all_v:
        mins = [min(v[i] for v in all_v) for i in range(3)]
        maxs = [max(v[i] for v in all_v) for i in range(3)]
        span = [max(maxs[i] - mins[i], 1e-6) for i in range(3)]
        pad = [0.05 * span[0], 0.05 * span[1], 0.02 * span[2]]
        ax.set_xlim(mins[0] - pad[0], maxs[0] + pad[0])
        ax.set_ylim(mins[1] - pad[1], maxs[1] + pad[1])
        ax.set_zlim(mins[2] - pad[2], maxs[2] + pad[2])
        ax.set_box_aspect(
            (span[0], span[1], max(span[2], 0.15 * max(span[0], span[1])))
        )
    labelled = [p for p in parts if p["kind"] in label_kinds][:max_labels]
    for part in labelled:
        a = part["anchor"]
        ax.text(
            a[0],
            a[1],
            a[2] * vertical_exaggeration,
            " " + str(part["label"]),
            fontsize=7,
            zorder=10,
        )
    for axis in (ax.xaxis, ax.yaxis, ax.zaxis):
        axis.set_major_locator(MaxNLocator(5))
    elev, azim = VIEWS[view]
    ax.view_init(elev=elev, azim=azim)
    ax.set_xlabel("x [m]")
    ax.set_ylabel("y [m]")
    ax.set_zlabel(
        "z [m]"
        + (f" (x{vertical_exaggeration:g})" if vertical_exaggeration != 1.0 else "")
    )
    if color_by is not None:
        stops = color_by.legend_stops(7)
        cmap = LinearSegmentedColormap.from_list("asset", [c[:3] for _, c in stops])
        sm = plt.cm.ScalarMappable(cmap=cmap, norm=Normalize(stops[0][0], stops[-1][0]))
        sm.set_array([])
        cb = fig.colorbar(sm, ax=ax, shrink=0.6, pad=0.08)
        cb.set_label(color_by.label + (f" [{color_by.unit}]" if color_by.unit else ""))
    else:
        handles = [
            Patch(
                facecolor=hex_color(object_color({"state": s, "group": "facility"})),
                label=STATE_LABELS[s],
            )
            for s in STATE_LABELS
            if any(o["state"] == s for o in scene.objects)
        ]
        if handles:
            ax.legend(handles=handles, loc="upper left", fontsize=8)
    ax.set_title(title or scene.name, fontsize=11)
    if scene.classification:
        fig.text(
            0.99,
            0.99,
            scene.classification,
            ha="right",
            va="top",
            color="#b00020",
            fontsize=9,
            weight="bold",
        )
    fig.text(
        0.01,
        0.01,
        "Schematic illustration - not for measurement",
        fontsize=7,
        color="#555",
    )
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return {
        "path": str(out),
        "caption": scene_caption(
            scene,
            color_by=color_by,
            view=view,
            vertical_exaggeration=vertical_exaggeration,
            enlarged=bool(floor),
            routing=routing_summary(
                {p["id"]: p["route"] for p in parts if p.get("route")}
            ),
        ),
    }


def render_all(
    scene: AssetScene,
    out_dir: Any,
    stem: str = "asset_scene",
    color_by: ColorBy | None = None,
    views: Sequence[str] = ("iso", "plan"),
    vertical_exaggeration: float = 1.0,
    routing: str = "auto",
) -> dict[str, Any]:
    """Write scene JSON, GLB, HTML and PNG views into ``out_dir``; returns paths and captions."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    result: dict[str, Any] = {
        "scene_json": str(scene.save(out / f"{stem}.json")),
        "glb": str(
            write_glb(
                scene, out / f"{stem}.glb", color_by, vertical_exaggeration, routing
            )
        ),
        "html": str(
            write_html(
                scene,
                out / f"{stem}.html",
                color_by,
                vertical_exaggeration,
                routing=routing,
            )
        ),
        "png": [],
    }
    try:
        import matplotlib  # noqa: F401
    except ImportError:
        result["warnings"] = ["matplotlib not installed; PNG views skipped"]
        return result
    for view in views:
        result["png"].append(
            render_png(
                scene,
                out / f"{stem}_{view}.png",
                view,
                color_by,
                vertical_exaggeration,
                routing=routing,
            )
        )
    return result
