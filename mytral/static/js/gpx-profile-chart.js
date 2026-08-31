/**
 * MyTraL elevation/gradient profile chart — gpx-profile-chart.js
 *
 * Standalone, dependency-free SVG renderer for an elevation profile coloured by
 * slope (gradient). Used by the 3D terrain viewer; kept independent of Leaflet
 * and Babylon so it can be reused.
 *
 * Public API (window.MytralProfileChart):
 *   gradeColorHex(gradePercent)            -> "#rrggbb"
 *   renderElevationProfile(container, points, opts) -> { highlight(i), clear() }
 *     points : [[distance_m, elevation_m], ...]
 *     opts.onHover(index) : called when the user hovers the chart
 *
 * Copyright (C) 2022-2026 Martin Dvorak <martin.dvorak@mindforger.com>
 * AGPL v3 — see LICENSE
 */

"use strict";

(function (global) {
    const NS = "http://www.w3.org/2000/svg";

    // slope -> colour ramp (single source of truth, mirrors the 2D activity page)
    function gradeColorHex(gradePercent) {
        if (gradePercent >= 8) return "#d63939"; // steep up
        if (gradePercent >= 4) return "#f59f00"; // up
        if (gradePercent > -4) return "#2fb344"; // ~flat
        if (gradePercent > -8) return "#4299e1"; // down
        return "#206bc4"; // steep down
    }

    function el(tag, attrs) {
        const node = document.createElementNS(NS, tag);
        for (const k in attrs) node.setAttribute(k, attrs[k]);
        return node;
    }

    function renderElevationProfile(container, points, opts) {
        opts = opts || {};
        container.innerHTML = "";
        if (!points || points.length < 2) return { highlight() {}, clear() {} };

        const W = Math.max(container.clientWidth || 800, 200);
        const H = Math.max(container.clientHeight || 160, 80);
        const padL = 46;
        const padR = 12;
        const padT = 10;
        const padB = 22;

        const dists = points.map((p) => p[0]);
        const eles = points.map((p) => p[1]);
        const dMax = dists[dists.length - 1] || 1;
        let eMin = Math.min.apply(null, eles);
        let eMax = Math.max.apply(null, eles);
        if (eMax - eMin < 1) eMax = eMin + 1;
        const ePad = (eMax - eMin) * 0.08;
        eMin -= ePad;
        eMax += ePad;

        const toX = (d) => padL + (d / dMax) * (W - padL - padR);
        const toY = (e) => H - padB - ((e - eMin) / (eMax - eMin)) * (H - padT - padB);

        const svg = el("svg", {
            width: "100%",
            height: H,
            viewBox: `0 0 ${W} ${H}`,
            preserveAspectRatio: "none",
            style: "display:block;",
        });

        // area fill under the profile
        let areaD = `M ${toX(dists[0])} ${H - padB}`;
        for (let i = 0; i < points.length; i++) {
            areaD += ` L ${toX(dists[i])} ${toY(eles[i])}`;
        }
        areaD += ` L ${toX(dMax)} ${H - padB} Z`;
        svg.appendChild(
            el("path", { d: areaD, fill: "rgba(32,107,196,0.10)", stroke: "none" })
        );

        // slope-coloured line, grouped into same-colour polyline runs
        let runColor = null;
        let runPts = [];
        const flushRun = () => {
            if (runPts.length >= 2) {
                svg.appendChild(
                    el("polyline", {
                        points: runPts.join(" "),
                        fill: "none",
                        stroke: runColor,
                        "stroke-width": 2.5,
                        "stroke-linejoin": "round",
                        "stroke-linecap": "round",
                    })
                );
            }
        };
        for (let i = 1; i < points.length; i++) {
            const dd = dists[i] - dists[i - 1];
            const grade = dd > 0 ? ((eles[i] - eles[i - 1]) / dd) * 100 : 0;
            const color = gradeColorHex(grade);
            const a = `${toX(dists[i - 1])},${toY(eles[i - 1])}`;
            const b = `${toX(dists[i])},${toY(eles[i])}`;
            if (color !== runColor) {
                flushRun();
                runColor = color;
                runPts = [a, b];
            } else {
                runPts.push(b);
            }
        }
        flushRun();

        // y-axis elevation guides (min / mid / max)
        [eMin + ePad, (eMin + eMax) / 2, eMax - ePad].forEach((e) => {
            const y = toY(e);
            svg.appendChild(
                el("line", {
                    x1: padL,
                    y1: y,
                    x2: W - padR,
                    y2: y,
                    stroke: "rgba(120,120,120,0.20)",
                    "stroke-width": 1,
                })
            );
            const t = el("text", {
                x: padL - 6,
                y: y + 3,
                "text-anchor": "end",
                "font-size": 10,
                fill: "var(--tblr-secondary, #888)",
            });
            t.textContent = Math.round(e) + " m";
            svg.appendChild(t);
        });

        // x-axis distance labels (0, mid, end) in km
        [0, dMax / 2, dMax].forEach((d) => {
            const t = el("text", {
                x: toX(d),
                y: H - 6,
                "text-anchor": d === 0 ? "start" : d === dMax ? "end" : "middle",
                "font-size": 10,
                fill: "var(--tblr-secondary, #888)",
            });
            t.textContent = (d / 1000).toFixed(1) + " km";
            svg.appendChild(t);
        });

        // hover crosshair
        const cross = el("line", {
            y1: padT,
            y2: H - padB,
            stroke: "#888",
            "stroke-width": 1,
            "stroke-dasharray": "3 3",
            visibility: "hidden",
        });
        const dot = el("circle", { r: 4, fill: "#206bc4", visibility: "hidden" });
        svg.appendChild(cross);
        svg.appendChild(dot);

        const nearestIdx = (clientX) => {
            const rect = svg.getBoundingClientRect();
            const svgX = ((clientX - rect.left) / rect.width) * W;
            const d = ((svgX - padL) / (W - padL - padR)) * dMax;
            // binary-ish: linear scan is fine for a few thousand points
            let best = 0;
            let bestDelta = Infinity;
            for (let i = 0; i < dists.length; i++) {
                const delta = Math.abs(dists[i] - d);
                if (delta < bestDelta) {
                    bestDelta = delta;
                    best = i;
                }
            }
            return best;
        };

        const place = (i) => {
            const x = toX(dists[i]);
            const y = toY(eles[i]);
            cross.setAttribute("x1", x);
            cross.setAttribute("x2", x);
            cross.setAttribute("visibility", "visible");
            dot.setAttribute("cx", x);
            dot.setAttribute("cy", y);
            dot.setAttribute("visibility", "visible");
        };
        const hide = () => {
            cross.setAttribute("visibility", "hidden");
            dot.setAttribute("visibility", "hidden");
        };

        svg.addEventListener("mousemove", (ev) => {
            const i = nearestIdx(ev.clientX);
            place(i);
            if (opts.onHover) opts.onHover(i);
        });
        svg.addEventListener("mouseleave", () => {
            hide();
            if (opts.onLeave) opts.onLeave();
        });

        container.appendChild(svg);
        return {
            highlight(i) {
                if (i >= 0 && i < points.length) place(i);
            },
            clear: hide,
        };
    }

    global.MytralProfileChart = { gradeColorHex, renderElevationProfile };
})(window);
