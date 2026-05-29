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
import pathlib

import pytest

from mytral import config
from mytral import loggers
from mytral import settings
from mytral.backends import dataset


@pytest.mark.mytral
def test_component_template_creation():
    """Test component template creation."""
    # GIVEN
    template = settings.ComponentTemplate(
        name="Chain",
        category="cycling",
        default_service_km=500,
    )

    # WHEN / THEN
    assert template.name == "Chain"
    assert template.category == "cycling"
    assert template.default_service_km == 500
    assert template.default_service_hours is None
    assert template.default_service_months is None


@pytest.mark.mytral
def test_load_templates():
    """Test loading pre-defined templates."""
    # GIVEN / WHEN
    templates = settings.COMPONENT_TEMPLATES

    # THEN
    assert len(templates) > 0
    # check cycling templates
    chain = next((t for t in templates if t.name == "Chain"), None)
    assert chain is not None
    assert chain.category == "cycling"
    assert chain.default_service_km == 500


@pytest.mark.mytral
def test_filter_templates_by_category():
    """Test filtering templates by category."""
    # GIVEN
    all_templates = settings.COMPONENT_TEMPLATES

    # WHEN
    cycling_templates = [t for t in all_templates if t.category == "cycling"]
    running_templates = [t for t in all_templates if t.category == "running"]

    # THEN
    assert len(cycling_templates) > 0
    assert len(running_templates) > 0
    assert all(t.category == "cycling" for t in cycling_templates)
    assert all(t.category == "running" for t in running_templates)


@pytest.mark.mytral
def test_template_to_dict():
    """Test template serialization."""
    # GIVEN
    template = settings.ComponentTemplate(
        name="Fork Service",
        category="cycling",
        default_service_hours=50,
        default_service_months=12,
        notes="Full service recommended",
    )

    # WHEN
    data = template.to_dict()

    # THEN
    assert data["name"] == "Fork Service"
    assert data["category"] == "cycling"
    assert data["default_service_hours"] == 50
    assert data["default_service_months"] == 12
    assert data["notes"] == "Full service recommended"


@pytest.mark.mytral
def test_apply_template_to_component():
    """Test applying template to create a component."""
    # GIVEN
    template = settings.ComponentTemplate(
        name="Chain",
        category="cycling",
        default_service_km=500,
    )

    # WHEN - simulate applying template
    component = settings.GearComponent(
        name=template.name,
        next_service_km=template.default_service_km,
        next_service_hours=template.default_service_hours,
        next_service_months=template.default_service_months,
    )

    # THEN
    assert component.name == "Chain"
    assert component.next_service_km == 500
    assert component.next_service_hours is None


#
# Dataset CRUD tests
#


def _make_ds(tmp_path: pathlib.Path):
    """Create a fresh dataset with a registered test user."""
    data_dir = tmp_path / ".local"
    data_dir.mkdir(parents=True, exist_ok=True)
    mytral_config = config.MytralConfig(
        persistence_type=config.PersistenceType.FILESYSTEM,
        persistence_data_dir=data_dir,
    )
    ds = dataset.MyTraLDataset(
        mytral_config=mytral_config, logger=loggers.MytralPrintLogger()
    )
    user_ds = ds.user()
    user_id = "test-user-ct"
    user_ds.register_new_user(user_id=user_id)
    return user_ds, user_id


@pytest.mark.mytral
def test_list_component_templates_seeded(tmp_path: pathlib.Path):
    """New user gets pre-seeded component templates."""
    #
    # GIVEN
    #
    user_ds, user_id = _make_ds(tmp_path)

    #
    # WHEN
    #
    templates = user_ds.list_component_templates(user_id=user_id)

    #
    # THEN
    #
    assert isinstance(templates, settings.UserComponentTemplates)
    assert len(templates.templates) > 0
    names = [t.name for t in templates.templates]
    assert "Chain" in names
    print(f"DONE - seeded {len(templates.templates)} templates")


@pytest.mark.mytral
def test_create_component_template(tmp_path: pathlib.Path):
    """Creating a template persists it and returns it."""
    #
    # GIVEN
    #
    user_ds, user_id = _make_ds(tmp_path)
    new_template = settings.ComponentTemplate(
        name="Custom Tire",
        category="cycling",
        default_service_km=2500,
    )
    original_count = len(user_ds.list_component_templates(user_id).templates)

    #
    # WHEN
    #
    created = user_ds.create_component_template(user_id=user_id, template=new_template)
    listed = user_ds.list_component_templates(user_id=user_id)

    #
    # THEN
    #
    assert created.name == "Custom Tire"
    assert created.key
    assert len(listed.templates) == original_count + 1
    found = listed.get_by_key(created.key)
    assert found is not None
    assert found.name == "Custom Tire"
    assert found.default_service_km == 2500
    print(f"DONE - created template key={created.key}")


@pytest.mark.mytral
def test_update_component_template(tmp_path: pathlib.Path):
    """Updating a template changes its fields and persists them."""
    #
    # GIVEN
    #
    user_ds, user_id = _make_ds(tmp_path)
    template = settings.ComponentTemplate(
        name="Update Me",
        category="running",
        default_service_km=600,
    )
    created = user_ds.create_component_template(user_id=user_id, template=template)

    #
    # WHEN
    #
    created.name = "Updated Name"
    created.default_service_km = 1200
    updated = user_ds.update_component_template(user_id=user_id, template=created)
    fetched = user_ds.get_component_template(user_id=user_id, key=created.key)

    #
    # THEN
    #
    assert updated.name == "Updated Name"
    assert updated.default_service_km == 1200
    assert fetched is not None
    assert fetched.name == "Updated Name"
    assert fetched.default_service_km == 1200
    print("DONE - updated template")


@pytest.mark.mytral
def test_delete_component_template(tmp_path: pathlib.Path):
    """Deleting a template removes it from storage."""
    #
    # GIVEN
    #
    user_ds, user_id = _make_ds(tmp_path)
    template = settings.ComponentTemplate(
        name="To Be Deleted",
        category="swimming",
        default_service_months=6,
    )
    created = user_ds.create_component_template(user_id=user_id, template=template)
    count_before = len(user_ds.list_component_templates(user_id).templates)

    #
    # WHEN
    #
    user_ds.delete_component_template(user_id=user_id, key=created.key)
    listed_after = user_ds.list_component_templates(user_id=user_id)
    fetched = user_ds.get_component_template(user_id=user_id, key=created.key)

    #
    # THEN
    #
    assert len(listed_after.templates) == count_before - 1
    assert fetched is None
    print("DONE - deleted template")
