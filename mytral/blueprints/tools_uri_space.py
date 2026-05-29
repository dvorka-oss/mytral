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

import flask

from mytral import app_ds
from mytral import app_user_ds as ds
from mytral import commons
from mytral import forms
from mytral import tools
from mytral.routes import COOKIE_USER
from mytral.routes import flask_app


@flask_app.route("/app/tools/prune", methods=["GET", "POST"])
def tools_prune():
    """Prune activities from the current dataset matching given filter criteria."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))
    user_profile = ds.profile(user_id)

    if flask.request.method == "POST":
        form = forms.ToolPruneDatasetForm()
        if form.validate_on_submit():
            ds.cache_evict(user_id)

            pruned_count = tools.prune_activities(
                user_id=user_id,
                dataset_name=user_profile.dataset_name,
                ds=ds,
                filter_when_year=form.when_year.data or tools.PRUNE_FILTER_ALL,
                filter_src=form.src.data or tools.PRUNE_FILTER_ALL,
                filter_src_key=form.src_key.data or tools.PRUNE_FILTER_ALL,
                filter_src_descriptor=form.src_descriptor.data
                or tools.PRUNE_FILTER_ALL,
            )

            flask.flash(
                message=f"Pruned {pruned_count} activities from the dataset",
                category="success",
            )
            return flask.redirect(flask.url_for("list_activities_year", year=0))

        flask.flash(
            message="Error while pruning dataset - form validation failed",
            category="error",
        )
        return flask.redirect(flask.url_for("home"))

    elif flask.request.method == "GET":
        activities = ds.list_activities(
            user_id=user_id, dataset_name=user_profile.dataset_name
        )

        # collect unique values for each filter field
        years = sorted(set(str(a.when_year) for a in activities if a.when_year))
        srcs = sorted(set(a.src for a in activities if a.src))
        src_keys = sorted(set(a.src_key for a in activities if a.src_key))
        src_descriptors = sorted(
            set(a.src_descriptor for a in activities if a.src_descriptor)
        )

        all_choice = [(tools.PRUNE_FILTER_ALL, tools.PRUNE_FILTER_ALL)]

        form = forms.ToolPruneDatasetForm()
        form.when_year.choices = all_choice + [(y, y) for y in years]
        form.when_year.data = tools.PRUNE_FILTER_ALL
        form.src.choices = all_choice + [(s, s) for s in srcs]
        form.src.data = tools.PRUNE_FILTER_ALL
        form.src_key.choices = all_choice + [(k, k) for k in src_keys]
        form.src_key.data = tools.PRUNE_FILTER_ALL
        form.src_descriptor.choices = all_choice + [(d, d) for d in src_descriptors]
        form.src_descriptor.data = tools.PRUNE_FILTER_ALL

        return flask.render_template(
            "tools-prune.html", user_profile=user_profile, form=form
        )

    else:
        flask.flash(message="Tools error - unsupported method", category="error")
        return flask.redirect(flask.url_for("home"))


@flask_app.route("/app/tools/dataset/optimize")
def tool_optimize_dataset():
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    ds.cache_evict(user_id)

    tools.optimize_current_dataset(
        user_id=user_id, dataset_name=ds.profile(user_id).dataset_name, ds=ds
    )

    return flask.redirect(flask.url_for("list_activities_year", year=0))


@flask_app.route("/app/tools/dataset/fix/gear")
def tool_dataset_gear():
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    ds.cache_evict(user_id)

    tools.fix_gear_keys(
        user_id=user_id, dataset_name=ds.profile(user_id).dataset_name, ds=ds
    )

    return flask.redirect(flask.url_for("list_activities_year", year=0))


@flask_app.route("/app/tools/datasets/merge/all")
def tool_merge_all_datasets():
    """Merge all datasets into the main - lifelong - dataset."""

    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    ds.cache_evict(user_id)

    dataset_name = commons.DATASET_NAME_MAIN
    tools.merge_datasets(
        user_id=user_id,
        dataset_names=ds.profile(user_id).dataset_names,
        target_dataset_name=dataset_name,
        ds=ds,
    )

    # switch to the merged dataset
    ds.profile(user_id).dataset_name = dataset_name

    return flask.redirect(flask.url_for("home"))


@flask_app.route("/app/tools/merge", methods=["GET", "POST"])
def tools_merge():
    """Merge & Join — combine activities across datasets."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))
    user_profile = ds.profile(user_id)

    if flask.request.method == "POST":
        if "merge-submit" in flask.request.form:
            merge_form = forms.ToolMergeAnotherForm(prefix="merge")
            merge_form.data_files.choices = [(f, f) for f in user_profile.dataset_names]
            if merge_form.validate():
                ds.cache_evict(user_id)
                tools.merge_datasets(
                    user_id=user_id,
                    dataset_names=[merge_form.data_files.data],
                    target_dataset_name=user_profile.dataset_name,
                    ds=ds,
                )
                return flask.redirect(flask.url_for("home"))

            flask.flash(message="Error merging another dataset", category="error")
            return flask.redirect(flask.url_for("tools_merge"))

        elif "join-submit" in flask.request.form:
            join_form = forms.ToolJoinForm(prefix="join")
            join_form.data_files.choices = [(f, f) for f in user_profile.dataset_names]
            if join_form.validate():
                ds.cache_evict(user_id)
                tools.join_datasets(
                    user_id=user_id,
                    src_dataset_name=join_form.data_files.data,
                    dst_dataset_name=user_profile.dataset_name,
                    ds=ds,
                )
                return flask.redirect(flask.url_for("home"))

            flask.flash(message="Error joining datasets", category="error")
            return flask.redirect(flask.url_for("tools_merge"))

        else:
            flask.flash(message="Unknown action", category="error")
            return flask.redirect(flask.url_for("tools_merge"))

    elif flask.request.method == "GET":
        dataset_choices = [(f, f) for f in user_profile.dataset_names]

        merge_form = forms.ToolMergeAnotherForm(prefix="merge")
        merge_form.data_files.choices = dataset_choices
        merge_form.data_files.default = user_profile.dataset_name
        merge_form.data_files.process(merge_form.data_files.default)

        join_form = forms.ToolJoinForm(prefix="join")
        join_form.data_files.choices = dataset_choices
        join_form.data_files.default = user_profile.dataset_name
        join_form.data_files.process(join_form.data_files.default)

        return flask.render_template(
            "tools-merge-join.html",
            user_profile=user_profile,
            merge_form=merge_form,
            join_form=join_form,
        )

    else:
        flask.flash(message="Tools error - unsupported method", category="error")
        return flask.redirect(flask.url_for("home"))


