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
import datetime
import os
import traceback
import uuid

import flask

import mytral
from mytral import app_config as _app_config
from mytral import app_logger
from mytral import app_user_ds as ds
from mytral import commons
from mytral import config as _config_mod
from mytral import forms
from mytral import persistences
from mytral import plugins
from mytral.backends import entities as be_entities
from mytral.blobstore import activity_service as _blob_svc_module
from mytral.integrations import concept2
from mytral.integrations import google_sheets
from mytral.integrations import imytral
from mytral.integrations import polar_hrm
from mytral.routes import COOKIE_USER
from mytral.routes import flask_app
from mytral.tasks import _entities as task_entities
from mytral.tasks.do import fit_import
from mytral.tasks.do import gpx_directory_import
from mytral.tasks.do import gpx_import

#
# helpers
#

# conflict resolution strategy constants
ON_CONFLICT_SKIP = "skip"
ON_CONFLICT_OVERRIDE = "override"
ON_CONFLICT_NEW_KEY = "new_key"


def _recording_import_activity_type_choices(user_id: str) -> list[tuple[str, str]]:
    """Build activity_type_key choices for tools FIT/GPX import forms."""
    return [("", "Auto / unspecified")] + ds.list_activity_types(user_id).choices()


def _build_fit_import_form(user_id: str) -> forms.ImportFitForm:
    """Instantiate FIT import form with dynamic activity type choices."""
    form = forms.ImportFitForm()
    form.activity_type.choices = _recording_import_activity_type_choices(user_id)
    return form


def _build_gpx_import_form(user_id: str) -> forms.ImportGpxForm:
    """Instantiate GPX import form with dynamic activity type choices."""
    form = forms.ImportGpxForm()
    form.activity_type.choices = _recording_import_activity_type_choices(user_id)
    return form


def _build_gpx_directory_import_form(user_id: str) -> forms.ImportGpxDirectoryForm:
    """Instantiate GPX directory import form with dynamic activity type choices."""
    form = forms.ImportGpxDirectoryForm()
    form.sport_type.choices = _recording_import_activity_type_choices(user_id)
    return form


def _find_activity_conflict(
    user_id: str,
    user_profile,
    activity,
) -> str | None:
    """Return the existing activity's key if it conflicts with *activity*, else None.

    Conflict rules
    --------------
    - For externally-sourced activities (non-empty ``src_key``): match by
      ``src`` + ``src_key`` across all activities in the target dataset year.
    - For MyTraL-JSON activities (empty ``src_key``): match by ``key``.

    """
    if activity.src_key:
        # match by src + src_key — look only at the same year for performance
        year_activities = ds.list_activities(
            user_id=user_id,
            dataset_name=user_profile.dataset_name,
            filter_year=activity.when_year,
        )
        for existing in year_activities:
            if existing.src == activity.src and existing.src_key == activity.src_key:
                return existing.key
    else:
        # match by key (MyTraL JSON re-import)
        try:
            ds.get_activity(
                user_id=user_id,
                dataset_name=user_profile.dataset_name,
                key=activity.key,
            )
            return activity.key
        except (ValueError, KeyError):
            pass
    return None


def _find_entity_conflict(user_id: str, entity_type, entity) -> str | None:
    """Return existing entity's key if it conflicts with *entity*, else None.

    All non-activity entity types are matched by ``key``.

    """
    key = getattr(entity, "key", None)
    if not key:
        return None

    try:
        if entity_type == plugins.MytralEntityType.ACTIVITY_TYPES:
            at = ds.list_activity_types(user_id)
            return key if at.exists(key) else None
        if entity_type == plugins.MytralEntityType.EXERCISES:
            exs = ds.list_exercises(user_id)
            return key if exs.exists(key) else None
        if entity_type == plugins.MytralEntityType.GEARS:
            gears = ds.list_gear(user_id)
            return key if gears.exists(key) else None
        if entity_type == plugins.MytralEntityType.GOALS:
            goals = ds.list_goals(user_id)
            return key if key in goals.goals_by_key else None
        if entity_type == plugins.MytralEntityType.LAPS:
            laps = ds.list_laps(user_id)
            return key if laps.exists(key) else None
        if entity_type == plugins.MytralEntityType.OUTFITS:
            outfits = ds.list_outfits(user_id)
            return key if outfits.get_by_key(key) is not None else None
        if entity_type == plugins.MytralEntityType.SYMPTOMS:
            symptoms = ds.list_symptoms(user_id)
            return key if symptoms.exists(key) else None
        if entity_type == plugins.MytralEntityType.COMPONENTS:
            templates = ds.list_component_templates(user_id)
            return key if templates.get_by_key(key) is not None else None
    except Exception:
        pass
    return None


