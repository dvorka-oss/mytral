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
import re
import traceback
import uuid

import flask

import mytral
from mytral import app_config
from mytral import app_ds
from mytral import app_logger
from mytral import app_user_ds as ds
from mytral import commons
from mytral import config
from mytral import forms
from mytral import security
from mytral import settings as user_settings
from mytral.migrations import FsPersistenceMigrations
from mytral.routes import COOKIE_MOBILE
from mytral.routes import COOKIE_TOKEN
from mytral.routes import COOKIE_USER
from mytral.routes import flask_app


@flask_app.route("/signup", methods=["GET", "POST"])
def signup():
    """Register new user account.

    User registration is controlled by the configuration option:
    - app_config.user_registration - allows/disallows new user registration
    - controlled by environment variable: MYTRAL_REGISTRATION_ENABLED
    - default: True (registration enabled)

    Note: This is different from auto_account_creation which creates accounts
    automatically during LOGIN for local/development deployments.

    """
    # check if registration is enabled
    if not app_config.user_registration:
        flask.flash(
            message=(
                "Automatic user registration is disabled - please reconfigure MyTraL "
                "or contact the administrator"
            ),
            category="error",
        )
        return flask.redirect(flask.url_for("login"))

    form = forms.SignUpForm()

    if flask.request.method == "GET":
        return flask.render_template(
            "sign-up.html",
            form=form,
            is_auto_user_registration=app_config.user_registration,
            is_desktop=app_config.incarnation == config.MytralIncarnation.DESKTOP,
        )

    elif flask.request.method == "POST":
        if (
            form.validate_on_submit()
            or app_config.incarnation == config.MytralIncarnation.DESKTOP
        ):
            new_username = form.username.data
            new_email = form.email.data
            new_password = form.password.data

            # sanity check username
            pattern = r"^[a-zA-Z][a-zA-Z0-9-]*$"
            if (
                not new_username
                or not isinstance(new_username, str)
                or re.match(pattern, new_username) is None
            ):
                flask.flash(
                    message=(
                        f"Invalid username: '{new_username}' - it must start with "
                        f"a letter and contain only letters, digits and hyphens"
                    ),
                    category="error",
                )
                return flask.render_template("sign-up.html", form=form)

            # sanity check password
            if (
                app_config.incarnation == config.MytralIncarnation.DESKTOP
                and not new_password
            ):
                new_password = "changeit"
                flask.flash(
                    message=(
                        f"Password of new user {new_username} set to {new_password}"
                    ),
                    category="success",
                )

            if (
                not new_password
                or not isinstance(new_password, str)
                or len(new_password) < 8
            ):
                flask.flash(
                    message=(
                        "Invalid password - it must contain at least 8 characters"
                    ),
                    category="error",
                )
                return flask.render_template("sign-up.html", form=form)

            # check if user already exists
            user_profiles = ds.list_profile_names()
            if new_username in user_profiles:
                flask.flash(
                    message=f"User '{new_username}' already exists. Please login.",
                    category="error",
                )
                return flask.redirect(flask.url_for("login"))

            app_logger.info(f"Registering new user: '{new_username}'...")

            # create user
            user_id = str(uuid.uuid4())
            new_password_enc = security.hash_password(new_password)

            ds.register_new_user(
                user_id=user_id, user_name=new_username, password_enc=new_password_enc
            )

            # create user profile
            new_profile = user_settings.UserProfile(
                user_id=user_id,
                user=new_username,
                email=new_email,
                password_enc=new_password_enc,
                dataset_name=commons.DATASET_NAME_MAIN,
                dataset_names=[commons.DATASET_NAME_MAIN],
                # bootstrap defaults - user should update these via onboarding
                born_year=commons.BOOTSTRAP_BORN_YEAR,
                born_month=commons.BOOTSTRAP_BORN_MONTH,
                born_day=commons.BOOTSTRAP_BORN_DAY,
                height=commons.BOOTSTRAP_HEIGHT_CM,
                auto_login=app_config.incarnation == config.MytralIncarnation.DESKTOP,
            )
            ds.create_profile(user_profile=new_profile)

            # log user in - store user_id (UUID) not username
            flask.session[COOKIE_USER] = user_id
            flask.session[COOKIE_TOKEN] = uuid.uuid4()

            flask.flash(
                message=f"Welcome {new_username}! Your account has been created.",
                category="success",
            )
            return flask.redirect(flask.url_for("home"))

        # form validation failed
        app_logger.error("Registering of the new user failed: form validation")
        flask.flash(
            message="Registration error - please check the form", category="error"
        )
        return flask.render_template("sign-up.html", form=form)

    # unsupported method
    flask.flash(
        message="Registration error - unsupported HTTP method", category="error"
    )
    return flask.redirect(flask.url_for("signup"))


