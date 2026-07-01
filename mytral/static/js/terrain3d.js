/**
 * MyTraL 3D terrain viewer — terrain3d.js
 *
 * Initialised by activity-view3d.html via the global `terrainConfig` object:
 *   terrainConfig.activityKey  string  activity UUID
 *   terrainConfig.maptype      string  "osm" | "standard" | "satellite"
 *   terrainConfig.geojsonUrl   string  full URL to the GeoJSON endpoint
 *   terrainConfig.gltfBaseUrl  string  base URL for GLTF (maptype appended as ?maptype=…)
 *
 * Trail is drawn as emissive tubes (a lifted slope-coloured ribbon plus a
 * faint near-surface shadow) in rendering group 1 so it is always visible and
 * never occluded by terrain. The
 * map tiles are rendered mostly unlit (see gltf_writer.py) so the map reads at
 * near-true brightness; lighting only adds gentle relief.
 *
 * Copyright (C) 2022-2026 Martin Dvorak <martin.dvorak@mindforger.com>
 * AGPL v3 — see LICENSE
 */

"use strict";

// --- single place for all look & feel tunables ---
const CONFIG = {
    // lighting / scene — balanced for contrast: map stays readable (emissive
    // floor) while a strong sun adds relief so forest/meadow/rock separate
    hwScaling: 0.75,
    skyColor: [0.26, 0.34, 0.43, 1.0], // medium slate (not light, not black)
    hemiIntensity: 0.4,
    hemiGround: [0.25, 0.25, 0.28],
    sunIntensity: 0.9, // directional relief / shading contrast
    sunDirection: [-0.5, -1.0, -0.35], // fixed NW-ish sun (stable hill-shade)
    ambient: [0.3, 0.3, 0.3],
    exposure: 0.95,
    contrast: 1.4, // separate terrain tones
    mapEmissive: 0.42, // unlit floor so the map is readable in shade
    mapAlbedo: 0.65, // lit term that the sun shades for relief
    // trail — slim depth-tested tube so terrain occludes it where it runs behind
    // a ridge; kept thin so it never looks like a fat worm
    trailRadiusFactor: 0.0011, // slope-coloured core radius (fraction of scene radius)
    trailZOffset: -2, // gentle depth bias against ground z-fighting (precision is tight)
    ribbonLiftM: 8, // small real-world lift above the surface
    // markers & hover dot (sizes as a fraction of scene radius)
    markerBadge: 0.015, // start/finish/peak badge size
    markerStem: 0.015, // pin stem height
    dotCore: 0.00315, // hover dot core radius
    dotHalo: 0.0091, // hover dot glow halo radius
    maxTrackPoints: 2000, // downsample cap for trail/hover/chart/flythrough
    // camera / zoom
    wheelPctFast: 0.03, // slider = 1
    wheelPctSlow: 0.0035, // slider = 20
    autoRotateSpeed: 0.0025,
    flySeconds: 30,
};

let _scene = null;
let _engine = null;
let _camera = null;
let _dirLight = null;
let _terrainMeshes = [];
let _cachedGeojson = null;
let _currentMaptype = terrainConfig.maptype;
let _autoRotating = true;

// scene context shared across helpers
let _sceneCtx = { center: null, radius: 0, sceneParams: null, markerD: 40 };
// downsampled track points in scene space: {x,y,z,dist,ele,grade}
let _trackScenePts = [];
let _hoverMarker = null;
let _hoverHalo = null;
let _tooltip = null;
let _chart = null;

// ---------------------------------------------------------------------------
// Bootstrap
// ---------------------------------------------------------------------------

window.addEventListener("DOMContentLoaded", () => {
    const canvas = document.getElementById("terrainCanvas");
    try {
        _engine = new BABYLON.Engine(canvas, true, { preserveDrawingBuffer: true });
    } catch (e) {
        showError(e);
        return;
    }
    _engine.setHardwareScalingLevel(CONFIG.hwScaling);

    fetchData()
        .then(({ geojson, rootUrl, filename }) => {
            _cachedGeojson = geojson;
            createScene(canvas, geojson, rootUrl, filename)
                .then(() => {
                    _engine.runRenderLoop(() => _scene && _scene.render());
                    hideSpinner();
                })
                .catch(showError);
        })
        .catch(showError);

    window.addEventListener("resize", () => _engine && _engine.resize());

    // map-style toggle buttons
    document.querySelectorAll("[data-maptype]").forEach((btn) => {
        btn.addEventListener("click", () => {
            const mt = btn.dataset.maptype;
            if (mt === _currentMaptype) return;
            _currentMaptype = mt;
            document
                .querySelectorAll("[data-maptype]")
                .forEach((b) => b.classList.toggle("active", b.dataset.maptype === mt));
            reloadTextures(mt);
        });
    });

    // camera preset buttons
    document.querySelectorAll("[data-view]").forEach((btn) => {
        btn.addEventListener("click", () => applyView(btn.dataset.view));
    });

    setupFullscreen();
});