def _import_activities_to_dataset(
    user_id: str,
    user_profile,
    correlation_id: str,
    activities: list,
    source_desc: str,
    on_conflict: str = ON_CONFLICT_SKIP,
) -> tuple[int, list[tuple[str, str]]]:
    """Persist converted activities to the user dataset.

    Parameters
    ----------
    user_id : str
        ID of the target user.
    user_profile :
        User profile carrying the dataset name.
    correlation_id : str
        Request correlation ID used for logging.
    activities : list
        Converted activity entities to persist.
    source_desc : str
        Human-readable source label used in log messages.
    on_conflict : str
        Conflict resolution strategy: ``"skip"`` (default), ``"override"``,
        or ``"new_key"``.

    Returns
    -------
    tuple[int, list[tuple[str, str]]]
        ``(imported_count, failed_list)`` where *failed_list* contains
        ``(name, key)`` tuples for every activity that could not be saved.

    """
    app_logger.info(
        f"Importing converted {source_desc} activities",
        correlation_id=correlation_id,
        activity_count=len(activities),
        on_conflict=on_conflict,
    )
    imported_count = 0
    failed: list[tuple[str, str]] = []
    for a in activities:
        try:
            existing_key = _find_activity_conflict(
                user_id=user_id, user_profile=user_profile, activity=a
            )

            if existing_key:
                if on_conflict == ON_CONFLICT_SKIP:
                    app_logger.info(
                        f"Skipping {source_desc} activity (conflict): '{a.name}'"
                    )
                    continue
                elif on_conflict == ON_CONFLICT_OVERRIDE:
                    app_logger.info(
                        f"Overriding {source_desc} activity (conflict): '{a.name}'"
                    )
                    a.key = existing_key
                    ds.update_activity(
                        user_id=user_id,
                        dataset_name=user_profile.dataset_name,
                        entity=a,
                    )
                    imported_count += 1
                    continue
                # else: on_conflict == ON_CONFLICT_NEW_KEY — fall through to create

            app_logger.info(
                f"Importing converted {source_desc} activity: '{a.name}' / {a.key}"
            )
            ds.create_activity(
                user_id=user_id,
                dataset_name=user_profile.dataset_name,
                entity=a,
            )
            imported_count += 1
        except Exception as e:
            app_logger.error(e)
            failed.append((a.name, a.key))

    return imported_count, failed


def _build_import_result(
    activities: list,
    source_name: str,
    imported_count: int,
    failed: list[tuple[str, str]],
    on_conflict: str = ON_CONFLICT_SKIP,
) -> dict:
    """Build a context dict for the tools-import-result.html template.

    Parameters
    ----------
    activities : list
        All converted activity entities (not just the saved ones).
    source_name : str
        Human-readable source label shown as the page title.
    imported_count : int
        Number of activities successfully saved.
    failed : list[tuple[str, str]]
        ``(name, key)`` pairs for activities that failed to save.
    on_conflict : str
        Conflict strategy used: ``"skip"``, ``"override"``, or ``"new_key"``.

    Returns
    -------
    dict
        Template context variables.

    """
    year_counts: dict[int, int] = {}
    sport_counts: dict[str, int] = {}
    dates: list = []

    for a in activities:
        year_counts[a.when_year] = year_counts.get(a.when_year, 0) + 1
        sport_counts[a.activity_type_key] = sport_counts.get(a.activity_type_key, 0) + 1
        if hasattr(a, "when") and a.when:
            dates.append(a.when)

    year_counts_sorted = dict(sorted(year_counts.items()))
    sport_counts_sorted = dict(
        sorted(sport_counts.items(), key=lambda x: x[1], reverse=True)
    )
    date_first = min(dates) if dates else None
    date_last = max(dates) if dates else None

    on_conflict_labels = {
        ON_CONFLICT_SKIP: "Skip (keep existing)",
        ON_CONFLICT_OVERRIDE: "Override (replace with imported)",
        ON_CONFLICT_NEW_KEY: "Add as new entity",
    }

    return {
        "import_source_name": source_name,
        "import_total": len(activities),
        "import_imported_count": imported_count,
        "import_failed_count": len(failed),
        "import_failed": failed,
        "import_year_counts": year_counts_sorted,
        "import_sport_counts": sport_counts_sorted,
        "import_date_first": date_first,
        "import_date_last": date_last,
        "import_on_conflict": on_conflict_labels.get(on_conflict, on_conflict),
    }


