# MyTraL: my trailing log
#
# Copyright (C) 2015-2026 Martin Dvorak <martin.dvorak@mindforger.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
"""Activity recommender: embedding-vector cosine-similarity search over activities.

The feature vector has three numeric dimensions, all in SI base units:

    [ duration_seconds, distance_m, elevation_gain_m ]

Values are min-max normalized to ``[0, 1]`` across the candidate set, then ranked by
cosine similarity to a query vector.  Matches can be clustered (k-means) and projected
to 2D (PCA) for a scatter plot.  Pure numpy - no Flask, no optional ML dependency.
"""

import dataclasses
import math

import numpy as np

from mytral.backends import entities

# number of top matches returned / shown
RECOMMENDER_MAX_RESULTS = 100

# number of numeric feature dimensions: duration (s), distance (m), elevation gain (m)
FEATURE_COUNT = 3

# minimum matches required before k-means clustering kicks in
CLUSTER_MIN_ACTIVITIES = 4
# maximum number of clusters
CLUSTER_MAX_K = 6
# k-means parameters (fixed seed keeps results reproducible and tests deterministic)
_KMEANS_MAX_ITERATIONS = 50
_KMEANS_SEED = 42


@dataclasses.dataclass
class RecommenderQuery:
    """Search inputs.  Activity type and gear are filters; the numeric fields (any of
    which may be ``None`` when left blank) form the query vector."""

    activity_type_key: str = ""
    gear_key: str = ""
    duration_seconds: int | None = None
    distance_m: int | None = None
    elevation_m: int | None = None


@dataclasses.dataclass
class ScoredActivity:
    """An activity with its cosine similarity to the query."""

    activity: entities.ActivityEntity
    score: float


@dataclasses.dataclass
class RecommendationResult:
    """Ranked matches plus the aggregated recommended activity type."""

    matches: list[ScoredActivity]
    recommended_type_key: str
    recommended_type_confidence: float
    candidate_count: int


@dataclasses.dataclass
class ClusterPoint:
    """A single activity placed in the 2D scatter with its cluster label."""

    activity: entities.ActivityEntity
    cluster: int
    x: float
    y: float


@dataclasses.dataclass
class ClusterCentroid:
    """A cluster centroid in 2D scatter space plus its raw-unit averages."""

    cluster: int
    x: float
    y: float
    size: int
    avg_duration_seconds: float
    avg_distance_m: float
    avg_elevation_m: float


@dataclasses.dataclass
class ClusterResult:
    """k-means clustering of matches projected to 2D."""

    points: list[ClusterPoint]
    centroids: list[ClusterCentroid]
    k: int


def filter_candidates(
    activities: list[entities.ActivityEntity],
    activity_type_key: str,
    gear_key: str,
) -> list[entities.ActivityEntity]:
    """Filter activities by activity type (exact) and gear (membership).  Empty filter
    strings match everything."""
    result = []
    for activity in activities:
        if activity_type_key and activity.activity_type_key != activity_type_key:
            continue
        if gear_key and gear_key not in activity.gears:
            continue
        result.append(activity)
    return result


def _activity_raw_vector(
    activity: entities.ActivityEntity,
) -> tuple[float, float, float]:
    """Return the raw (unnormalized) feature vector in SI base units."""
    duration_seconds = activity.hours * 3600 + activity.minutes * 60 + activity.seconds
    return (
        float(duration_seconds),
        float(activity.distance),
        float(activity.elevation_gain),
    )


def _raw_matrix(activities: list[entities.ActivityEntity]) -> np.ndarray:
    """Stack raw feature vectors into an ``(n, FEATURE_COUNT)`` matrix."""
    return np.array([_activity_raw_vector(a) for a in activities], dtype=float)


