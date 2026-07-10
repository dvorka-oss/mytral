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
import numpy as np
import pytest

from mytral import recommender
from mytral.backends import entities


def _activity(
    key,
    activity_type_key="run",
    hours=0,
    minutes=0,
    seconds=0,
    distance=0,
    elevation_gain=0,
    gears=None,
):
    """Build a minimal ActivityEntity for recommender tests."""
    a = entities.ActivityEntity()
    a.key = key
    a.activity_type_key = activity_type_key
    a.hours = hours
    a.minutes = minutes
    a.seconds = seconds
    a.distance = distance
    a.elevation_gain = elevation_gain
    a.gears = gears if gears is not None else []
    return a


@pytest.mark.mytral
def test_filter_candidates_by_type_gear_and_all():
    # GIVEN
    activities = [
        _activity("a1", activity_type_key="run", gears=["G1"]),
        _activity("a2", activity_type_key="ride", gears=["G2"]),
        _activity("a3", activity_type_key="run", gears=["G2"]),
    ]

    # WHEN
    by_type = recommender.filter_candidates(activities, "run", "")
    by_gear = recommender.filter_candidates(activities, "", "G2")
    by_both = recommender.filter_candidates(activities, "run", "G2")
    all_of = recommender.filter_candidates(activities, "", "")

    # THEN
    assert [a.key for a in by_type] == ["a1", "a3"]
    assert [a.key for a in by_gear] == ["a2", "a3"]
    assert [a.key for a in by_both] == ["a3"]
    assert [a.key for a in all_of] == ["a1", "a2", "a3"]
    print("DONE: filter_candidates filters by type, gear, both and none")


@pytest.mark.mytral
def test_normalize_maps_to_unit_interval_and_handles_constant_column():
    # GIVEN - column 1 is constant (must not divide by zero)
    raw = np.array([[0.0, 5.0, 10.0], [10.0, 5.0, 20.0]])

    # WHEN
    normalized, mins, maxs = recommender._normalize(raw)

    # THEN
    assert normalized[:, 0].tolist() == [0.0, 1.0]
    assert normalized[:, 1].tolist() == [0.0, 0.0]
    assert normalized[:, 2].tolist() == [0.0, 1.0]
    assert mins.tolist() == [0.0, 5.0, 10.0]
    assert maxs.tolist() == [10.0, 5.0, 20.0]
    print("DONE: _normalize maps to [0,1] and zeroes constant columns")


@pytest.mark.mytral
def test_recommend_ranks_exact_match_first():
    # GIVEN - three activities pointing in distinct feature directions
    activities = [
        _activity("A1", hours=1, distance=10_000, elevation_gain=0),
        _activity("A2", hours=1, distance=0, elevation_gain=1_000),
        _activity("A3", hours=0, distance=10_000, elevation_gain=1_000),
    ]
    # query equals A1's normalized profile
    query = recommender.RecommenderQuery(
        duration_seconds=3_600, distance_m=10_000, elevation_m=0
    )

    # WHEN
    result = recommender.recommend(activities, query)

    # THEN
    assert result.candidate_count == 3
    assert result.matches[0].activity.key == "A1"
    assert result.matches[0].score == pytest.approx(1.0)
    print("DONE: recommend ranks the exact match first with score 1.0")


@pytest.mark.mytral
def test_recommend_blank_query_dimensions_fall_back_to_mean():
    # GIVEN - only distance provided; duration and elevation left blank
    activities = [
        _activity("A1", hours=1, distance=10_000, elevation_gain=0),
        _activity("A2", hours=1, distance=0, elevation_gain=1_000),
        _activity("A3", hours=0, distance=10_000, elevation_gain=1_000),
    ]
    query = recommender.RecommenderQuery(distance_m=10_000)

    # WHEN
    result = recommender.recommend(activities, query)

    # THEN - stays non-degenerate and ranks all candidates
    assert len(result.matches) == 3
    assert all(0.0 <= m.score <= 1.0 for m in result.matches)
    print("DONE: blank query dimensions fall back to the candidate mean")


@pytest.mark.mytral
def test_recommend_caps_at_max_results():
    # GIVEN - more candidates than the cap
    activities = [
        _activity(f"a{i}", distance=1_000 * (i + 1), hours=1) for i in range(150)
    ]
    query = recommender.RecommenderQuery(distance_m=50_000, duration_seconds=3_600)

    # WHEN
    result = recommender.recommend(activities, query)

    # THEN
    assert result.candidate_count == 150
    assert len(result.matches) == recommender.RECOMMENDER_MAX_RESULTS
    print("DONE: recommend caps matches at RECOMMENDER_MAX_RESULTS")


@pytest.mark.mytral
def test_recommend_empty_candidate_set():
    # GIVEN - filter that matches nothing
    activities = [_activity("a1", activity_type_key="run")]
    query = recommender.RecommenderQuery(activity_type_key="swim")

    # WHEN
    result = recommender.recommend(activities, query)

    # THEN
    assert result.candidate_count == 0
    assert result.matches == []
    assert result.recommended_type_key == ""
    print("DONE: empty candidate set returns an empty result")


@pytest.mark.mytral
def test_recommended_type_weighted_vote():
    # GIVEN - two 'run' matches (incl. the top one) and one 'ride'
    activities = [
        _activity("A1", activity_type_key="run", hours=1, distance=10_000),
        _activity("A2", activity_type_key="run", hours=1, elevation_gain=1_000),
        _activity(
            "A3", activity_type_key="ride", distance=10_000, elevation_gain=1_000
        ),
    ]
    query = recommender.RecommenderQuery(
        duration_seconds=3_600, distance_m=10_000, elevation_m=0
    )

    # WHEN
    result = recommender.recommend(activities, query)

    # THEN - run wins: weights run=1.0+0.5, ride=0.5, total=2.0
    assert result.recommended_type_key == "run"
    assert result.recommended_type_confidence == pytest.approx(0.75)
    print("DONE: recommended type is the similarity-weighted majority")


@pytest.mark.mytral
def test_cluster_labels_points_and_builds_centroids():
    # GIVEN - enough matches to trigger k-means
    activities = [
        _activity(f"a{i}", hours=i % 3, distance=1_000 * i, elevation_gain=10 * i)
        for i in range(10)
    ]
    matches = [recommender.ScoredActivity(activity=a, score=1.0) for a in activities]

    # WHEN
    clustered = recommender.cluster(matches)

    # THEN
    assert len(clustered.points) == 10
    assert 2 <= clustered.k <= recommender.CLUSTER_MAX_K
    assert len({p.cluster for p in clustered.points}) == len(clustered.centroids)
    assert all(np.isfinite([p.x, p.y]).all() for p in clustered.points)
    print("DONE: cluster labels every point and summarizes centroids")


@pytest.mark.mytral
def test_cluster_small_set_falls_back_to_single_cluster():
    # GIVEN - fewer matches than CLUSTER_MIN_ACTIVITIES
    activities = [_activity(f"a{i}", distance=1_000 * i) for i in range(3)]
    matches = [recommender.ScoredActivity(activity=a, score=1.0) for a in activities]

    # WHEN
    clustered = recommender.cluster(matches)

    # THEN
    assert clustered.k == 1
    assert {p.cluster for p in clustered.points} == {0}
    assert len(clustered.centroids) == 1
    print("DONE: small match sets fall back to a single cluster")