def _import_all_entities_to_dataset(
    user_id: str,
    user_profile,
    correlation_id: str,
    entities_by_type: dict[plugins.MytralEntityType, list],
    source_desc: str,
    on_conflict: str = ON_CONFLICT_SKIP,
) -> tuple[int, list[tuple[str, str]]]:
    """Persist all imported MyTraL entities to the user dataset.

    Parameters
    ----------
    user_id : str
        ID of the target user.
    user_profile :
        User profile carrying the dataset name.
    correlation_id : str
        Request correlation ID used for logging.
    entities_by_type : dict
        Mapping of entity type to deserialized entity list (from the plugin).
    source_desc : str
        Human-readable source label used in log messages.
    on_conflict : str
        Conflict resolution strategy: ``"skip"`` (default), ``"override"``,
        or ``"new_key"``.

    Returns
    -------
    tuple[int, list[tuple[str, str]]]
        ``(imported_count, failed_list)`` where *failed_list* contains
        ``(name, key)`` tuples for every entity that could not be saved.

    """
    imported_count = 0
    failed: list[tuple[str, str]] = []

    for entity_type, entity_list in entities_by_type.items():
        app_logger.info(
            f"Importing {source_desc} entities",
            correlation_id=correlation_id,
            entity_type=entity_type.value,
            count=len(entity_list),
            on_conflict=on_conflict,
        )
        for entity in entity_list:
            name = getattr(entity, "name", str(entity))
            key = getattr(entity, "key", "")
            try:
                existing_key = _find_entity_conflict(
                    user_id=user_id, entity_type=entity_type, entity=entity
                )

                if existing_key:
                    if on_conflict == ON_CONFLICT_SKIP:
                        app_logger.info(
                            f"Skipping {source_desc} entity (conflict): '{name}'"
                        )
                        continue
                    elif on_conflict == ON_CONFLICT_OVERRIDE:
                        app_logger.info(
                            f"Overriding {source_desc} entity (conflict): '{name}'"
                        )
                        _update_entity(
                            user_id=user_id,
                            user_profile=user_profile,
                            entity_type=entity_type,
                            entity=entity,
                        )
                        imported_count += 1
                        continue
                    # else: ON_CONFLICT_NEW_KEY — reassign key and fall through

                    if on_conflict == ON_CONFLICT_NEW_KEY:
                        entity.key = str(uuid.uuid4())

                if entity_type == plugins.MytralEntityType.ACTIVITIES:
                    ds.create_activity(
                        user_id=user_id,
                        dataset_name=user_profile.dataset_name,
                        entity=entity,
                    )
                elif entity_type == plugins.MytralEntityType.ACTIVITY_TYPES:
                    ds.create_activity_type(user_id=user_id, activity_type=entity)
                elif entity_type == plugins.MytralEntityType.COMPONENTS:
                    ds.create_component_template(user_id=user_id, template=entity)
                elif entity_type == plugins.MytralEntityType.EXERCISES:
                    ds.create_exercise(user_id=user_id, exercise=entity)
                elif entity_type == plugins.MytralEntityType.GEARS:
                    ds.create_gear(
                        user_id=user_id,
                        gear=entity,
                        dataset_name=user_profile.dataset_name,
                    )
                elif entity_type == plugins.MytralEntityType.GOALS:
                    ds.create_goal(user_id=user_id, goal=entity)
                elif entity_type == plugins.MytralEntityType.LAPS:
                    ds.create_lap(user_id=user_id, lap=entity)
                elif entity_type == plugins.MytralEntityType.OUTFITS:
                    ds.create_outfit(user_id=user_id, outfit=entity)
                elif entity_type == plugins.MytralEntityType.SYMPTOMS:
                    ds.create_symptom(user_id=user_id, symptom=entity)
                imported_count += 1
            except Exception as e:
                app_logger.error(
                    f"Failed to import {source_desc} entity: {e}",
                    entity_type=entity_type.value,
                    name=name,
                    key=key,
                )
                failed.append((name, key))

    return imported_count, failed


def _update_entity(user_id: str, user_profile, entity_type, entity) -> None:
    """Dispatch an update call for the given entity type."""
    if entity_type == plugins.MytralEntityType.ACTIVITIES:
        ds.update_activity(
            user_id=user_id,
            dataset_name=user_profile.dataset_name,
            entity=entity,
        )
    elif entity_type == plugins.MytralEntityType.ACTIVITY_TYPES:
        ds.update_activity_type(user_id=user_id, activity_type=entity)
    elif entity_type == plugins.MytralEntityType.COMPONENTS:
        ds.update_component_template(user_id=user_id, template=entity)
    elif entity_type == plugins.MytralEntityType.EXERCISES:
        ds.update_exercise(user_id=user_id, exercise=entity)
    elif entity_type == plugins.MytralEntityType.GEARS:
        ds.update_gear(
            user_id=user_id, gear=entity, dataset_name=user_profile.dataset_name
        )
    elif entity_type == plugins.MytralEntityType.GOALS:
        ds.update_goal(user_id=user_id, goal=entity)
    elif entity_type == plugins.MytralEntityType.LAPS:
        ds.update_lap(user_id=user_id, lap=entity)
    elif entity_type == plugins.MytralEntityType.OUTFITS:
        ds.update_outfit(user_id=user_id, outfit=entity)
    elif entity_type == plugins.MytralEntityType.SYMPTOMS:
        ds.update_symptom(user_id=user_id, symptom=entity)