@flask_app.route("/login", methods=["GET", "POST"])
def login():
    # MyTraL (access) token is generated on login by MyTraL server and stored
    # Flask session:
    #
    # - Flask session is stored in the browser cookies
    # - Flask encrypts the session data,
    #   which means that the data are potentially visible to the user
    #   (as the user may get access to the encryption key),
    #   but NOT to the other users - otherwise other user (attacker)
    #   could get access to user cookies, then it can steal the token
    #   from the session and impersonate the user
    # - At the same time, APPLICATION secrets must not be stored in the user
    #   session, because user can get access to the session data and encrypt it
    #

    if flask.request.method == "GET":
        form = forms.LogInForm()

        auto_login_usernames = []
        if app_config.incarnation == config.MytralIncarnation.DESKTOP:
            auto_login_usernames = list(ds.list_profile_names(auto_login=True).keys())

        return flask.render_template(
            "log-in.html",
            auto_login_usernames=auto_login_usernames,
            is_migrate=config.MytralPersistenceFsConfig(app_config).is_migrate(),
            migrate_form=forms.MigrateDataForm(),
            form=form,
        )

    elif flask.request.method == "POST":
        form = forms.LogInForm()
        user_name = form.username.data

        if not app_ds.is_user_name(user_name=user_name):
            if mytral.app_config.auto_account_creation:
                new_username = form.username.data
                new_password = form.password.data

                # sanity check
                pattern = r"^[a-zA-Z][a-zA-Z0-9-]*$"
                if (
                    not new_username
                    or not isinstance(new_username, str)
                    or re.match(pattern, new_username) is None
                ):
                    raise ValueError(
                        f"Invalid username: '{new_username}' -  it must be a string "
                        f"starting with a letter and containing only letters, digits "
                        f"and hyphens"
                    )

                # TODO make this method and reuse throughout the code
                if (
                    not new_password
                    or not isinstance(new_password, str)
                    or len(new_password) < 8
                ):
                    raise ValueError(
                        "Invalid password - it must be a string containing at least "
                        "8 characters"
                    )

                app_logger.info(
                    f"Login: creating user profile for the new user: "
                    f"'{new_username}'..."
                )

                user_id = str(uuid.uuid4())
                new_password_enc = security.hash_password(new_password)
                ds.register_new_user(
                    user_name=new_username,
                    user_id=user_id,
                    password_enc=new_password_enc,
                )
            else:
                msg = f"Login error - unknown user '{user_name}' - sign-up please"
                app_logger.error(msg, user_name=user_name)
                flask.flash(message=msg, category="error")
                return flask.redirect(flask.url_for("signup"))
        else:  # NOT auto account creation
            profile_names = ds.list_profile_names()
            if user_name in profile_names:
                user_id = profile_names[user_name]

                # password check
                user_profile = ds.profile(user_id)
                if (
                    user_profile.auto_login
                    and app_config.incarnation == config.MytralIncarnation.DESKTOP
                ):
                    flask.flash(
                        message=f"Auto logged in as user '{user_name}'",
                        category="success",
                    )
                elif not security.verify_password(
                    form.password.data, user_profile.password_enc
                ):
                    flask.flash(message="Incorrect password", category="error")
                    return flask.redirect(flask.url_for("login"))
            else:
                msg = f"Login error - unknown user '{user_name}' - sign-up please"
                app_logger.error(msg, user_name=user_name)
                flask.flash(message=msg, category="error")
                return flask.redirect(flask.url_for("home"))

        # POST
        flask.session[COOKIE_USER] = user_id
        # safe foo token to client cookies
        flask.session[COOKIE_TOKEN] = str(uuid.uuid4())

        # if the page width is <800px, then switch to mobile view
        app_logger.debug(f"Storing page width to session: {form.page_width.data}")
        if form.page_width.data and int(form.page_width.data) < 800:
            flask.session[COOKIE_MOBILE] = str(form.page_width.data)
        else:
            flask.session[COOKIE_MOBILE] = ""
        app_logger.debug(f"  ... stored: {flask.session.get(COOKIE_MOBILE)}")

        return flask.redirect(flask.url_for("home"))

    flask.flash(message="Settings error - unsupported HTTP method", category="error")
    return flask.redirect(flask.url_for("home"))


@flask_app.route("/login/migrate", methods=["POST"])
def login_migrate():
    """Handle data migration from the login page.

    Reads the current data spec version from disk, runs any applicable
    migration steps, updates config.json with the new version, and
    redirects back to the login page.
    """
    # force a fresh read from disk (bypass cache)
    config.MytralPersistenceFsConfig.invalidate_cache()
    cfg = config.MytralPersistenceFsConfig(app_config)

    if not cfg.is_migrate():
        flask.flash(
            message="No data migration is needed at this time.",
            category="info",
        )
        return flask.redirect(flask.url_for("login"))

    try:
        migrations = FsPersistenceMigrations(
            logger=app_logger, cfg=cfg, ds=mytral.app_ds
        )
        migrations.migrate()

        # persist the updated data spec version to config.json
        cfg.update_data_spec_version()

        # invalidate cache so the next login page GET reads the updated disk state
        config.MytralPersistenceFsConfig.invalidate_cache()

        flask.flash(
            message="Data migration completed successfully. You can now log in.",
            category="success",
        )
    except Exception as ex:
        app_logger.error(
            f"Data migration failed: {ex}", traceback=traceback.format_exc()
        )
        flask.flash(
            message=f"Data migration failed: {ex}. Please check the logs.",
            category="error",
        )

    return flask.redirect(flask.url_for("login"))


