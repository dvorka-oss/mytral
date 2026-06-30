/**
 * MyTraL 3D terrain viewer — terrain3d.js
 *
 * Initialised by activity-view3d.html via the global `terrainConfig` object:
 *   terrainConfig.activityKey  string  activity UUID
 *   terrainConfig.maptype      string  "osm" | "standard" | "satellite"
 *   terrainConfig.geojsonUrl   string  full URL to the GeoJSON endpoint
 *   terrainConfig.gltfBaseUrl  string  base URL for GLTF (maptype appended as ?maptype=…)
 *
 * Copyright (C) 2022-2026 Martin Dvorak <martin.dvorak@mindforger.com>
 * AGPL v3 — see LICENSE
 */

"use strict";

const TRAIL_COLOR = "#c01414";  // deeper red for stronger contrast
const TRAIL_WIDTH = 6;
const TEXTURE_SIZE = 512;
const TERRAIN_TINT = new BABYLON.Color3(0.86, 0.92, 0.86);

let _scene = null;
let _engine = null;
let _terrainMeshes = [];
let _cachedGeojson = null;
let _currentMaptype = terrainConfig.maptype;
let _camera = null;
let _baseWheelPrecision = 0;
let _autoRotating = true;
let _dirLight = null;

// ---------------------------------------------------------------------------
// Bootstrap
// ---------------------------------------------------------------------------

window.addEventListener("DOMContentLoaded", () => {
    const canvas = document.getElementById("terrainCanvas");
    _engine = new BABYLON.Engine(canvas, true, { preserveDrawingBuffer: true });
    _engine.setHardwareScalingLevel(0.75);

    fetchData().then(({ geojson, rootUrl, filename }) => {
        _cachedGeojson = geojson;
        createScene(canvas, geojson, rootUrl, filename).then(() => {
            _engine.runRenderLoop(() => _scene && _scene.render());
            hideSpinner();
        }).catch(showError);
    }).catch(showError);

    window.addEventListener("resize", () => _engine && _engine.resize());

    // map-style toggle buttons
    document.querySelectorAll("[data-maptype]").forEach(btn => {
        btn.addEventListener("click", () => {
            const mt = btn.dataset.maptype;
            if (mt === _currentMaptype) return;
            _currentMaptype = mt;
            document.querySelectorAll("[data-maptype]").forEach(b =>
                b.classList.toggle("active", b.dataset.maptype === mt));
            reloadTextures(mt);
        });
    });
});

// ---------------------------------------------------------------------------
// Data loading
// ---------------------------------------------------------------------------