#
# URI space
#


@flask_app.route("/app/tools/import")
def tool_import():
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    return flask.render_template(
        "tools-import.html",
        user_profile=ds.profile(user_id),
        import_races_csv_form=forms.ImportGsheetsRacesCsvForm(),
        import_concept2_csv_form=forms.ImportConcept2CsvForm(),
        import_gsheets_year_csv_form=forms.ImportGsheetsYearCsvForm(),
        import_gsheets_all_years_csv_form=forms.ImportGsheetsAllYearsCsvForm(),
        import_mytral_json_form=forms.ImportMytralJsonForm(),
        import_polar_hrm_form=forms.ImportPolarHrmForm(),
        import_fit_form=_build_fit_import_form(user_id),
        import_gpx_form=_build_gpx_import_form(user_id),
        import_gpx_directory_form=_build_gpx_directory_import_form(user_id),
        is_desktop=_app_config.incarnation == _config_mod.MytralIncarnation.DESKTOP,
    )


@flask_app.route("/app/tools/import/concept2/workouts/csv", methods=["POST"])
def tool_import_concept2_workouts_csv():
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    user_profile = ds.profile(user_id)

    form = forms.ImportConcept2CsvForm()
    if not form.validate_on_submit():
        for field_errors in form.errors.values():
            for error in field_errors:
                flask.flash(error, "warning")
        return flask.redirect(flask.url_for("tool_import"))

    # save CSV file to user's work/ directory
    user_work_dir = persistences.create_user_work(ds.user_dir(user_id=user_id))

    correlation_id = f"{uuid.uuid4()}"
    csv_file = form.csv_file.data
    csv_path = user_work_dir / f"{correlation_id}-raw-activities.csv"
    csv_file.save(str(csv_path))

    app_logger.info("Concept2 workouts CSV UPLOADED")
    flask.flash("Concept2 workouts as CSV uploaded successfully.", "success")

    # import using plugins
    concept2_plugin = plugins.registry.get_plugin(
        concept2.Concept2ActivitiesImportPlugin.NAME
    )

    # CONVERT CSV rows to MyTraL activities
    activities = concept2_plugin.import_activities(
        datasets={
            concept2.Concept2ActivitiesImportPlugin.USE_TYPE_CONCEPT2_CSV: csv_path
        },
        user_profile=user_profile,
        output_path=user_work_dir / f"{correlation_id}-activities.json",
        correlation_id=correlation_id,
    )
    app_logger.info(
        "Concept2 CSV workouts CONVERTED to activities",
        correlation_id=correlation_id,
        activity_count=len(activities),
    )
    # IMPORT activities to the current dataset
    imported_count, failed = _import_activities_to_dataset(
        user_id=user_id,
        user_profile=user_profile,
        correlation_id=correlation_id,
        activities=activities,
        source_desc="Concept2",
        on_conflict=form.on_conflict.data,
    )

    return flask.render_template(
        "tools-import-result.html",
        user_profile=ds.profile(user_id),
        **_build_import_result(
            activities=activities,
            source_name="Concept2",
            imported_count=imported_count,
            failed=failed,
            on_conflict=form.on_conflict.data,
        ),
    )