@flask_app.route("/logout", methods=["GET"])
def logout():
    user_id = flask.session.pop(COOKIE_USER, None)
    flask.session.pop(COOKIE_TOKEN, None)
    if user_id:
        ds.cache_evict(user_id=user_id)
    return flask.redirect(flask.url_for("login"))


@flask_app.route("/profile")
def profile():
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    if flask.request.method == "GET":
        user_profile = ds.profile(user_id)

        form = forms.ProfileForm()

        form.user_id.data = user_profile.user_id
        form.user_name.data = user_profile.user
        form.display_name.data = user_profile.display_name
        form.email.data = user_profile.email
        form.admin.data = user_profile.admin
        form.expert.data = user_profile.expert
        form.auto_login.data = user_profile.auto_login
        form.birthday_year.data = user_profile.born_year
        form.birthday_month.data = user_profile.born_month
        form.birthday_day.data = user_profile.born_day
        form.height.data = user_profile.height
        form.age.data = user_profile.age

        return flask.render_template(
            "profile-get.html",
            user_profile=user_profile,
            form=form,
        )

    flask.flash(message="Profile error - unsupported HTTP method", category="error")
    return flask.redirect(flask.url_for("home"))


@flask_app.route("/profile/update", methods=["GET", "POST"])
def profile_update():
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))
    user_profile = ds.profile(user_id)

    if flask.request.method == "GET":
        update_form = forms.UpdateProfileForm()
        update_form.display_name.data = user_profile.display_name

        update_form.password.data = ""
        update_form.password_confirm.data = ""

        update_form.birthday_year.data = user_profile.born_year
        update_form.birthday_month.data = user_profile.born_month
        update_form.birthday_day.data = user_profile.born_day

        update_form.height.data = user_profile.height
        update_form.expert.data = user_profile.expert
        # allow auto login on desktop only
        if app_config.incarnation == config.MytralIncarnation.DESKTOP:
            update_form.auto_login.data = user_profile.auto_login
        else:
            update_form.auto_login.data = False
        update_form.currency.data = user_profile.currency

        # TODO location
        # TODO bio

        return flask.render_template(
            "profile-update.html",
            user_profile=user_profile,
            form=update_form,
            upload_avatar_form=forms.UploadAvatarForm(prefix="ua"),
            delete_avatar_form=forms.DeleteAvatarForm(prefix="da"),
        )

    elif flask.request.method == "POST":
        update_form = forms.UpdateProfileForm()

        if update_form.validate_on_submit():
            try:
                if (
                    update_form.birthday_year.data
                    and update_form.birthday_month.data
                    and update_form.birthday_day.data
                ):
                    user_profile.born_year = int(update_form.birthday_year.data)
                    user_profile.born_month = int(update_form.birthday_month.data)
                    user_profile.born_day = int(update_form.birthday_day.data)

                    user_profile.refresh_age()

                if update_form.height.data:
                    user_profile.height = float(update_form.height.data)
                user_profile.expert = update_form.expert.data
                if app_config.incarnation == config.MytralIncarnation.DESKTOP:
                    user_profile.auto_login = update_form.auto_login.data
                else:
                    user_profile.auto_login = False
                user_profile.currency = update_form.currency.data.upper()[:3]
                user_profile.display_name = update_form.display_name.data.strip()
            except Exception as ex:
                flask.flash(
                    message=(f"Profile update error - invalid form data: {ex}"),
                    category="error",
                )
                app_logger.error(
                    f"Profile update error - invalid form data: {ex}:"
                    f"\n{traceback.format_exc()}",
                    exception=traceback.format_exc(),
                )
                return flask.redirect(flask.url_for("profile"))

            # if password is non-empty, then update it
            if update_form.password.data:
                if update_form.password.data != update_form.password_confirm.data:
                    flask.flash(
                        message=(
                            "Profile update error - password and password confirmation "
                            "don't fit - nothing updated"
                        ),
                        category="error",
                    )
                    return flask.redirect(flask.url_for("profile"))

                user_profile.password_enc = security.hash_password(
                    password=str(update_form.password.data)
                )

            # TODO location
            # TODO bio

            ds.update_profile(user_profile)

            return flask.redirect(flask.url_for("profile"))

        # validation failed - re-render the form with error details
        return flask.render_template(
            "profile-update.html",
            user_profile=user_profile,
            form=update_form,
            upload_avatar_form=forms.UploadAvatarForm(prefix="ua"),
            delete_avatar_form=forms.DeleteAvatarForm(prefix="da"),
        )

    flask.flash(
        message="Profile update error - unsupported HTTP method", category="error"
    )
    return flask.redirect(flask.url_for("profile"))