def _normalize(raw: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Min-max normalize each column to ``[0, 1]``.  A constant column maps to 0 (it
    carries no information and this avoids division by zero).  Returns the normalized
    matrix plus the per-column min and max."""
    mins = raw.min(axis=0)
    maxs = raw.max(axis=0)
    spans = maxs - mins
    normalized = np.zeros_like(raw)
    nonzero = spans > 0
    normalized[:, nonzero] = (raw[:, nonzero] - mins[nonzero]) / spans[nonzero]
    return normalized, mins, maxs


def _query_vector(
    query: RecommenderQuery,
    raw: np.ndarray,
    mins: np.ndarray,
    maxs: np.ndarray,
) -> np.ndarray:
    """Build the normalized query vector.  Provided dimensions are normalized with the
    candidate min/max and clamped to ``[0, 1]``; blank dimensions fall back to the
    candidate-set mean so the vector stays neutral there and never collapses to 1D."""
    spans = maxs - mins
    nonzero = spans > 0
    means = raw.mean(axis=0)
    vector = np.zeros(FEATURE_COUNT)
    vector[nonzero] = (means[nonzero] - mins[nonzero]) / spans[nonzero]

    provided = [query.duration_seconds, query.distance_m, query.elevation_m]
    for i, value in enumerate(provided):
        if value is None:
            continue
        if spans[i] > 0:
            vector[i] = min(max((float(value) - mins[i]) / spans[i], 0.0), 1.0)
        else:
            vector[i] = 0.0
    return vector


def _cosine(query: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    """Cosine similarity between ``query`` and every row of ``matrix``.  Zero-norm rows
    (or a zero-norm query) score 0."""
    query_norm = float(np.linalg.norm(query))
    row_norms = np.linalg.norm(matrix, axis=1)
    denom = row_norms * query_norm
    scores = np.zeros(matrix.shape[0])
    valid = denom > 0
    scores[valid] = (matrix @ query)[valid] / denom[valid]
    return scores


def _recommended_type(matches: list[ScoredActivity]) -> tuple[str, float]:
    """Similarity-weighted vote of activity type over the matches.  Falls back to a
    plain count vote when all scores are zero.  Returns (type key, confidence share)."""
    if not matches:
        return "", 0.0
    weights: dict[str, float] = {}
    total = 0.0
    for match in matches:
        weight = max(match.score, 0.0)
        key = match.activity.activity_type_key
        weights[key] = weights.get(key, 0.0) + weight
        total += weight
    if total <= 0:
        weights = {}
        for match in matches:
            key = match.activity.activity_type_key
            weights[key] = weights.get(key, 0.0) + 1.0
        total = float(len(matches))
    best_key = max(weights, key=weights.__getitem__)
    return best_key, weights[best_key] / total


def recommend(
    activities: list[entities.ActivityEntity],
    query: RecommenderQuery,
    limit: int = RECOMMENDER_MAX_RESULTS,
) -> RecommendationResult:
    """Rank activities by cosine similarity to the query; return the top ``limit``."""
    candidates = filter_candidates(activities, query.activity_type_key, query.gear_key)
    if not candidates:
        return RecommendationResult(
            matches=[],
            recommended_type_key="",
            recommended_type_confidence=0.0,
            candidate_count=0,
        )
    raw = _raw_matrix(candidates)
    normalized, mins, maxs = _normalize(raw)
    query_vector = _query_vector(query, raw, mins, maxs)
    scores = _cosine(query_vector, normalized)

    order = np.argsort(-scores, kind="stable")
    matches = [
        ScoredActivity(activity=candidates[i], score=float(scores[i]))
        for i in order[:limit]
    ]
    recommended_key, confidence = _recommended_type(matches)
    return RecommendationResult(
        matches=matches,
        recommended_type_key=recommended_key,
        recommended_type_confidence=confidence,
        candidate_count=len(candidates),
    )


def _choose_k(n: int) -> int:
    """Pick a reasonable cluster count for ``n`` points."""
    k = round(math.sqrt(n / 2.0))
    return int(min(max(k, 2), CLUSTER_MAX_K))


def _kmeans(matrix: np.ndarray, k: int) -> np.ndarray:
    """Plain Lloyd's k-means; returns a cluster label per row.  Empty clusters keep
    their previous centroid.  Deterministic via a fixed seed."""
    rng = np.random.default_rng(_KMEANS_SEED)
    n = matrix.shape[0]
    centroids = matrix[rng.choice(n, size=k, replace=False)].copy()
    labels = np.full(n, -1, dtype=int)
    for _ in range(_KMEANS_MAX_ITERATIONS):
        distances = np.linalg.norm(matrix[:, None, :] - centroids[None, :, :], axis=2)
        new_labels = distances.argmin(axis=1)
        if np.array_equal(new_labels, labels):
            break
        labels = new_labels
        for cluster in range(k):
            members = matrix[labels == cluster]
            if len(members) > 0:
                centroids[cluster] = members.mean(axis=0)
    return labels


def _pca_2d(matrix: np.ndarray) -> np.ndarray:
    """Project rows to 2D via PCA (SVD on the mean-centered matrix)."""
    centered = matrix - matrix.mean(axis=0)
    _, _, vt = np.linalg.svd(centered, full_matrices=False)
    coords = centered @ vt[:2].T
    if coords.shape[1] < 2:
        coords = np.column_stack([coords, np.zeros(coords.shape[0])])
    return coords


def _cluster_centroids(
    raw: np.ndarray, coords: np.ndarray, labels: np.ndarray
) -> list[ClusterCentroid]:
    """Build centroid summaries (2D position + raw-unit averages) per cluster."""
    centroids = []
    for cluster in sorted(set(labels.tolist())):
        mask = labels == cluster
        members_raw = raw[mask]
        members_coords = coords[mask]
        centroids.append(
            ClusterCentroid(
                cluster=int(cluster),
                x=float(members_coords[:, 0].mean()),
                y=float(members_coords[:, 1].mean()),
                size=int(mask.sum()),
                avg_duration_seconds=float(members_raw[:, 0].mean()),
                avg_distance_m=float(members_raw[:, 1].mean()),
                avg_elevation_m=float(members_raw[:, 2].mean()),
            )
        )
    return centroids


def cluster(matches: list[ScoredActivity]) -> ClusterResult:
    """Cluster matches (k-means over normalized vectors) and project them to 2D.  Small
    sets fall back to a single cluster."""
    activities = [m.activity for m in matches]
    n = len(activities)
    if n == 0:
        return ClusterResult(points=[], centroids=[], k=0)
    raw = _raw_matrix(activities)
    normalized, _, _ = _normalize(raw)
    coords = _pca_2d(normalized)

    if n < CLUSTER_MIN_ACTIVITIES:
        labels = np.zeros(n, dtype=int)
        k = 1
    else:
        k = _choose_k(n)
        labels = _kmeans(normalized, k)

    points = [
        ClusterPoint(
            activity=activities[i],
            cluster=int(labels[i]),
            x=float(coords[i, 0]),
            y=float(coords[i, 1]),
        )
        for i in range(n)
    ]
    centroids = _cluster_centroids(raw, coords, labels)
    return ClusterResult(points=points, centroids=centroids, k=k)