@flask_app.route("/app/tools/import/gsheets/all-years/csv", methods=["POST"])
def tool_import_gsheets_all_years_csv():
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    user_profile = ds.profile(user_id)

    form = forms.ImportGsheetsAllYearsCsvForm()
    if not form.validate_on_submit():
        for field_errors in form.errors.values():
            for error in field_errors:
                flask.flash(error, "warning")
        return flask.redirect(flask.url_for("tool_import"))

    # save CSV file to user's work/ directory
    user_work_dir = persistences.create_user_work(ds.user_dir(user_id=user_id))

    correlation_id = f"{uuid.uuid4()}"
    csv_file = form.csv_file.data
    csv_path = user_work_dir / f"{correlation_id}-raw-all-years.csv"
    csv_file.save(str(csv_path))

    app_logger.info("Google Sheets all-years CSV UPLOADED")
    flask.flash("Google Sheets all-years CSV uploaded successfully.", "success")

    # import using plugins
    t_g_a_plugin = google_sheets.GoogleSheetsAllYearsImportPlugin
    all_years_plugin = plugins.registry.get_plugin(t_g_a_plugin.NAME)

    # CONVERT CSV rows to MyTraL activities
    activities = all_years_plugin.import_activities(
        datasets={t_g_a_plugin.USE_TYPE_GSHEETS_ALL_YEARS_CSV: csv_path},
        user_profile=user_profile,
        output_path=user_work_dir / f"{correlation_id}-activities-all-years.json",
        correlation_id=correlation_id,
    )
    app_logger.info(
        "Google Sheets all-years CSV CONVERTED to activities",
        correlation_id=correlation_id,
        activity_count=len(activities),
    )
    # IMPORT activities to the current dataset
    imported_count, failed = _import_activities_to_dataset(
        user_id=user_id,
        user_profile=user_profile,
        correlation_id=correlation_id,
        activities=activities,
        source_desc="Google Sheets all years",
        on_conflict=form.on_conflict.data,
    )

    return flask.render_template(
        "tools-import-result.html",
        user_profile=ds.profile(user_id),
        **_build_import_result(
            activities=activities,
            source_name="Google Sheets All Years",
            imported_count=imported_count,
            failed=failed,
            on_conflict=form.on_conflict.data,
        ),
    )


@flask_app.route("/app/tools/import/gsheets/year/csv", methods=["POST"])
def tool_import_gsheets_year_csv():
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    user_profile = ds.profile(user_id)

    form = forms.ImportGsheetsYearCsvForm()
    if not form.validate_on_submit():
        for field_errors in form.errors.values():
            for error in field_errors:
                flask.flash(error, "warning")
        return flask.redirect(flask.url_for("tool_import"))

    # save CSV to user's work/ directory
    user_work_dir = persistences.create_user_work(ds.user_dir(user_id=user_id))

    correlation_id = f"{uuid.uuid4()}"
    csv_file = form.csv_file.data
    csv_path = user_work_dir / f"{correlation_id}-raw-year.csv"
    csv_file.save(str(csv_path))

    app_logger.info("Google Sheets year CSV UPLOADED")
    flask.flash("Google Sheets year CSV uploaded successfully.", "success")

    # import using plugins
    t_g_plugin = google_sheets.GoogleSheetsActivitiesImportPlugin
    year_plugin = plugins.registry.get_plugin(t_g_plugin.NAME)

    # CONVERT CSV rows to MyTraL activities (Strava JSON not provided)
    activities = year_plugin.import_activities(
        datasets={
            t_g_plugin.USE_TYPE_GSHEETS_CSV: csv_path,
        },
        user_profile=user_profile,
        output_path=user_work_dir / f"{correlation_id}-activities-year.json",
        correlation_id=correlation_id,
    )
    app_logger.info(
        "Google Sheets year CSV CONVERTED to activities",
        correlation_id=correlation_id,
        activity_count=len(activities),
    )
    # IMPORT activities to the current dataset
    imported_count, failed = _import_activities_to_dataset(
        user_id=user_id,
        user_profile=user_profile,
        correlation_id=correlation_id,
        activities=activities,
        source_desc="Google Sheets year",
        on_conflict=form.on_conflict.data,
    )

    return flask.render_template(
        "tools-import-result.html",
        user_profile=ds.profile(user_id),
        **_build_import_result(
            activities=activities,
            source_name="Google Sheets Year",
            imported_count=imported_count,
            failed=failed,
            on_conflict=form.on_conflict.data,
        ),
    )


@flask_app.route("/app/tools/import/gsheets/races/csv", methods=["POST"])
def tool_import_gsheets_races_csv():
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    user_profile = ds.profile(user_id)

    form = forms.ImportGsheetsRacesCsvForm()
    if not form.validate_on_submit():
        for field_errors in form.errors.values():
            for error in field_errors:
                flask.flash(error, "warning")
        return flask.redirect(flask.url_for("tool_import"))

    # save CSV file to user's work/ directory
    user_work_dir = persistences.create_user_work(ds.user_dir(user_id=user_id))

    correlation_id = f"{uuid.uuid4()}"
    csv_file = form.csv_file.data
    csv_path = user_work_dir / f"{correlation_id}-raw-races.csv"
    csv_file.save(str(csv_path))

    app_logger.info("Google Sheets CSV races UPLOADED")
    flask.flash("Races as Google Sheets CSV uploaded successfully.", "success")

    # import using plugins
    gsheets_plugin = plugins.registry.get_plugin(
        google_sheets.GoogleSheetsRacesImportPlugin.NAME
    )

    # CONVERT GSheets rows to MyTraL activities
    activities = gsheets_plugin.import_activities(
        datasets={
            google_sheets.GoogleSheetsRacesImportPlugin.USE_TYPE_GSHEETS_CSV: csv_path,
        },
        user_profile=user_profile,
        output_path=user_work_dir / f"{correlation_id}-activities-races.json",
        correlation_id=correlation_id,
    )
    app_logger.info(
        "Google Sheets CSV races CONVERTED to activities",
        correlation_id=correlation_id,
        activity_count=len(activities),
    )
    # IMPORT race activities to the current dataset
    imported_count, failed = _import_activities_to_dataset(
        user_id=user_id,
        user_profile=user_profile,
        correlation_id=correlation_id,
        activities=activities,
        source_desc="Google Sheets",
        on_conflict=form.on_conflict.data,
    )

    return flask.render_template(
        "tools-import-result.html",
        user_profile=ds.profile(user_id),
        **_build_import_result(
            activities=activities,
            source_name="Google Sheets Races",
            imported_count=imported_count,
            failed=failed,
            on_conflict=form.on_conflict.data,
        ),
    )