async function fetchData() {
    showSpinner("Loading track data…");
    const geoResp = await fetch(terrainConfig.geojsonUrl);
    if (!geoResp.ok) throw new Error(`GeoJSON fetch failed: ${geoResp.status}`);
    const geojson = await geoResp.json();

    // rootUrl must end with "/" so Babylon.js resolves relative texture URIs correctly
    const rootUrl = terrainConfig.gltfBaseUrl.replace(/\/[^/]+$/, "/");
    const filename = terrainConfig.gltfBaseUrl.replace(/.*\//, "") + `?maptype=${_currentMaptype}`;
    return { geojson, rootUrl, filename };
}

// ---------------------------------------------------------------------------
// Scene creation
// ---------------------------------------------------------------------------

async function createScene(canvas, geojson, rootUrl, filename) {
    _scene = new BABYLON.Scene(_engine);
    _scene.clearColor = new BABYLON.Color4(0.18, 0.24, 0.30, 1.0);
    applySceneLook(_scene);

    setupLights(_scene);
    const { center, radius } = await loadTerrain(_scene, rootUrl, filename);
    setupCamera(canvas, _scene, center, radius);
    bakeTrackTextures(_scene, geojson);
    placeSignposts(_scene, geojson);
    setupHoverTracking(_scene, geojson);

    // auto-rotate slowly; stop permanently on first user interaction
    _scene.onBeforeRenderObservable.add(() => {
        if (_autoRotating && _camera) _camera.alpha += 0.003;
    });
    const stopRotation = () => { _autoRotating = false; };
    canvas.addEventListener("pointerdown", stopRotation, { once: true });
    canvas.addEventListener("wheel", stopRotation, { once: true });
}

function applySceneLook(scene) {
    // gently darken and increase contrast to avoid washed-out terrain tiles
    scene.imageProcessingConfiguration.toneMappingEnabled = true;
    scene.imageProcessingConfiguration.toneMappingType =
        BABYLON.ImageProcessingConfiguration.TONEMAPPING_ACES;
    scene.imageProcessingConfiguration.exposure = 0.95;
    scene.imageProcessingConfiguration.contrast = 1.18;
}

function setupLights(scene) {
    const hemi = new BABYLON.HemisphericLight(
        "hemi", new BABYLON.Vector3(0, 1, 0), scene);
    hemi.intensity = 0.5;

    _dirLight = new BABYLON.DirectionalLight(
        "sun", new BABYLON.Vector3(1, -1, 0.5), scene);
    _dirLight.intensity = 1.8;
    scene.ambientColor = new BABYLON.Color3(0.88, 0.92, 0.88);
}

async function loadTerrain(scene, rootUrl, filename) {
    showSpinner("Loading terrain mesh…");
    const result = await BABYLON.SceneLoader.ImportMeshAsync(
        "", rootUrl, filename, scene, null, ".gltf");

    _terrainMeshes = [];

    // collect only meshes that have UV data (textured terrain tiles)
    // set a fallback base colour so tiles appear as green terrain even
    // when the map-tile texture fails to load (instead of black holes)
    result.meshes.forEach(parentMesh => {
        parentMesh.getChildren().forEach(mesh => {
            if (mesh.getVerticesData(BABYLON.VertexBuffer.UVKind)) {
                // slight green tint to keep forests rich and mountains light gray
                mesh.material.albedoColor = TERRAIN_TINT;
                _terrainMeshes.push(mesh);
            }
        });
    });

    // compute bounding box of the entire terrain
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
    const radius = minWorld
        ? maxWorld.subtract(minWorld).length()
        : 5000;
    return { center, radius };
}

function setupCamera(canvas, scene, center, radius) {
    const initRadius = radius * 1.5;
    _camera = new BABYLON.ArcRotateCamera(
        "cam", -Math.PI / 6, Math.PI / 3.5, initRadius, center, scene);
    _camera.minZ = radius * 0.0005;
    _camera.maxZ = radius * 200;
    _camera.lowerRadiusLimit = radius * 0.05;
    _camera.upperRadiusLimit = radius * 10;
    _camera.upperBetaLimit = Math.PI / 2 - 0.05;
    _baseWheelPrecision = 1 / radius * 10;
    _camera.wheelPrecision = _baseWheelPrecision * 3;
    _camera.zoomToMouseLocation = true;
    _camera.panningSensibility = 1 / radius * 500;
    _camera.panningInertia = 0.7;
    _camera.attachControl(canvas, true);

    // dynamic lighting: rotate directional light with camera so terrain
    // relief remains visible from every angle (CubeTrek behaviour)
    _camera.onViewMatrixChangedObservable.add(() => {
        if (_dirLight && _camera) {
            _dirLight.direction = new BABYLON.Vector3(
                -_camera.position.y, _camera.position.x, 0);
        }
    });
}

// ---------------------------------------------------------------------------
// GPX trail texture-baking (CubeTrek approach)
//
// Draws the GPX path directly onto each terrain tile's emissive texture so
// the trail follows the terrain surface exactly at every point. No 3D tube,
// no Z-fighting, no floating offset.
// ---------------------------------------------------------------------------

function bakeTrackTextures(scene, geojson) {
    const tileBBoxes = geojson.properties && geojson.properties.tileBBoxes;
    if (!tileBBoxes || tileBBoxes.length === 0) {
        console.warn("terrain3d: no tileBBoxes in GeoJSON, track not drawn");
        return;
    }
    if (_terrainMeshes.length === 0) {
        console.warn("terrain3d: no textured terrain meshes to draw track on");
        return;
    }

    const coords = geojson.geometry.coordinates;
    if (!coords || coords.length === 0) return;

    // create an emissive DynamicTexture for each textured terrain mesh
    const textureContexts = [];
    for (let i = 0; i < _terrainMeshes.length; i++) {
        const dt = new BABYLON.DynamicTexture("dtx" + i, TEXTURE_SIZE, scene);
        const ctx = dt.getContext();
        ctx.strokeStyle = TRAIL_COLOR;
        ctx.lineWidth = TRAIL_WIDTH;
        ctx.beginPath();
        textureContexts.push(ctx);

        _terrainMeshes[i].material.emissiveTexture = dt;
        _terrainMeshes[i].material.emissiveColor = new BABYLON.Color3(1, 1, 1);
    }

    // draw the GPX path into each tile's texture
    let tileIndex = -1;
    let pxPerDegLon = 0;
    let pxPerDegLat = 0;

    for (let j = 1; j < coords.length; j++) {
        const lon = coords[j][0];
        const lat = coords[j][1];
        const prevLon = coords[j - 1][0];
        const prevLat = coords[j - 1][1];

        // find which tile contains this point
        if (tileIndex === -1 || !pointInTile(lat, lon, tileBBoxes[tileIndex])) {
            // before tile switch: draw the connecting line into the OLD tile
            if (tileIndex !== -1) {
                const x = (lon - tileBBoxes[tileIndex].w_Bound) * pxPerDegLon;
                const y = (lat - tileBBoxes[tileIndex].s_Bound) * pxPerDegLat;
                textureContexts[tileIndex].lineTo(x, y);
            }

            // find the new tile
            for (let k = 0; k < tileBBoxes.length; k++) {
                if (pointInTile(lat, lon, tileBBoxes[k])) {
                    tileIndex = k;
                    pxPerDegLon = TEXTURE_SIZE / tileBBoxes[k].widthLonDegree;
                    pxPerDegLat = TEXTURE_SIZE / tileBBoxes[k].widthLatDegree;

                    // after tile switch: move to previous point in the NEW tile
                    const x = (prevLon - tileBBoxes[k].w_Bound) * pxPerDegLon;
                    const y = (prevLat - tileBBoxes[k].s_Bound) * pxPerDegLat;
                    textureContexts[k].moveTo(x, y);
                    break;
                }
            }
        }

        if (tileIndex === -1) continue;

        const x = (lon - tileBBoxes[tileIndex].w_Bound) * pxPerDegLon;
        const y = (lat - tileBBoxes[tileIndex].s_Bound) * pxPerDegLat;
        textureContexts[tileIndex].lineTo(x, y);
    }

    // stroke all textures
    for (let i = 0; i < textureContexts.length; i++) {
        textureContexts[i].stroke();
        _terrainMeshes[i].material.emissiveTexture.update();
    }
}

function pointInTile(lat, lon, bbox) {
    return bbox.n_Bound >= lat && bbox.s_Bound <= lat
        && bbox.w_Bound <= lon && bbox.e_Bound >= lon;
}

// ---------------------------------------------------------------------------
// Track label signposts (start, finish, highest point)
// ---------------------------------------------------------------------------

function placeSignposts(scene, geojson) {
    const labels = geojson.properties && geojson.properties.labels;
    if (!labels) return;

    const sp = geojson.properties.scene;
    if (!sp) return;

    const cLat = sp.center_lat;
    const cLon = sp.center_lon;
    const mPerDegLat = sp.meters_per_degree_lat;
    const mPerDegLon = sp.meters_per_degree_lon;
    const sf = sp.scale_factor;

    const font = "36px Helvetica";
    const planeHeight = 80;
    const labelKeys = ["start", "highest", "end"];

    labelKeys.forEach(key => {
        const lbl = labels[key];
        if (!lbl) return;

        // scene XZ from lat/lon (Y-up convention, mesh_builder.py formula)
        const sx = (lbl.lat - cLat) * mPerDegLat * sf;
        const sz = (lbl.lon - cLon) * mPerDegLon * sf;

        // ray-cast from high above straight down to find terrain surface
        const ray = new BABYLON.Ray(
            new BABYLON.Vector3(sx, 20000, sz),
            new BABYLON.Vector3(0, -1, 0),
            25000);
        const hit = scene.pickWithRay(ray);
        if (!hit || !hit.hit) return;

        const surfaceY = hit.pickedPoint.y;

        // measure text width to size the sign plane
        const tmpDt = new BABYLON.DynamicTexture("tmp", 64, scene);
        const tmpCtx = tmpDt.getContext();
        tmpCtx.font = font;
        const textW = tmpCtx.measureText(lbl.label).width + 8;
        tmpDt.dispose();

        const dtHeight = 54;
        const ratio = planeHeight / dtHeight;
        const planeW = textW * ratio;

        // text texture
        const dt = new BABYLON.DynamicTexture("lbl_" + key,
            { width: textW, height: dtHeight }, scene, false);
        dt.drawText(lbl.label, null, null, font, "#000000", "#ffffff", true);

        // sign material (semi-transparent white)
        const signMat = new BABYLON.StandardMaterial("signMat_" + key, scene);
        signMat.diffuseTexture = dt;
        signMat.alpha = 0.85;
        signMat.backFaceCulling = false;

        // sign plane — horizontal, facing up, positioned above surface
        const sign = BABYLON.MeshBuilder.CreatePlane("sign_" + key, {
            width: planeW,
            height: planeHeight,
            sideOrientation: BABYLON.Mesh.DOUBLESIDE,
        }, scene);
        sign.material = signMat;
        sign.position.x = sx;
        sign.position.y = surfaceY + planeHeight + 60;
        sign.position.z = sz;
        sign.rotation.x = Math.PI / 2;
        sign.isPickable = false;

        // post — thin vertical rectangle connecting sign to surface
        const postMat = new BABYLON.StandardMaterial("postMat_" + key, scene);
        postMat.diffuseColor = new BABYLON.Color3(0.5, 0.5, 0.5);
        postMat.alpha = 0.6;

        const post = BABYLON.MeshBuilder.CreatePlane("post_" + key, {
            width: 14,
            height: 120,
            sideOrientation: BABYLON.Mesh.DOUBLESIDE,
        }, scene);
        post.material = postMat;
        post.position.x = sx;
        post.position.y = surfaceY + 60;
        post.position.z = sz;
        post.rotation.x = Math.PI / 2;
        post.isPickable = false;
    });
}

// ---------------------------------------------------------------------------
// KD-tree for fast nearest-trackpoint lookup on hover
// ---------------------------------------------------------------------------

class KdTree {
    constructor(points) {
        this._pts = points;  // array of [lon, lat, ele, time, dist, hr]
        this._root = this._build(0, points.length, 0);
    }

    _build(start, end, depth) {
        if (start >= end) return null;
        const axis = depth % 2;  // 0 = lon, 1 = lat
        const slice = this._pts.slice(start, end);
        slice.sort((a, b) => a[axis] - b[axis]);
        const mid = start + Math.floor(slice.length / 2);
        // place median at mid position
        const tmp = this._pts[mid];
        this._pts[mid] = slice[Math.floor(slice.length / 2)];
        this._pts[mid] = tmp;
        // actually just sort in-place is simpler
        this._pts.splice(start, end - start, ...slice);
        return {
            idx: mid,
            axis: axis,
            left: this._build(start, mid, depth + 1),
            right: this._build(mid + 1, end, depth + 1),
        };
    }

    nearest(lon, lat, maxDist) {
        let bestIdx = -1;
        let bestDist = maxDist;
        const _search = (node) => {
            if (!node) return;
            const pt = this._pts[node.idx];
            const dlon = pt[0] - lon;
            const dlat = pt[1] - lat;
            const dist = Math.sqrt(dlon * dlon + dlat * dlat);
            if (dist < bestDist) {
                bestDist = dist;
                bestIdx = node.idx;
            }
            const axisVal = node.axis === 0 ? lon : lat;
            const nodeVal = node.axis === 0 ? pt[0] : pt[1];
            const diff = axisVal - nodeVal;
            const near = diff < 0 ? node.left : node.right;
            const far = diff < 0 ? node.right : node.left;
            _search(near);
            if (Math.abs(diff) < bestDist) _search(far);
        };
        _search(this._root);
        return bestIdx >= 0 ? this._pts[bestIdx] : null;
    }
}

function setupHoverTracking(scene, geojson) {
    const coords = geojson.geometry.coordinates;
    if (!coords || coords.length < 2) return;

    // build KD-tree from track coordinates [lon, lat, ele, time, dist, hr]
    const kdtree = new KdTree(coords);

    const sp = geojson.properties.scene;
    if (!sp) return;
    const cLat = sp.center_lat;
    const cLon = sp.center_lon;
    const mPerDegLat = sp.meters_per_degree_lat;
    const mPerDegLon = sp.meters_per_degree_lon;
    const sf = sp.scale_factor;

    // hover marker sphere
    const markerMat = new BABYLON.StandardMaterial("markerMat", scene);
    markerMat.emissiveColor = new BABYLON.Color3(0.2, 0.6, 1.0);
    markerMat.disableLighting = true;
    const marker = BABYLON.MeshBuilder.CreateSphere("hoverMarker",
        { diameter: 40 * sf }, scene);
    marker.material = markerMat;
    marker.isVisible = false;
    marker.isPickable = false;

    const tooltip = document.getElementById("trackTooltip");
    const canvas = scene.getEngine().getRenderingCanvas();

    scene.onPointerObservable.add((pointerInfo) => {
        if (pointerInfo.type !== BABYLON.PointerEventTypes.POINTERMOVE) return;

        const hit = scene.pick(scene.pointerX, scene.pointerY);
        if (!hit || !hit.hit) {
            marker.isVisible = false;
            if (tooltip) tooltip.style.display = "none";
            return;
        }

        // convert hit point to lat/lon
        const lat = hit.pickedPoint.x / (mPerDegLat * sf) + cLat;
        const lon = hit.pickedPoint.z / (mPerDegLon * sf) + cLon;

        const nearest = kdtree.nearest(lon, lat, 0.001);
        if (!nearest) {
            marker.isVisible = false;
            if (tooltip) tooltip.style.display = "none";
            return;
        }

        // position marker on terrain surface at nearest track point
        const tLon = nearest[0];
        const tLat = nearest[1];
        const mx = (tLat - cLat) * mPerDegLat * sf;
        const mz = (tLon - cLon) * mPerDegLon * sf;
        const ray = new BABYLON.Ray(
            new BABYLON.Vector3(mx, 20000, mz),
            new BABYLON.Vector3(0, -1, 0), 25000);
        const surfaceHit = scene.pickWithRay(ray);
        if (surfaceHit && surfaceHit.hit) {
            marker.position.x = mx;
            marker.position.y = surfaceHit.pickedPoint.y + 30 * sf;
            marker.position.z = mz;
            marker.isVisible = true;
        }

        // update tooltip
        if (tooltip) {
            const ele = nearest[2] > 0 ? Math.round(nearest[2]) + " m" : "";
            const dist = nearest[4] > 0
                ? (nearest[4] / 1000).toFixed(1) + " km" : "";
            tooltip.textContent = [ele, dist].filter(Boolean).join(" · ");
            tooltip.style.display = "block";
            tooltip.style.left = (scene.pointerX + 15) + "px";
            tooltip.style.top = (scene.pointerY - 30) + "px";
        }
    });

    // hide marker when pointer leaves canvas
    canvas.addEventListener("mouseleave", () => {
        marker.isVisible = false;
        if (tooltip) tooltip.style.display = "none";
    });
}

// ---------------------------------------------------------------------------
// Map-style switcher
// ---------------------------------------------------------------------------

async function reloadTextures(maptype) {
    if (!_scene) return;
    showSpinner("Switching map style…");

    // dispose old terrain meshes and reload GLTF with new texture URLs
    for (const m of _terrainMeshes) m.dispose();
    _terrainMeshes = [];

    const rootUrl = terrainConfig.gltfBaseUrl.replace(/\/[^/]+$/, "/");
    const filename = terrainConfig.gltfBaseUrl.replace(/.*\//, "") + `?maptype=${maptype}`;
    try {
        const result = await BABYLON.SceneLoader.ImportMeshAsync(
            "", rootUrl, filename, _scene, null, ".gltf");

        _terrainMeshes = [];
        result.meshes.forEach(parentMesh => {
            parentMesh.getChildren().forEach(mesh => {
                if (mesh.getVerticesData(BABYLON.VertexBuffer.UVKind)) {
                    mesh.material.albedoColor = TERRAIN_TINT;
                    _terrainMeshes.push(mesh);
                }
            });
        });

        // re-bake track textures on the new terrain
        if (_cachedGeojson) {
            bakeTrackTextures(_scene, _cachedGeojson);
        }
    } catch (e) {
        showError(e);
        return;
    }
    hideSpinner();
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

// ---------------------------------------------------------------------------
// Zoom speed slider
// ---------------------------------------------------------------------------

function updateZoomSpeed(v) {
    const value = parseInt(v, 10);
    const label = document.getElementById("zoomLabel");
    if (label) label.textContent = value;
    if (_camera && _baseWheelPrecision > 0) {
        _camera.wheelPrecision = _baseWheelPrecision * value;
    }
}