// ---------------------------------------------------------------------------
// Fullscreen toggle (maximizes the 3D card across the whole screen)
// ---------------------------------------------------------------------------

function setupFullscreen() {
    const card = document.getElementById("terrain3dCard");
    const btn = document.getElementById("terrain3dFullscreenBtn");
    if (!card || !btn) return;

    const maximizeSvg = btn.innerHTML;
    const minimizeSvg =
        '<svg xmlns="http://www.w3.org/2000/svg" class="icon icon-tabler' +
        ' icon-tabler-arrows-minimize" width="24" height="24" viewBox="0 0 24 24"' +
        ' stroke-width="2" stroke="currentColor" fill="none" stroke-linecap="round"' +
        ' stroke-linejoin="round"><path stroke="none" d="M0 0h24v24H0z" fill="none"/>' +
        '<path d="M5 9l4 0l0 -4"/><path d="M3 3l6 6"/><path d="M5 15l4 0l0 4"/>' +
        '<path d="M3 21l6 -6"/><path d="M19 9l-4 0l0 -4"/><path d="M15 9l6 -6"/>' +
        '<path d="M19 15l-4 0l0 4"/><path d="M15 15l6 6"/></svg>';

    const setState = (full) => {
        card.classList.toggle("terrain-fullscreen", full);
        btn.innerHTML = full ? minimizeSvg : maximizeSvg;
        btn.title = full ? "Exit fullscreen" : "Fullscreen";
        // Babylon must re-read the canvas size after the card resizes
        if (_engine) setTimeout(() => _engine.resize(), 60);
    };

    btn.addEventListener("click", (event) => {
        event.preventDefault();
        setState(!card.classList.contains("terrain-fullscreen"));
    });
    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && card.classList.contains("terrain-fullscreen")) {
            setState(false);
        }
    });
}

// ---------------------------------------------------------------------------
// Data loading
// ---------------------------------------------------------------------------