@flask_app.route("/app/tools/import/mytral/json", methods=["POST"])
def tool_import_mytral_json():
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    user_profile = ds.profile(user_id)

    form = forms.ImportMytralJsonForm()
    if not form.validate_on_submit():
        for field_errors in form.errors.values():
            for error in field_errors:
                flask.flash(error, "warning")
        return flask.redirect(flask.url_for("tool_import"))

    # save JSON file to user's work/ directory
    user_work_dir = persistences.create_user_work(ds.user_dir(user_id=user_id))

    correlation_id = f"{uuid.uuid4()}"
    json_file = form.json_file.data
    json_path = user_work_dir / f"{correlation_id}-raw-mytral.json"
    json_file.save(str(json_path))

    app_logger.info("MyTraL JSON UPLOADED")

    # import using plugin
    mytral_plugin = plugins.registry.get_plugin(imytral.MyTraLImportPlugin.NAME)

    entities_by_type = mytral_plugin.import_entities(
        datasets={imytral.MyTraLImportPlugin.USE_TYPE_JSON: json_path},
        user_profile=user_profile,
        correlation_id=correlation_id,
    )
    total_converted = sum(len(v) for v in entities_by_type.values())
    entity_type_label = (
        next(iter(entities_by_type)).value if entities_by_type else "unknown"
    )
    app_logger.info(
        "MyTraL JSON CONVERTED to entities",
        correlation_id=correlation_id,
        entity_type=entity_type_label,
        total=total_converted,
    )

    # IMPORT entities to the current dataset
    imported_count, failed = _import_all_entities_to_dataset(
        user_id=user_id,
        user_profile=user_profile,
        correlation_id=correlation_id,
        entities_by_type=entities_by_type,
        source_desc="MyTraL",
        on_conflict=form.on_conflict.data,
    )

    # build a generic result context (year/activity type stats only apply to activities)
    all_entities = [e for lst in entities_by_type.values() for e in lst]
    activities_only = [
        e for e in all_entities if isinstance(e, be_entities.ActivityEntity)
    ]

    result_ctx = _build_import_result(
        activities=activities_only,
        source_name=f"MyTraL JSON ({entity_type_label})",
        imported_count=imported_count,
        failed=failed,
        on_conflict=form.on_conflict.data,
    )
    result_ctx["import_total"] = total_converted

    return flask.render_template(
        "tools-import-result.html",
        user_profile=ds.profile(user_id),
        **result_ctx,
    )