@flask_app.route("/app/tools/join")
def tools_join():
    """Redirect to unified Merge & Join page."""
    return flask.redirect(flask.url_for("tools_merge"))


@flask_app.route("/app/tools/filter", methods=["GET", "POST"])
def tools_filter():
    """Filter activities of the current dataset to given date range, optionally
    purge activities from the source dataset, create new (target) dataset with matching.

    """
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))
    user_profile = ds.profile(user_id)

    if flask.request.method == "POST":
        form = forms.ToolFilterDateRangeDataset()
        if form.validate_on_submit():
            ds.cache_evict(user_id)

            src_dataset_name = user_profile.dataset_name

            dst_ds_name = app_ds.create_dataset_name(custom_name="")
            ds.create_activities_dataset(user_id=user_id, dataset_name=dst_ds_name)

            dst_ds_name = tools.filter_date_range_dataset(
                user_id=user_id,
                ds=ds,
                filter_newer_str=form.filter_newer.data,
                filter_older_str=form.filter_older.data,
                src_dataset_name=src_dataset_name,
                dst_dataset_name=dst_ds_name,
                do_extract=bool(form.do_extract.data),
            )

            # switch to filtered dataset & force reload
            user_profile.dataset_name = dst_ds_name
            ds.update_profile(user_id)

            return flask.redirect(flask.url_for("home"))

        flask.flash(
            message=(
                "Error while filtering dataset by date range - form validation failed"
            ),
            category="error",
        )
        return flask.redirect(flask.url_for("home"))

    elif flask.request.method == "GET":
        form = forms.ToolFilterDateRangeDataset()

        this_year = datetime.datetime.now().year

        form.filter_newer.data = f"{this_year}-01-01"
        form.filter_older.data = f"{this_year}-12-31"
        form.do_extract.data = True

        return flask.render_template(
            "tools-filter.html", user_profile=user_profile, form=form
        )

    else:
        flask.flash(message="Tools error - unsupported method", category="error")
        return flask.redirect(flask.url_for("home"))


@flask_app.route("/app/tools/optimize", methods=["GET", "POST"])
def tools_optimize():
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))
    user_profile = ds.profile(user_id)

    if flask.request.method == "POST":
        form = forms.ActivityTypeMigrationForm()
        if form.validate_on_submit():
            from_key = form.from_activity_type.data
            to_key = form.to_activity_type.data

            if from_key == to_key:
                flask.flash(
                    message="Cannot migrate to the same activity type",
                    category="error",
                )
                return flask.redirect(flask.url_for("tools_optimize"))

            ds.cache_evict(user_id)

            migrated = tools.migrate_activity_type(
                user_id=user_id,
                dataset_name=user_profile.dataset_name,
                from_type_key=from_key,
                to_type_key=to_key,
                ds=ds,
            )

            flask.flash(
                message=f"Migrated {migrated} activities to the new type",
                category="success",
            )
            return flask.redirect(flask.url_for("list_activities_year", year=0))

        flask.flash(
            message="Activity type migration error - form validation failed",
            category="error",
        )
        return flask.redirect(flask.url_for("tools_optimize"))

    elif flask.request.method == "GET":
        # build activity type choices with usage counts
        # bypass list_activity_types cache which may hold zero-count data from
        # init_user_cache — _load_activity_types always computes fresh counts
        ats = ds._load_activity_types(
            user_id=user_id, dataset_name=user_profile.dataset_name
        )
        choices_with_counts = []
        for at in ats.activity_types_by_key.values():
            choices_with_counts.append((at.key, f"{at.name} ({at.count})"))
        # sort by name
        choices_with_counts.sort(key=lambda x: x[1].lower())

        form = forms.ActivityTypeMigrationForm()
        form.from_activity_type.choices = choices_with_counts
        form.to_activity_type.choices = choices_with_counts

        return flask.render_template(
            "tools-optimize.html",
            user_profile=user_profile,
            migrate_at_form=form,
        )

    else:
        flask.flash(message="Tools error - unsupported method", category="error")
        return flask.redirect(flask.url_for("home"))
