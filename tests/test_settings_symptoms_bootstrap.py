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
import pytest

from mytral.blueprints import health_uri_space
from mytral.settings import Symptom
from mytral.settings import UserSymptoms


@pytest.mark.mytral
def test_user_symptoms_bootstrap_enriches_symptoms_with_body_parts():
    # GIVEN
    bootstrap = UserSymptoms.bootstrap()
    all_valid_body_parts = {
        body_part_id
        for body_parts in health_uri_space.BODY_PARTS.values()
        for body_part_id in body_parts
    }

    # WHEN
    by_name = {symptom.name: symptom for symptom in bootstrap}
    headache = by_name["headache"]
    thrombosis = by_name[Symptom.S_THROMBOSIS]
    sore_throat = by_name["sore throat"]

    # THEN
    assert len(bootstrap) == len(UserSymptoms.BOOTSTRAP)
    for symptom in bootstrap:
        assert symptom.body_parts
        assert set(symptom.body_parts).issubset(all_valid_body_parts)

    assert "front-head" in headache.body_parts
    assert "front-calf-l" in thrombosis.body_parts
    assert "front-neck" in sore_throat.body_parts
    print("DONE: bootstrap symptoms include valid affected body parts")