@flask_app.route("/app/tools/import/polar/hrm", methods=["POST"])
def tool_import_polar_hrm():
    """Submit an async Polar HRM import task.

    Desktop-only: requires a local filesystem path.
    """
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    # desktop-only guard
    if _app_config.incarnation != _config_mod.MytralIncarnation.DESKTOP:
        err_msg = "Polar HRM import is only available in the desktop version."
        app_logger.error(err_msg)
        flask.flash(err_msg, "warning")
        return flask.redirect(flask.url_for("tool_import"))

    form = forms.ImportPolarHrmForm()
    if not form.validate_on_submit():
        for field_errors in form.errors.values():
            for error in field_errors:
                flask.flash(error, "warning")
        return flask.redirect(flask.url_for("tool_import"))

    data_dir = form.data_dir.data.strip()
    if not os.path.isdir(data_dir):
        return flask.render_template(
            "mytral-error.html",
            user_profile=ds.profile(user_id),
            title="Import Error",
            message=f"The specified Polar data directory does not exist: {data_dir}",
            back_endpoint="tool_import",
        )

    correlation_id = str(uuid.uuid4())

    task_entity = task_entities.TaskEntity(
        key=str(uuid.uuid4()),
        user_id=str(user_id),
        task_type=polar_hrm.POLAR_HRM_TASK_TYPE,
        status=task_entities.TaskStatus.QUEUED,
        created_at=datetime.datetime.now(),
        started_at=None,
        completed_at=None,
        error_message=None,
        error_type=None,
        error_traceback=None,
        progress=0,
        parameters={
            "user_id": user_id,
            "dataset_name": ds.profile(user_id).dataset_name,
            polar_hrm.POLAR_HRM_DATA_DIR_KEY: data_dir,
            "on_conflict": form.on_conflict.data,
            "correlation_id": correlation_id,
        },
        is_cancelled=False,
    )

    try:
        task_id = flask_app.task_manager.executor.submit(task_entity)
        flask.flash(
            f"Polar HRM import started (task {task_id}). "
            "Check the Tasks page for progress.",
            "success",
        )
        return flask.redirect(flask.url_for("task_detail", task_id=task_id))
    except Exception as exc:
        app_logger.exception(
            "Failed to submit Polar HRM import task",
            error=str(exc),
            traceback=traceback.format_exc(),
        )
        flask.flash(f"Failed to start Polar HRM import: {exc}", "error")
        return flask.redirect(flask.url_for("tool_import"))


@flask_app.route("/app/tools/import/fit", methods=["POST"])
def tool_import_fit():
    """Create an activity from an uploaded FIT file and queue processing task."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    form = _build_fit_import_form(str(user_id))
    if not form.validate_on_submit():
        for field_errors in form.errors.values():
            for error in field_errors:
                flask.flash(error, "warning")
        return flask.redirect(flask.url_for("tool_import"))

    user_profile = ds.profile(user_id)
    fit_file = form.recording_file.data
    fit_file.stream.seek(0)
    activity = be_entities.ActivityEntity()
    activity.key = ds.create_key()
    activity.name = (
        form.activity_name.data.strip()
        if form.activity_name.data and form.activity_name.data.strip()
        else os.path.splitext(fit_file.filename or "FIT import")[0]
    )
    activity.activity_type_key = ""  # cleared so FIT summary can set the correct type
    if form.activity_type.data:
        activity.activity_type_key = form.activity_type.data
    activity.src = "fit-import"
    activity.src_descriptor = "tools-import"
    ds.create_activity(
        user_id=user_id,
        dataset_name=user_profile.dataset_name,
        entity=activity,
    )

    blob_svc = _blob_svc_module.ActivityBlobService(
        store=mytral.app_blobstore,
        dataset=ds,
        config=_app_config,
    )
    meta = blob_svc.upload_recording(
        user_id=str(user_id),
        activity_key=activity.key,
        uploaded_file=fit_file.stream,
        original_filename=fit_file.filename or "import.fit",
        content_type=fit_file.content_type or "application/octet-stream",
    )

    task_entity = task_entities.TaskEntity(
        key=str(uuid.uuid4()),
        user_id=str(user_id),
        task_type=fit_import.FitImportTask.TASK_TYPE,
        status=task_entities.TaskStatus.QUEUED,
        created_at=datetime.datetime.now(),
        started_at=None,
        completed_at=None,
        error_message=None,
        error_type=None,
        error_traceback=None,
        progress=0,
        parameters={
            "user_id": user_id,
            "dataset_name": user_profile.dataset_name,
            "activity_key": activity.key,
            "source_blob_uuid": meta.blob_key,
            "blob_key": meta.blob_key,
            "extract_summary": True,
        },
        is_cancelled=False,
        result_route="get_activity",
        result_route_kwargs={"key": activity.key},
    )
    task_id = flask_app.task_manager.executor.submit(task_entity)
    flask.flash(
        f"FIT import queued (task {task_id}) for activity {activity.key}", "success"
    )
    return flask.redirect(flask.url_for("get_activity", key=activity.key))


@flask_app.route("/app/tools/import/gpx", methods=["POST"])
def tool_import_gpx():
    """Create an activity from an uploaded GPX file and queue processing task."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    form = _build_gpx_import_form(user_id)
    if not form.validate_on_submit():
        for field_errors in form.errors.values():
            for error in field_errors:
                flask.flash(error, "warning")
        return flask.redirect(flask.url_for("tool_import"))

    user_profile = ds.profile(user_id)
    gpx_file = form.recording_file.data
    gpx_file.stream.seek(0)
    activity = be_entities.ActivityEntity()
    activity.key = ds.create_key()
    activity.name = (
        form.activity_name.data.strip()
        if form.activity_name.data and form.activity_name.data.strip()
        else os.path.splitext(gpx_file.filename or "GPX import")[0]
    )
    activity.activity_type_key = commons.AT_WORKOUT
    if form.activity_type.data:
        activity.activity_type_key = form.activity_type.data
    activity.src = "gpx-import"
    activity.src_descriptor = "tools-import"
    ds.create_activity(
        user_id=user_id,
        dataset_name=user_profile.dataset_name,
        entity=activity,
    )

    blob_svc = _blob_svc_module.ActivityBlobService(
        store=mytral.app_blobstore,
        dataset=ds,
        config=_app_config,
    )
    meta = blob_svc.upload_recording(
        user_id=user_id,
        activity_key=activity.key,
        uploaded_file=gpx_file.stream,
        original_filename=gpx_file.filename or "import.gpx",
        content_type=gpx_file.content_type or "application/gpx+xml",
    )

    task_entity = task_entities.TaskEntity(
        key=str(uuid.uuid4()),
        user_id=user_id,
        task_type=gpx_import.GpxImportTask.TASK_TYPE,
        status=task_entities.TaskStatus.QUEUED,
        created_at=datetime.datetime.now(),
        started_at=None,
        completed_at=None,
        error_message=None,
        error_type=None,
        error_traceback=None,
        progress=0,
        parameters={
            "user_id": user_id,
            "dataset_name": user_profile.dataset_name,
            "activity_key": activity.key,
            "source_blob_uuid": meta.blob_key,
            "blob_key": meta.blob_key,
            "extract_summary": True,
        },
        is_cancelled=False,
        result_route="get_activity",
        result_route_kwargs={"key": activity.key},
    )
    task_id = flask_app.task_manager.executor.submit(task_entity)
    flask.flash(
        f"GPX import queued (task {task_id}) for activity {activity.key}", "success"
    )
    return flask.redirect(flask.url_for("task_detail", task_id=task_id))


