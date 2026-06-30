# CubeTrek Integration: API Keys, Licensing & Distribution

Analysis of three practical questions before implementing CubeTrek-style 3D GPX
visualization in MytraL.

Sources examined:
- CubeTrek: `/home/dvorka/p/mytral/git/cube-trek/CubeTrek`
- TopoLibrary: `/home/dvorka/p/mytral/git/cube-trek/TopoLibrary`

---

## 1. API Keys Needed?

**MapTiler key: YES — but avoidable.**

CubeTrek uses MapTiler as the **map tile texture** painted onto the 3D terrain
mesh (satellite imagery + street map). The GLTF terrain geometry and elevation
data need **no key at all** — they come from NASA SRTM public domain data.

| Component | Key needed? | Notes |
|---|---|---|
| SRTM elevation data (terrain mesh) | ❌ None | NASA public domain, free download |
| MapTiler tiles (texture on terrain) | ✅ Required by CubeTrek | Free tier: 100k tiles/month |
| OSM raster tiles (alternative texture) | ❌ None | Slightly less polished, attribution required |
| Stamen Terrain tiles (another alt.) | ❌ None | Good for hiking/cycling |
| Babylon.js (3D renderer) | ❌ None | Apache 2.0, bundle locally |

**Practical recommendation:** ship MytraL with **OSM raster tiles as default**
(zero config for users), and let users optionally set a MapTiler key in settings
for the full satellite-imagery experience. This means most users need no API key
at all.

---

## 2. Can It Be Freely Distributed in MytraL?

**There is a legal wrinkle — but a clean solution exists.**

**CubeTrek** is licensed **GPL v2** (no "or later" clause in the LICENSE file,
and source headers show only an IDE placeholder, not an explicit license
statement). GPL v2 is **not compatible with AGPL v3** (MytraL's license), so
translated/derived Java code from CubeTrek cannot be incorporated into MytraL
directly.

**TopoLibrary** has no LICENSE file; source headers show only the IDE default
`"To change this license header"` placeholder. **No license = all rights
reserved by default.** This is the bigger concern.

### The Clean Solution — Independent Reimplementation

Algorithms themselves are **not copyrightable** under law — only the specific
code expression is. The approach is to:

- Use the TopoLibrary source as **algorithm documentation** (reference/inspiration)
- Write fresh, original Python code implementing the same mathematical procedures
- This is the same as reading a paper about Ramer-Douglas-Peucker and
  implementing it yourself — clearly not a derivative work

This is how virtually every open source port is done. The algorithms (haversine,
HGT binary format, Web Mercator tiles, triangle mesh from grid) are well-known
public domain mathematics — none of it is novel to TopoLibrary.

### All Other Components Are Clean

| Component | License | Distributable in AGPL v3 MytraL? |
|---|---|---|
| Babylon.js | Apache 2.0 | ✅ Yes |
| gpxpy | MIT | ✅ Yes |
| fitdecode | MIT | ✅ Yes |
| pygltflib | MIT | ✅ Yes |
| numpy | BSD | ✅ Yes |
| NASA SRTM data | Public domain | ✅ Yes |
| MapTiler tiles | Commercial ToS | ✅ Used via API, not redistributed |
| OSM tile data | ODbL | ✅ Yes with attribution |

### Recommended Action

Contact the TopoLibrary/CubeTrek author (r-follador on GitHub) and ask them to
add an explicit license — or simply ask permission. Given it is already a public
GitHub repo used as a library, they almost certainly intend it to be freely
usable.

---

## 3. Will Distribution Be Smooth for Users?

**Mostly yes — with one first-run moment.**

| Concern | Impact | Solution |
|---|---|---|
| Python dependencies | ✅ Zero friction | gpxpy, numpy, pygltflib — pure Python, `pip install` |
| Babylon.js / map3d.js | ✅ Zero friction | Copy 18.8 KB JS file to `mytral/static/js/` once, ships with app |
| MapTiler API key | ⚠️ Optional config | Default to OSM tiles (no key); users add key for satellite |
| SRTM elevation files | ⚠️ One-time download | ~5–15 MB per activity region, auto-downloaded on first 3D view |
| PythonAnywhere hosting | ✅ Fine | On-demand HGT downloads stored in data dir |
| PyInstaller desktop app | ✅ Fine | HGT files download to `~/.mytral/hgt/` on first use |

**The one UX moment:** the very first time a user opens the 3D view for a given
geographic region, MytraL downloads the SRTM tile(s) (~3–5 MB for a typical
alpine track). This is a one-time operation per region, then cached forever. A
simple "Preparing terrain data…" spinner in the UI handles this gracefully.

**Summary:** zero-config for most users (OSM tiles, auto-SRTM download),
completely smooth after first regional use. Optional MapTiler key for satellite
texture for the full CubeTrek look.