async function fetchData() {
    showSpinner("Loading track data…");
    const geoResp = await fetch(terrainConfig.geojsonUrl);
    if (!geoResp.ok) throw new Error(`GeoJSON fetch failed: ${geoResp.status}`);
    const geojson = await geoResp.json();

    const rootUrl = terrainConfig.gltfBaseUrl.replace(/\/[^/]+$/, "/");
    const filename =
        terrainConfig.gltfBaseUrl.replace(/.*\//, "") + `?maptype=${_currentMaptype}`;
    return { geojson, rootUrl, filename };
}

// ---------------------------------------------------------------------------
// Scene creation
// ---------------------------------------------------------------------------

async function createScene(canvas, geojson, rootUrl, filename) {
    _scene = new BABYLON.Scene(_engine);
    _scene.clearColor = new BABYLON.Color4(...CONFIG.skyColor);
    applySceneLook(_scene);
    setupLights(_scene);

    const { center, radius } = await loadTerrain(_scene, rootUrl, filename);
    const sp = geojson.properties && geojson.properties.scene;
    _sceneCtx = { center, radius, sceneParams: sp, markerD: radius * 0.012 };

    setupCamera(canvas, _scene, center, radius);

    if (sp) {
        _trackScenePts = buildTrackScenePoints(_scene, geojson, sp);
        buildTrail(_scene, _trackScenePts, sp);
        placeSignposts(_scene, geojson, sp);
        setupHoverTracking(_scene);
        setupChart();
    }

    setupAutoRotate(canvas);
}

function applySceneLook(scene) {
    const ip = scene.imageProcessingConfiguration;
    ip.toneMappingEnabled = true;
    ip.toneMappingType = BABYLON.ImageProcessingConfiguration.TONEMAPPING_ACES;
    ip.exposure = CONFIG.exposure;
    ip.contrast = CONFIG.contrast;
}

function setupLights(scene) {
    const hemi = new BABYLON.HemisphericLight(
        "hemi",
        new BABYLON.Vector3(0, 1, 0),
        scene
    );
    hemi.intensity = CONFIG.hemiIntensity;
    hemi.groundColor = new BABYLON.Color3(...CONFIG.hemiGround);

    // fixed sun — stable hill-shade from one direction (no per-frame swinging)
    _dirLight = new BABYLON.DirectionalLight(
        "sun",
        new BABYLON.Vector3(...CONFIG.sunDirection),
        scene
    );
    _dirLight.intensity = CONFIG.sunIntensity;
    scene.ambientColor = new BABYLON.Color3(...CONFIG.ambient);
}

function collectTerrainMeshes(result) {
    // collect only meshes that carry UVs (the textured terrain tiles) and apply
    // the look from CONFIG: a partial emissive floor (map readable in shade) plus
    // a lit albedo term that the sun shades for relief/contrast
    const meshes = [];
    const emiss = new BABYLON.Color3(
        CONFIG.mapEmissive,
        CONFIG.mapEmissive,
        CONFIG.mapEmissive
    );
    const albedo = new BABYLON.Color3(
        CONFIG.mapAlbedo,
        CONFIG.mapAlbedo,
        CONFIG.mapAlbedo
    );
    result.meshes.forEach((parent) => {
        parent.getChildren().forEach((mesh) => {
            if (!mesh.getVerticesData(BABYLON.VertexBuffer.UVKind)) return;
            const mat = mesh.material;
            if (mat) {
                if (mat.emissiveColor) mat.emissiveColor = emiss;
                if ("albedoColor" in mat) mat.albedoColor = albedo;
            }
            meshes.push(mesh);
        });
    });
    return meshes;
}

async function loadTerrain(scene, rootUrl, filename) {
    showSpinner("Loading terrain mesh…");
    const result = await BABYLON.SceneLoader.ImportMeshAsync(
        "",
        rootUrl,
        filename,
        scene,
        null,
        ".gltf"
    );
    _terrainMeshes = collectTerrainMeshes(result);

    let minWorld = null;
    let maxWorld = null;
    for (const m of _terrainMeshes) {
        m.refreshBoundingInfo();
        const bb = m.getBoundingInfo().boundingBox;
        if (!minWorld) {
            minWorld = bb.minimumWorld.clone();
            maxWorld = bb.maximumWorld.clone();
        } else {
            minWorld = BABYLON.Vector3.Minimize(minWorld, bb.minimumWorld);
            maxWorld = BABYLON.Vector3.Maximize(maxWorld, bb.maximumWorld);
        }
    }

    const center = minWorld
        ? BABYLON.Vector3.Center(minWorld, maxWorld)
        : BABYLON.Vector3.Zero();
    const radius = minWorld ? maxWorld.subtract(minWorld).length() : 5000;
    return { center, radius };
}

function setupCamera(canvas, scene, center, radius) {
    const initRadius = radius * 1.5;
    _camera = new BABYLON.ArcRotateCamera(
        "cam",
        -Math.PI / 6,
        Math.PI / 3.5,
        initRadius,
        center,
        scene
    );
    // tight near/far ratio (~3000:1) for crisp depth precision so the trail is
    // cleanly occluded by ridges without z-fighting against the ground
    _camera.minZ = radius * 0.01;
    _camera.maxZ = radius * 30;
    _camera.lowerRadiusLimit = radius * 0.02;
    _camera.upperRadiusLimit = radius * 10;
    _camera.upperBetaLimit = Math.PI / 2 - 0.02;
    // uniform, distance-proportional zoom (consistent feel at every scale)
    _camera.wheelDeltaPercentage = wheelPctFromSlider(readZoomSlider());
    _camera.useNaturalPinchZoom = true;
    _camera.panningSensibility = (1 / radius) * 500;
    _camera.panningInertia = 0.7;
    _camera.attachControl(canvas, true);
}

// ---------------------------------------------------------------------------
// Track → scene-space points (drape onto the surface via ray-cast)
// ---------------------------------------------------------------------------

function sceneXZ(lat, lon, sp) {
    // the glTF loader's __root__ node negates world X (z-flip + 180° Y rotation)
    // to convert glTF right-handed coords to Babylon's left-handed system, so X
    // must be negated here for the trail/markers to align with the terrain map
    return {
        x: -(lat - sp.center_lat) * sp.meters_per_degree_lat * sp.scale_factor,
        z: (lon - sp.center_lon) * sp.meters_per_degree_lon * sp.scale_factor,
    };
}

function analyticY(ele, sp) {
    // fallback when a ray-cast misses the terrain (mirrors mesh_builder.py)
    return (
        (ele - (sp.terrain_min_elevation_m - sp.height_offset_m)) *
        sp.scale_factor *
        sp.z_exaggeration
    );
}

function surfaceY(scene, x, z) {
    const ray = new BABYLON.Ray(
        new BABYLON.Vector3(x, 1e5, z),
        new BABYLON.Vector3(0, -1, 0),
        2e5
    );
    const hit = scene.pickWithRay(ray, (m) => _terrainMeshes.indexOf(m) !== -1);
    return hit && hit.hit ? hit.pickedPoint.y : null;
}

function buildTrackScenePoints(scene, geojson, sp) {
    const coords = geojson.geometry.coordinates || [];
    if (coords.length < 2) return [];

    // downsample to keep ray-casts, ribbon, hover scan and chart light
    const step = Math.max(1, Math.ceil(coords.length / CONFIG.maxTrackPoints));
    const sampled = [];
    for (let i = 0; i < coords.length; i += step) sampled.push(coords[i]);
    if (sampled[sampled.length - 1] !== coords[coords.length - 1]) {
        sampled.push(coords[coords.length - 1]);
    }

    const pts = [];
    let prevY = null;
    for (let i = 0; i < sampled.length; i++) {
        const lon = sampled[i][0];
        const lat = sampled[i][1];
        const ele = sampled[i][2];
        const dist = sampled[i][4];
        const { x, z } = sceneXZ(lat, lon, sp);
        let y = surfaceY(scene, x, z);
        if (y === null) y = prevY !== null ? prevY : analyticY(ele, sp);
        prevY = y;
        // drop points coincident in XZ with the previous one — a degenerate
        // tube segment would otherwise crash CreateTube and blank the scene
        const last = pts[pts.length - 1];
        if (last && last.x === x && last.z === z) continue;
        pts.push({ x, y, z, dist, ele, grade: 0 });
    }
    // per-point slope (%) from distance/elevation deltas
    for (let i = 1; i < pts.length; i++) {
        const dd = pts[i].dist - pts[i - 1].dist;
        pts[i].grade = dd > 0 ? ((pts[i].ele - pts[i - 1].ele) / dd) * 100 : 0;
    }
    if (pts.length > 1) pts[0].grade = pts[1].grade;
    return pts;
}

// ---------------------------------------------------------------------------
// Trail rendering — lifted gradient ribbon + faint surface shadow
// ---------------------------------------------------------------------------

// emissive tube material that is depth-tested (so terrain occludes the trail)
// but biased toward the camera with zOffset to avoid z-fighting with the ground
function trailMat(scene, name, color) {
    const mat = new BABYLON.StandardMaterial(name, scene);
    mat.disableLighting = true; // unlit → vivid regardless of scene lighting
    mat.emissiveColor = color;
    mat.zOffset = CONFIG.trailZOffset;
    return mat;
}

function buildTrail(scene, pts, sp) {
    if (pts.length < 2) return;
    const lift = CONFIG.ribbonLiftM * sp.scale_factor * sp.z_exaggeration;
    const core = Math.max(_sceneCtx.radius * CONFIG.trailRadiusFactor, 1e-6);
    const liftPts = pts.map((p) => new BABYLON.Vector3(p.x, p.y + lift, p.z));

    // slope-coloured tube: one tube per contiguous colour run, merged per colour.
    // depth-tested (default group) so the terrain occludes it behind ridges.
    // (no concentric dark casing — a wider casing tube would enclose and hide
    // the coloured core now that the trail is no longer drawn always-on-top)
    const colorHex = pts.map((p) => MytralProfileChart.gradeColorHex(p.grade));
    const tubesByColor = {};
    let runStart = 0;
    for (let i = 1; i <= pts.length; i++) {
        if (i === pts.length || colorHex[i] !== colorHex[runStart]) {
            const endExcl = Math.min(i + 1, pts.length); // connect adjacent runs
            const path = liftPts.slice(runStart, endExcl);
            if (path.length >= 2) {
                const tube = BABYLON.MeshBuilder.CreateTube(
                    "trailRun",
                    { path, radius: core, tessellation: 8, cap: BABYLON.Mesh.NO_CAP },
                    scene
                );
                const hex = colorHex[runStart];
                if (!tubesByColor[hex]) tubesByColor[hex] = [];
                tubesByColor[hex].push(tube);
            }
            runStart = i;
        }
    }
    for (const hex in tubesByColor) {
        const merged = BABYLON.Mesh.MergeMeshes(tubesByColor[hex], true, true);
        if (!merged) continue;
        merged.material = trailMat(scene, "trailMat_" + hex, BABYLON.Color3.FromHexString(hex));
        merged.isPickable = false;
    }
}

// ---------------------------------------------------------------------------
// Track label signposts (start, finish, highest point)
// ---------------------------------------------------------------------------

// draw a clean coin-style badge (filled circle + white ring + glyph, and an
// optional caption underneath) onto a DynamicTexture for a billboarded marker
function makeBadgeTexture(scene, name, fill, glyph, caption) {
    const S = 256;
    const dt = new BABYLON.DynamicTexture(
        name,
        { width: S, height: caption ? S + 90 : S },
        scene,
        true
    );
    const ctx = dt.getContext();
    const cx = S / 2;
    const cy = S / 2;
    const r = S / 2 - 18;
    // soft drop shadow
    ctx.beginPath();
    ctx.arc(cx, cy + 6, r, 0, Math.PI * 2);
    ctx.fillStyle = "rgba(0,0,0,0.35)";
    ctx.fill();
    // coin
    ctx.beginPath();
    ctx.arc(cx, cy, r, 0, Math.PI * 2);
    ctx.fillStyle = fill;
    ctx.fill();
    ctx.lineWidth = 14;
    ctx.strokeStyle = "#ffffff";
    ctx.stroke();
    // glyph
    ctx.fillStyle = "#ffffff";
    ctx.font = "bold 150px Helvetica, Arial, sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(glyph, cx, cy + 6);
    if (caption) {
        ctx.font = "bold 56px Helvetica, Arial, sans-serif";
        ctx.fillStyle = "#ffffff";
        ctx.strokeStyle = "rgba(0,0,0,0.55)";
        ctx.lineWidth = 8;
        ctx.strokeText(caption, cx, S + 44);
        ctx.fillText(caption, cx, S + 44);
    }
    dt.update();
    return { dt, aspect: (caption ? S + 90 : S) / S };
}

function placeSignposts(scene, geojson, sp) {
    const labels = geojson.properties && geojson.properties.labels;
    if (!labels) return;

    const badge = _sceneCtx.radius * CONFIG.markerBadge;
    const stem = _sceneCtx.radius * CONFIG.markerStem;
    // start = green "S", finish = red "F", peak = amber "▲" + elevation caption
    const styles = {
        start: { fill: "#2fb344", glyph: "S", caption: null },
        end: { fill: "#d63939", glyph: "F", caption: null },
        highest: { fill: "#f59f00", glyph: "▲", caption: null },
    };

    ["start", "highest", "end"].forEach((key) => {
        const lbl = labels[key];
        const style = styles[key];
        if (!lbl || !style) return;

        const { x: sx, z: sz } = sceneXZ(lbl.lat, lbl.lon, sp);
        const sy = surfaceY(scene, sx, sz);
        if (sy === null) return;

        const caption = key === "highest" ? lbl.label : null;
        const { dt, aspect } = makeBadgeTexture(
            scene,
            "badge_" + key,
            style.fill,
            style.glyph,
            caption
        );
        const mat = new BABYLON.StandardMaterial("badgeMat_" + key, scene);
        mat.diffuseTexture = dt;
        mat.diffuseTexture.hasAlpha = true;
        mat.emissiveColor = new BABYLON.Color3(1, 1, 1);
        mat.disableLighting = true;
        mat.useAlphaFromDiffuseTexture = true;
        mat.backFaceCulling = false;
        // depth-tested (shared group) so the badge is occluded behind a mountain,
        // not floating in front of it — matches the trail and the hover dot

        const plane = BABYLON.MeshBuilder.CreatePlane(
            "badge_" + key,
            { width: badge, height: badge * aspect },
            scene
        );
        plane.material = mat;
        plane.billboardMode = BABYLON.Mesh.BILLBOARDMODE_ALL;
        plane.position = new BABYLON.Vector3(sx, sy + stem + badge * 0.5, sz);
        plane.isPickable = false;

        // thin pin stem from the surface up to the badge
        const stemMesh = BABYLON.MeshBuilder.CreateCylinder(
            "stem_" + key,
            { height: stem, diameter: _sceneCtx.radius * 0.002 },
            scene
        );
        const stemMat = new BABYLON.StandardMaterial("stemMat_" + key, scene);
        stemMat.disableLighting = true;
        stemMat.emissiveColor = BABYLON.Color3.FromHexString(style.fill).scale(0.7);
        stemMesh.material = stemMat;
        stemMesh.position = new BABYLON.Vector3(sx, sy + stem * 0.5, sz);
        stemMesh.isPickable = false;
    });
}

// ---------------------------------------------------------------------------
// Hover tracking (linear nearest scan — no KD-tree, single ray-cast per move)
// ---------------------------------------------------------------------------

function setupHoverTracking(scene) {
    if (_trackScenePts.length < 2) return;
    const R = _sceneCtx.radius;

    // glowing accent halo (radial-gradient disc, billboarded) behind a white core
    const haloDt = new BABYLON.DynamicTexture("haloDt", 256, scene, true);
    const hctx = haloDt.getContext();
    const grd = hctx.createRadialGradient(128, 128, 10, 128, 128, 124);
    grd.addColorStop(0, "rgba(255,150,30,0.95)");
    grd.addColorStop(0.45, "rgba(255,150,30,0.45)");
    grd.addColorStop(1, "rgba(255,150,30,0)");
    hctx.fillStyle = grd;
    hctx.fillRect(0, 0, 256, 256);
    haloDt.update();
    const haloMat = new BABYLON.StandardMaterial("haloMat", scene);
    haloMat.diffuseTexture = haloDt;
    haloMat.diffuseTexture.hasAlpha = true;
    haloMat.emissiveColor = new BABYLON.Color3(1, 1, 1);
    haloMat.disableLighting = true;
    haloMat.useAlphaFromDiffuseTexture = true;
    haloMat.backFaceCulling = false;
    // depth-tested (shared group) so the dot is occluded when the hovered point
    // is behind a mountain — matching the trail, not floating in front of peaks
    _hoverHalo = BABYLON.MeshBuilder.CreatePlane(
        "hoverHalo",
        { size: R * CONFIG.dotHalo * 2 },
        scene
    );
    _hoverHalo.material = haloMat;
    _hoverHalo.billboardMode = BABYLON.Mesh.BILLBOARDMODE_ALL;
    _hoverHalo.isVisible = false;
    _hoverHalo.isPickable = false;

    const markerMat = new BABYLON.StandardMaterial("markerMat", scene);
    markerMat.emissiveColor = new BABYLON.Color3(1.0, 0.55, 0.05); // vivid orange core
    markerMat.disableLighting = true;
    _hoverMarker = BABYLON.MeshBuilder.CreateSphere(
        "hoverMarker",
        { diameter: R * CONFIG.dotCore * 2 },
        scene
    );
    _hoverMarker.material = markerMat;
    _hoverMarker.isVisible = false;
    _hoverMarker.isPickable = false;

    // gentle pulse on the halo so the position is easy to spot
    let pulse = 0;
    scene.onBeforeRenderObservable.add(() => {
        if (!_hoverHalo || !_hoverHalo.isVisible) return;
        pulse += _engine.getDeltaTime() * 0.005;
        const s = 1 + 0.18 * Math.sin(pulse);
        _hoverHalo.scaling.set(s, s, s);
    });

    _tooltip = document.getElementById("trackTooltip");
    const canvas = scene.getEngine().getRenderingCanvas();

    scene.onPointerObservable.add((pi) => {
        if (pi.type !== BABYLON.PointerEventTypes.POINTERMOVE) return;
        const hit = scene.pick(
            scene.pointerX,
            scene.pointerY,
            (m) => _terrainMeshes.indexOf(m) !== -1
        );
        if (!hit || !hit.hit) {
            hideHover();
            return;
        }
        const idx = nearestTrackIdx(hit.pickedPoint.x, hit.pickedPoint.z);
        if (idx < 0) {
            hideHover();
            return;
        }
        showHoverAt(idx, false);
    });

    canvas.addEventListener("mouseleave", () => hideHover());
}

function nearestTrackIdx(x, z) {
    let best = -1;
    let bestD = Infinity;
    for (let i = 0; i < _trackScenePts.length; i++) {
        const dx = _trackScenePts[i].x - x;
        const dz = _trackScenePts[i].z - z;
        const d = dx * dx + dz * dz;
        if (d < bestD) {
            bestD = d;
            best = i;
        }
    }
    return best;
}

function showHoverAt(idx, fromChart) {
    const p = _trackScenePts[idx];
    if (!p) return;
    const lift = _sceneCtx.radius * CONFIG.dotCore;
    if (_hoverMarker) {
        _hoverMarker.position.set(p.x, p.y + lift, p.z);
        _hoverMarker.isVisible = true;
    }
    if (_hoverHalo) {
        _hoverHalo.position.set(p.x, p.y + lift, p.z);
        _hoverHalo.isVisible = true;
    }
    if (_tooltip) {
        const ele = p.ele > 0 ? Math.round(p.ele) + " m" : "";
        const dist = p.dist > 0 ? (p.dist / 1000).toFixed(1) + " km" : "";
        const grade = (p.grade >= 0 ? "+" : "") + p.grade.toFixed(1) + " %";
        _tooltip.textContent = [dist, ele, grade].filter(Boolean).join(" · ");
        _tooltip.style.display = "block";
        _tooltip.style.left = _scene.pointerX + 15 + "px";
        _tooltip.style.top = _scene.pointerY - 30 + "px";
    }
    if (_chart && !fromChart) _chart.highlight(idx);
}

function hideHover() {
    if (_hoverMarker) _hoverMarker.isVisible = false;
    if (_hoverHalo) _hoverHalo.isVisible = false;
    if (_tooltip) _tooltip.style.display = "none";
    if (_chart) _chart.clear();
}

// ---------------------------------------------------------------------------
// Elevation/gradient chart (cross-linked with the 3D hover marker)
// ---------------------------------------------------------------------------

function setupChart() {
    const el = document.getElementById("elevationChart");
    if (!el || !window.MytralProfileChart || _trackScenePts.length < 2) return;
    const points = _trackScenePts.map((p) => [p.dist, p.ele]);
    _chart = MytralProfileChart.renderElevationProfile(el, points, {
        onHover: (idx) => showHoverAt(idx, true),
        onLeave: () => hideHover(),
    });
}

// ---------------------------------------------------------------------------
// Camera presets + follow-track flythrough
// ---------------------------------------------------------------------------

// self-removing manual tween (BABYLON.Animation loop-mode constants are absent
// from the vendored UMD build, which made CreateAndStartAnimation loop forever)
let _camTween = null;

function stopCamTween() {
    if (_camTween && _scene) {
        _scene.onBeforeRenderObservable.remove(_camTween);
        _camTween = null;
    }
}

function animateCameraTo(alpha, beta, radius, target) {
    if (!_camera || !_scene) return;
    _autoRotating = false;
    stopFly(); // a preset overrides an in-progress flythrough
    stopCamTween(); // never stack tweens → never "keeps repeating"
    const from = {
        a: _camera.alpha,
        b: _camera.beta,
        r: _camera.radius,
        t: _camera.target.clone(),
    };
    const to = { a: alpha, b: beta, r: radius, t: (target || from.t).clone() };
    const durationMs = 700;
    let elapsed = 0;
    _camTween = _scene.onBeforeRenderObservable.add(() => {
        elapsed += _engine.getDeltaTime();
        let f = Math.min(elapsed / durationMs, 1);
        f = f < 0.5 ? 2 * f * f : 1 - Math.pow(-2 * f + 2, 2) / 2; // easeInOutQuad
        _camera.alpha = from.a + (to.a - from.a) * f;
        _camera.beta = from.b + (to.b - from.b) * f;
        _camera.radius = from.r + (to.r - from.r) * f;
        _camera.target = BABYLON.Vector3.Lerp(from.t, to.t, f);
        if (f >= 1) stopCamTween();
    });
}

function applyView(view) {
    if (!_camera || !_sceneCtx.center) return;
    const c = _sceneCtx.center;
    const r = _sceneCtx.radius;
    const beta = Math.PI / 3.2;
    switch (view) {
        case "reset":
            animateCameraTo(-Math.PI / 6, Math.PI / 3.5, r * 1.5, c);
            break;
        case "top":
            animateCameraTo(_camera.alpha, 0.02, r * 1.4, c);
            break;
        case "north":
            animateCameraTo(-Math.PI / 2, beta, r * 1.4, c);
            break;
        case "south":
            animateCameraTo(Math.PI / 2, beta, r * 1.4, c);
            break;
        case "east":
            animateCameraTo(Math.PI, beta, r * 1.4, c);
            break;
        case "west":
            animateCameraTo(0, beta, r * 1.4, c);
            break;
        case "fly":
            toggleFly(); // start, or stop if already flying
            break;
    }
}

let _flyObs = null;

// swap the Fly-through button between "play / Fly-through" and "stop / Stop"
const _FLY_PLAY_SVG =
    '<svg xmlns="http://www.w3.org/2000/svg" class="icon" width="24" height="24"' +
    ' viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none"' +
    ' stroke-linecap="round" stroke-linejoin="round">' +
    '<path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M7 4v16l13 -8z"/></svg>';
const _FLY_STOP_SVG =
    '<svg xmlns="http://www.w3.org/2000/svg" class="icon" width="24" height="24"' +
    ' viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none"' +
    ' stroke-linecap="round" stroke-linejoin="round">' +
    '<path stroke="none" d="M0 0h24v24H0z" fill="none"/>' +
    '<path d="M5 5m0 2a2 2 0 0 1 2 -2h10a2 2 0 0 1 2 2v10a2 2 0 0 1 -2 2h-10a2 2 0 0 1 -2 -2z"/></svg>';

function setFlyButton(running) {
    const btn = document.querySelector('[data-view="fly"]');
    if (!btn) return;
    btn.classList.toggle("btn-primary", !running);
    btn.classList.toggle("btn-danger", running);
    btn.innerHTML = running ? _FLY_STOP_SVG + " Stop" : _FLY_PLAY_SVG + " Fly-through";
}

function toggleFly() {
    if (_flyObs) stopFly();
    else startFlythrough();
}

function stopFly() {
    if (_flyObs && _scene) {
        _scene.onBeforeRenderObservable.remove(_flyObs);
        _flyObs = null;
    }
    setFlyButton(false);
}

function startFlythrough() {
    if (!_scene || _trackScenePts.length < 2) return;
    _autoRotating = false;
    stopCamTween();
    stopFly(); // restart cleanly instead of stacking another flight
    setFlyButton(true);
    const pts = _trackScenePts;
    const total = CONFIG.flySeconds * 1000;
    let t = 0;
    _camera.radius = _sceneCtx.radius * 0.45;
    _camera.beta = Math.PI / 3.2;
    _flyObs = _scene.onBeforeRenderObservable.add(() => {
        t += _engine.getDeltaTime();
        const f = Math.min(t / total, 1);
        const fi = f * (pts.length - 1);
        const i = Math.floor(fi);
        const frac = fi - i;
        const a = pts[i];
        const b = pts[Math.min(i + 1, pts.length - 1)];
        _camera.target = new BABYLON.Vector3(
            a.x + (b.x - a.x) * frac,
            a.y + (b.y - a.y) * frac,
            a.z + (b.z - a.z) * frac
        );
        _camera.alpha += 0.0006 * _engine.getDeltaTime();
        showHoverAt(Math.round(fi), false);
        if (f >= 1) stopFly();
    });
}

function setupAutoRotate(canvas) {
    _scene.onBeforeRenderObservable.add(() => {
        if (_autoRotating && _camera) _camera.alpha += CONFIG.autoRotateSpeed;
    });
    const stop = () => {
        _autoRotating = false;
    };
    canvas.addEventListener("pointerdown", stop, { once: true });
    canvas.addEventListener("wheel", stop, { once: true });
}

// ---------------------------------------------------------------------------
// Map-style switcher
// ---------------------------------------------------------------------------

async function reloadTextures(maptype) {
    if (!_scene) return;
    showSpinner("Switching map style…");
    for (const m of _terrainMeshes) m.dispose();
    _terrainMeshes = [];

    const rootUrl = terrainConfig.gltfBaseUrl.replace(/\/[^/]+$/, "/");
    const filename =
        terrainConfig.gltfBaseUrl.replace(/.*\//, "") + `?maptype=${maptype}`;
    try {
        const result = await BABYLON.SceneLoader.ImportMeshAsync(
            "",
            rootUrl,
            filename,
            _scene,
            null,
            ".gltf"
        );
        _terrainMeshes = collectTerrainMeshes(result);
    } catch (e) {
        showError(e);
        return;
    }
    hideSpinner();
}

// ---------------------------------------------------------------------------
// Zoom speed slider (uniform, distance-proportional)
// ---------------------------------------------------------------------------

function readZoomSlider() {
    const s = document.getElementById("zoomSlider");
    return s ? parseInt(s.value, 10) : 14;
}

function wheelPctFromSlider(value) {
    // slider 1 (fast) .. 20 (slow) → wheelDeltaPercentage (high .. low)
    const f = (Math.min(Math.max(value, 1), 20) - 1) / 19;
    return CONFIG.wheelPctFast + (CONFIG.wheelPctSlow - CONFIG.wheelPctFast) * f;
}

function updateZoomSpeed(v) {
    const value = parseInt(v, 10);
    const label = document.getElementById("zoomLabel");
    if (label) label.textContent = value;
    if (_camera) _camera.wheelDeltaPercentage = wheelPctFromSlider(value);
}

// ---------------------------------------------------------------------------
// Spinner / error helpers
// ---------------------------------------------------------------------------

function showSpinner(msg) {
    const el = document.getElementById("terrainSpinner");
    if (!el) return;
    el.style.display = "flex";
    const txt = el.querySelector(".spinner-label");
    if (txt && msg) txt.textContent = msg;
}

function hideSpinner() {
    const el = document.getElementById("terrainSpinner");
    if (el) el.style.display = "none";
}

function showError(err) {
    console.error("terrain3d:", err);
    hideSpinner();
    const el = document.getElementById("terrainError");
    if (el) {
        el.textContent = `3D viewer error: ${err.message || err}`;
        el.style.display = "block";
    }
}