@flask_app.route("/app/tools/import/gpx/directory", methods=["POST"])
def tool_import_gpx_directory():
    """Submit an async GPX directory import task.

    Desktop-only: requires a local filesystem path.
    """
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    # desktop-only guard
    if _app_config.incarnation != _config_mod.MytralIncarnation.DESKTOP:
        flask.flash(
            "GPX directory import is only available in the desktop version.",
            "warning",
        )
        return flask.redirect(flask.url_for("tool_import"))

    form = _build_gpx_directory_import_form(user_id)
    if not form.validate_on_submit():
        for field_errors in form.errors.values():
            for error in field_errors:
                flask.flash(error, "warning")
        return flask.redirect(flask.url_for("tool_import"))

    data_dir = form.data_dir.data.strip()
    if not data_dir:
        return flask.render_template(
            "mytral-error.html",
            user_profile=ds.profile(user_id),
            title="Import Error",
            message="GPX directory path cannot be empty or whitespace-only.",
            back_endpoint="tool_import",
        )
    if not os.path.isabs(data_dir):
        return flask.render_template(
            "mytral-error.html",
            user_profile=ds.profile(user_id),
            title="Import Error",
            message="GPX directory path must be absolute (e.g. /home/user/gpx).",
            back_endpoint="tool_import",
        )
    if not os.path.isdir(data_dir):
        return flask.render_template(
            "mytral-error.html",
            user_profile=ds.profile(user_id),
            title="Import Error",
            message=f"The specified GPX directory does not exist: {data_dir}",
            back_endpoint="tool_import",
        )

    correlation_id = str(uuid.uuid4())

    task_entity = task_entities.TaskEntity(
        key=str(uuid.uuid4()),
        user_id=user_id,
        task_type=gpx_directory_import.GpxDirectoryImportTask.TASK_TYPE,
        status=task_entities.TaskStatus.QUEUED,
        created_at=datetime.datetime.now(),
        started_at=None,
        completed_at=None,
        error_message=None,
        error_type=None,
        error_traceback=None,
        progress=0,
        parameters={
            "user_id": user_id,
            "dataset_name": ds.profile(user_id).dataset_name,
            "data_dir": data_dir,
            "sport_type": form.sport_type.data,
            "on_conflict": form.on_conflict.data,
            "correlation_id": correlation_id,
        },
        is_cancelled=False,
    )

    try:
        task_id = flask_app.task_manager.executor.submit(task_entity)
        flask.flash(
            f"GPX directory import started (task {task_id}). "
            "Check the Tasks page for progress.",
            "success",
        )
        return flask.redirect(flask.url_for("task_detail", task_id=task_id))
    except Exception as exc:
        app_logger.exception(
            "Failed to submit GPX directory import task", error=str(exc)
        )
        flask.flash(f"Failed to start GPX directory import: {exc}", "error")
        return flask.redirect(flask.url_for("tool_import"))
