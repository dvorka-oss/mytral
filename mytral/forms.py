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
import os
from datetime import datetime

import flask_wtf
import flask_wtf.file
import wtforms
from wtforms import validators

from mytral import commons
from mytral.backends import entities


class ToolFilterDateRangeDataset(flask_wtf.FlaskForm):
    filter_newer = wtforms.StringField(
        label="Filter newer than",
        validators=[validators.DataRequired(), validators.Length(min=10, max=10)],
    )

    filter_older = wtforms.StringField(
        label="Filter older than",
        validators=[validators.DataRequired(), validators.Length(min=10, max=10)],
    )

    do_extract = wtforms.BooleanField(
        label="Extract",
        validators=[],
        default=True,
    )

    submit = wtforms.SubmitField("Filter")


class CopyDayForm(flask_wtf.FlaskForm):
    target_year = wtforms.IntegerField(
        label="Year",
        validators=[
            validators.DataRequired(),
            validators.NumberRange(min=1900, max=2100),
        ],
    )

    target_month = wtforms.IntegerField(
        label="Month",
        validators=[validators.DataRequired(), validators.NumberRange(min=1, max=12)],
    )

    target_day = wtforms.IntegerField(
        label="Day",
        validators=[validators.DataRequired(), validators.NumberRange(min=1, max=31)],
    )

    submit = wtforms.SubmitField("Copy Activities")


class SignUpForm(flask_wtf.FlaskForm):
    LABEL_PASSWORD = "Password"
    FIELD_PASSWORD = "password"

    username = wtforms.StringField(
        label="User name",
        validators=[validators.DataRequired(), validators.Length(min=2, max=25)],
    )
    email = wtforms.StringField(
        label="Email",
        validators=[
            validators.DataRequired(),
            validators.Email(),
            validators.Length(min=7, max=50),
        ],
    )
    password = wtforms.PasswordField(
        LABEL_PASSWORD,
        validators=[validators.DataRequired(), validators.Length(min=8, max=50)],
    )
    password_confirm = wtforms.PasswordField(
        label="Confirm password",
        validators=[validators.DataRequired(), validators.EqualTo(FIELD_PASSWORD)],
    )
    submit = wtforms.SubmitField("Sign up")


class LogInForm(flask_wtf.FlaskForm):
    username = wtforms.StringField(
        label="User name",
        validators=[validators.DataRequired(), validators.Email()],
    )
    password = wtforms.PasswordField(
        SignUpForm.LABEL_PASSWORD, validators=[validators.DataRequired()]
    )

    page_width = wtforms.IntegerField(
        label="",
        validators=[],
        default=0,
    )

    submit = wtforms.SubmitField("Sign in")


class ProfileForm(flask_wtf.FlaskForm):
    user_id = wtforms.StringField(
        label="",
        validators=[],
    )

    user_name = wtforms.StringField(
        label="",
        validators=[validators.DataRequired()],
    )

    display_name = wtforms.StringField(
        label="",
        validators=[],
    )

    email = wtforms.StringField(
        label="",
        validators=[validators.DataRequired(), validators.Email()],
    )

    admin = wtforms.BooleanField(
        label="",
        validators=[],
        default=False,
    )
    expert = wtforms.BooleanField(
        label="",
        validators=[],
        default=False,
    )
    auto_login = wtforms.BooleanField(
        label="",
        validators=[],
        default=False,
    )

    birthday_year = wtforms.IntegerField(
        label="",
        validators=[validators.DataRequired(), validators.NumberRange(1900, 2100)],
        default=2000,
    )
    birthday_month = wtforms.IntegerField(
        label="",
        validators=[validators.DataRequired(), validators.NumberRange(1, 12)],
        default=1,
    )
    birthday_day = wtforms.IntegerField(
        label="",
        validators=[validators.DataRequired(), validators.NumberRange(1, 31)],
        default=1,
    )

    # default location used in activities where it is not specified
    location = wtforms.StringField(
        label="Location",
        validators=[],
        default="Prague, Czech Republic",
    )

    height = wtforms.IntegerField(
        label="",
        validators=[validators.DataRequired(), validators.NumberRange(0, 275)],
        default=190,
    )

    age = wtforms.IntegerField(
        label="",
        validators=[validators.DataRequired(), validators.NumberRange(0, 150)],
        default=30,
    )

    bio = wtforms.TextAreaField(
        label="",
        validators=[],
        default=(
            "Consistent hard work, day after day, week after week, year after year. "
            "No magic bullets, no shortcuts. — JoshCox"
        ),
    )

    submit = wtforms.SubmitField("Save")


class UpdateProfileForm(flask_wtf.FlaskForm):
    # if user leaves password blank, it will not be updated
    password = wtforms.PasswordField(SignUpForm.LABEL_PASSWORD)
    password_confirm = wtforms.PasswordField(SignUpForm.LABEL_PASSWORD)

    display_name = wtforms.StringField(
        label="Athlete Name",
        validators=[validators.DataRequired(), validators.Length(min=1, max=64)],
        default="",
    )

    expert = wtforms.BooleanField(
        label="Expert Mode",
        validators=[],
        default=False,
    )

    auto_login = wtforms.BooleanField(
        label="Auto Login",
        validators=[],
        default=False,
    )

    birthday_year = wtforms.IntegerField(
        label="",
        validators=[validators.Optional(), validators.NumberRange(1900, 2100)],
        default=2000,
    )
    birthday_month = wtforms.IntegerField(
        label="",
        validators=[validators.Optional(), validators.NumberRange(1, 12)],
        default=1,
    )
    birthday_day = wtforms.IntegerField(
        label="",
        validators=[validators.Optional(), validators.NumberRange(1, 31)],
        default=1,
    )

    location = wtforms.StringField(
        label="",
        validators=[],
        default="Prague, Czech Republic",
    )

    # height (unit: cm)
    height = wtforms.FloatField(
        label="",
        validators=[validators.Optional(), validators.NumberRange(50, 275)],
        default=1.8,
    )

    currency = wtforms.StringField(
        label="",
        validators=[validators.DataRequired(), validators.Length(min=3, max=3)],
        default="USD",
    )

    bio = wtforms.TextAreaField(
        label="",
        validators=[],
        default=(
            "Consistent hard work, day after day, week after week, year after year. "
            "No magic bullets, no shortcuts. — JoshCox"
        ),
    )

    submit = wtforms.SubmitField("Save")


class StravaSecretsForm(flask_wtf.FlaskForm):
    """Form for setting encrypted Strava API client credentials."""

    client_id = wtforms.StringField(
        label="Strava API Client ID",
        validators=[validators.DataRequired(), validators.Length(min=1, max=64)],
        default="",
    )

    client_secret = wtforms.PasswordField(
        label="Strava API Client Secret",
        validators=[validators.DataRequired(), validators.Length(min=1, max=256)],
        default="",
    )

    submit = wtforms.SubmitField("Save Secrets")


class SettingsForm(flask_wtf.FlaskForm):
    new_dataset_file = wtforms.StringField(
        label="",
        validators=[],
        default="",
    )

    data_files = wtforms.SelectField(
        label="",
        validators=[],  # [validators.DataRequired()],
        choices=[],
        validate_choice=False,
    )

    submit = wtforms.SubmitField("Set")


class ToolMergeAnotherForm(flask_wtf.FlaskForm):
    data_files = wtforms.SelectField(
        label="",
        validators=[],  # [validators.DataRequired()],
        choices=[],
        validate_choice=False,
    )

    submit = wtforms.SubmitField("Merge another")


class ToolJoinForm(flask_wtf.FlaskForm):
    data_files = wtforms.SelectField(
        label="",
        validators=[],  # [validators.DataRequired()],
        choices=[],
        validate_choice=False,
    )

    submit = wtforms.SubmitField("Join")


class ToolPruneDatasetForm(flask_wtf.FlaskForm):
    when_year = wtforms.SelectField(
        label="Year",
        validators=[],
        choices=[],
        validate_choice=False,
    )

    src = wtforms.SelectField(
        label="Source",
        validators=[],
        choices=[],
        validate_choice=False,
    )

    src_key = wtforms.SelectField(
        label="Source Key",
        validators=[],
        choices=[],
        validate_choice=False,
    )

    src_descriptor = wtforms.SelectField(
        label="Source Descriptor",
        validators=[],
        choices=[],
        validate_choice=False,
    )

    submit = wtforms.SubmitField("Prune")


#
# Exercise @ activity
#


class AddActivityExerciseForm(flask_wtf.FlaskForm):
    activity_key = wtforms.HiddenField(
        label="",
        validators=[validators.DataRequired()],
    )

    exercise_name = wtforms.SelectField(
        label="Name",
        validators=[validators.DataRequired()],
        choices=[],  # dynamically initialized in routes module
        validate_choice=False,
        default="",  # dynamically initialized in routes module
    )

    weight = wtforms.FloatField(
        label="Weight (kg)",
        validators=[validators.NumberRange(0, 500)],
        default=0.0,
    )
    series = wtforms.IntegerField(
        label="Series",
        validators=[validators.NumberRange(0, 100)],
        default=0,
    )
    repetitions = wtforms.IntegerField(
        label="Repetitions",
        validators=[validators.NumberRange(0, 10_000)],
        default=0,
    )

    duration = wtforms.IntegerField(
        label="Duration (s)",
        validators=[validators.NumberRange(0, 3600)],
        default=0,
    )
    rest = wtforms.IntegerField(
        label="Rest (s)",
        validators=[validators.NumberRange(0, 3600)],
        default=0,
    )

    submit = wtforms.SubmitField("Add")


class UpdateActivityExerciseForm(AddActivityExerciseForm):
    submit = wtforms.SubmitField("Save")


def from_activity_exercise_form(
    form: AddActivityExerciseForm,
) -> entities.ExerciseEntity:
    return entities.ExerciseEntity(
        activity_key=form.activity_key.data or "",
        name=form.exercise_name.data,
        weight=form.weight.data or 0.0,
        series=form.series.data or 0,
        repetitions=form.repetitions.data or 0,
        duration=form.duration.data or 0,
        rest=form.rest.data or 0,
    )


#
# Symptom @ activity
#


class AddActivitySymptomForm(flask_wtf.FlaskForm):
    activity_key = wtforms.HiddenField(
        label="",
        validators=[validators.DataRequired()],
    )

    symptom = wtforms.SelectField(
        label="Name",
        validators=[validators.DataRequired()],
        choices=[],  # dynamically initialized in routes module
        validate_choice=False,
        default="",  # dynamically initialized in routes module
    )

    side = wtforms.SelectField(
        label="Side",
        validators=[],
        choices=[
            ("", ""),
            ("left", "left"),
            ("right", "right"),
        ],
        validate_choice=False,
        default="",  # dynamically initialized in routes module
    )
    body_part = wtforms.StringField(
        label="Body part",
        validators=[],
        default="",
    )
    health = wtforms.IntegerField(
        label="Health (100% healthy to 0% sick)",
        validators=[validators.NumberRange(0, 100)],
        default=0,
    )

    submit = wtforms.SubmitField("Add")


class UpdateActivitySymptomForm(AddActivitySymptomForm):
    submit = wtforms.SubmitField("Save")


def from_activity_symptom_form(
    form: AddActivitySymptomForm,
) -> entities.SicknessSymptomEntity:
    return entities.SicknessSymptomEntity(
        activity_key=form.activity_key.data or "",
        symptom=form.symptom.data,
        side=form.side.data,
        body_part=form.body_part.data or "",
        health=form.health.data or 0,
    )


#
# Lap @ activity
#


class AddActivityLapForm(flask_wtf.FlaskForm):
    activity_key = wtforms.HiddenField(
        label="",
        validators=[validators.DataRequired()],
    )

    order = wtforms.HiddenField(
        label="",
        validators=[],
        default=0,
    )

    lap_name = wtforms.SelectField(
        label="Name",
        validators=[validators.DataRequired()],
        choices=[],  # dynamically initialized in routes module
        validate_choice=False,
        default="",  # dynamically initialized in routes module
    )

    distance = wtforms.IntegerField(
        label="Distance (m)",
        validators=[validators.NumberRange(0, 100_000)],
        default=0,
    )

    hours = wtforms.IntegerField(
        render_kw={"placeholder": "0"},
        label="Hours",
        description="Duration in hours (0-23)",
        validators=[validators.NumberRange(0, 23)],
        default=0,
    )
    minutes = wtforms.IntegerField(
        render_kw={"placeholder": "0"},
        label="Minutes",
        description="Duration in minutes (0-59)",
        validators=[validators.NumberRange(0, 59)],
        default=0,
    )
    seconds = wtforms.IntegerField(
        render_kw={"placeholder": "0"},
        label="Seconds",
        description="Duration in seconds (0-59)",
        validators=[validators.NumberRange(0, 59)],
        default=0,
    )

    comment = wtforms.StringField(
        label="Comment",
        validators=[],
        default="",
    )

    ranked = wtforms.BooleanField(
        label="",
        validators=[],
        default=False,
    )

    submit = wtforms.SubmitField("Add")


class UpdateActivityLapForm(AddActivityLapForm):
    submit = wtforms.SubmitField("Save")


def from_activity_lap_form(
    form: AddActivityLapForm,
) -> entities.LapEntity:
    hours = form.hours.data or 0
    minutes = form.minutes.data or 0
    seconds = form.seconds.data or 0
    total_seconds = hours * 3600 + minutes * 60 + seconds

    return entities.LapEntity(
        activity_key=form.activity_key.data or "",
        order=int(form.order.data) if form.order.data else 0,
        name=form.lap_name.data,
        distance=form.distance.data or 0,
        duration=total_seconds,
        comment=form.comment.data or "",
        ranked=form.ranked.data or False,
    )


#
# Activities
#


class CreateActivityForm(flask_wtf.FlaskForm):
    when_year = wtforms.IntegerField(
        render_kw={"placeholder": "YYYY"},
        label="Year",
        description="Year when the activity was performed",
        validators=[validators.DataRequired(), validators.NumberRange(1900, 2100)],
        default=datetime.now().year,
    )
    when_month = wtforms.IntegerField(
        render_kw={"placeholder": "MM"},
        label="Month",
        description="Month (1-12)",
        validators=[validators.DataRequired(), validators.NumberRange(1, 12)],
        default=datetime.now().month,
    )
    when_day = wtforms.IntegerField(
        render_kw={"placeholder": "DD"},
        label="Day",
        description="Day of the month (1-31)",
        validators=[validators.DataRequired(), validators.NumberRange(1, 31)],
        default=datetime.now().day,
    )
    when_hour = wtforms.IntegerField(
        render_kw={"placeholder": "HH"},
        label="Hour",
        description="Hour of the day (0-23)",
        validators=[
            validators.NumberRange(0, 23)
        ],  # 0 is not valid value for DataRequired
        default=datetime.now().hour,
    )
    when_minute = wtforms.IntegerField(
        render_kw={"placeholder": "MM"},
        label="Minute",
        description="Minute (0-59)",
        validators=[
            validators.NumberRange(0, 59)
        ],  # 0 is not valid value for DataRequired
        default=datetime.now().minute,
    )
    when_second = wtforms.IntegerField(
        render_kw={"placeholder": "SS"},
        label="Second",
        description="Second (0-59)",
        validators=[
            validators.NumberRange(0, 59)
        ],  # 0 is not valid value for DataRequired
        default=datetime.now().second,
    )

    ###

    name = wtforms.StringField(
        render_kw={"placeholder": "Activity name"},
        label="Title",
        description="Activity name",
        default="",
        validators=[],
    )
    description = wtforms.TextAreaField(
        render_kw={"placeholder": "Activity description"},
        label="Description",
        description="Activity description. Supports Markdown formatting.",
        validators=[],
    )
    where = wtforms.StringField(
        render_kw={"placeholder": "Location"},
        label="Where",
        description="Location where the activity took place",
        validators=[],
        default="",
    )

    ###

    activity_type_key = wtforms.SelectField(
        label="Type",
        description="Type of the activity",
        validators=[validators.DataRequired()],
        # choices & default are dynamically set in the view
        validate_choice=False,
    )
    intensity = wtforms.SelectField(
        label="Intensity",
        description="Intensity of the activity",
        validators=[],  # [validators.DataRequired()],
        # TODO make it dynamic
        choices=commons.INTENSITIES,
        validate_choice=False,
        default=commons.INTENSITY_EASY,
    )
    gears = wtforms.SelectMultipleField(
        label="Gears",
        description="Gear(s) used for the activity",
        validators=[],
        choices=[],
        validate_choice=False,
    )
    outfit = wtforms.SelectField(
        label="Outfit",
        description="Outfit used for the activity",
        validators=[],
        choices=[],
        validate_choice=False,
    )
    formula = wtforms.StringField(
        render_kw={"placeholder": "Workout formula"},
        label="Formula",
        description=(
            "Workout formula describing what was exercised, number of repetitions, "
            "rest and more. For instance: 3*(10*squats + 5*crunches), "
            "3*(2k/r30s + 3k/r20s) or 3*"
        ),
        validators=[],
    )

    ###

    exercises = wtforms.FieldList(
        wtforms.FormField(AddActivityExerciseForm),
        min_entries=0,
        max_entries=100,
    )

    sickness_symptoms = wtforms.FieldList(
        wtforms.FormField(AddActivitySymptomForm),
        min_entries=0,
        max_entries=100,
    )

    laps = wtforms.FieldList(
        wtforms.FormField(AddActivityLapForm),
        min_entries=0,
        max_entries=100,
    )

    ###

    hours = wtforms.IntegerField(
        render_kw={"placeholder": "0"},
        label="Hours",
        description="Duration in hours (0-23)",
        validators=[validators.NumberRange(0, 23)],
        default=0,
    )
    minutes = wtforms.IntegerField(
        render_kw={"placeholder": "0"},
        label="Minutes",
        description="Duration in minutes (0-59)",
        validators=[validators.NumberRange(0, 59)],
        default=0,
    )
    seconds = wtforms.IntegerField(
        render_kw={"placeholder": "0"},
        label="Seconds",
        description="Duration in seconds (0-59)",
        validators=[validators.NumberRange(0, 59)],
        default=0,
    )

    ###

    distance = wtforms.IntegerField(
        render_kw={"placeholder": "0"},
        label="Distance (m)",
        description="Distance in meters",
        validators=[],
        default=0,
    )

    ###

    warm_up = wtforms.BooleanField(
        label="",
        validators=[],
        default=False,
    )
    cool_down = wtforms.BooleanField(
        label="",
        validators=[],
        default=False,
    )
    commute = wtforms.BooleanField(
        label="",
        validators=[],
        default=False,
    )
    ranked = wtforms.BooleanField(
        label="",
        validators=[],
        default=False,
    )
    race = wtforms.BooleanField(
        label="",
        validators=[],
        default=False,
    )

    ###

    kcal = wtforms.IntegerField(
        label="",
        validators=[],
        default=0,
    )
    max_speed = wtforms.FloatField(
        label="",
        validators=[],
        default=0.0,
    )
    elevation_gain = wtforms.IntegerField(
        render_kw={"placeholder": "0"},
        label="Gain",
        description="Elevation gain in meters",
        validators=[],
        default=0,
    )
    elevation_min = wtforms.IntegerField(
        render_kw={"placeholder": "0"},
        label="Min",
        description="Minimum elevation in meters",
        validators=[],
        default=0,
    )
    elevation_max = wtforms.IntegerField(
        render_kw={"placeholder": "0"},
        label="Max",
        description="Maximum elevation in meters",
        validators=[],
        default=0,
    )
    avg_watts = wtforms.FloatField(
        render_kw={"placeholder": "0.0"},
        label="Avg Watts",
        description="Average power in watts (0.0-2000.0)",
        validators=[validators.NumberRange(0.0, 2000.0)],
        default=0,
    )
    max_watts = wtforms.FloatField(
        render_kw={"placeholder": "0.0"},
        label="Max Watts",
        description="Maximum power in watts (0.0-2000.0)",
        validators=[validators.NumberRange(0.0, 2000.0)],
        default=0,
    )

    avg_cadence = wtforms.IntegerField(
        render_kw={"placeholder": "0"},
        label="Avg Cadence",
        description="Average cadence in revolutions/strokes per minute (0-300)",
        validators=[validators.NumberRange(0, 300)],
        default=0,
    )
    max_cadence = wtforms.IntegerField(
        render_kw={"placeholder": "0"},
        label="Max Cadence",
        description="Maximum cadence in revolutions/strokes per minute (0-300)",
        validators=[validators.NumberRange(0, 300)],
        default=0,
    )

    avg_hr = wtforms.IntegerField(
        render_kw={"placeholder": "0"},
        label="Avg HR",
        description="Average heart rate in beats per minute (0-250)",
        validators=[validators.NumberRange(0, 250)],
        default=0,
    )
    max_hr = wtforms.IntegerField(
        render_kw={"placeholder": "0"},
        label="Max HR",
        description="Maximum heart rate in beats per minute (0-250)",
        validators=[validators.NumberRange(0, 250)],
        default=0,
    )
    min_hr = wtforms.IntegerField(
        render_kw={"placeholder": "0"},
        label="Resting HR",
        description=(
            "Resting heart rate in beats per minute (0-250) - ideally measured "
            "in the morning after waking up"
        ),
        validators=[validators.NumberRange(0, 250)],
        default=0,
    )

    ###

    weight = wtforms.FloatField(
        render_kw={"placeholder": "0.0"},
        label="Weight (kg)",
        description="Athlete's body weight in kilograms",
        validators=[],
        default=0.0,
    )

    ###

    cost = wtforms.FloatField(
        render_kw={"placeholder": "0.0"},
        label="Cost",
        description="Activity cost (e.g., gym entry fee, sauna, race registration)",
        validators=[validators.NumberRange(min=0.0)],
        default=0.0,
    )

    ###

    weather = wtforms.SelectField(
        label="Weather",
        description=(
            "Weather conditions during the activity (e.g., sunny, rainy, cloudy)"
        ),
        validators=[],
        choices=commons.WEATHERS,
        default="",
    )
    temperature = wtforms.IntegerField(
        render_kw={"placeholder": "18"},
        label="Temperature (℃)",
        description="Temperature in degrees Celsius (-70 to 70)",
        validators=[validators.NumberRange(-70, 70)],
        default=18,
    )

    ###

    suffer_score = wtforms.FloatField(
        render_kw={"placeholder": "0.0"},
        label="Suffer score",
        description="Subjective difficulty score indicating how hard the workout felt",
        validators=[],
        default=0.0,
    )
    fitness_score = wtforms.FloatField(
        render_kw={"placeholder": "0.0"},
        label="Fitness score",
        description="Training stress score or fitness impact of the activity",
        validators=[],
        default=0.0,
    )

    ###

    src = wtforms.StringField(
        render_kw={"placeholder": "manual"},
        label="Source",
        description="Source of the activity e.g. strava.com, concept2.com or manual",
        validators=[],
        default="manual",
    )
    src_descriptor = wtforms.StringField(
        render_kw={"placeholder": "Additional source info"},
        label="Descriptor",
        description=(
            "Extension point allowing to specify additional information for "
            "source e.g. which paper log book has been used for this entry "
            "e.g. green paper log book '97"
        ),
        validators=[],
        default="",
    )
    src_key = wtforms.StringField(
        render_kw={"placeholder": "UUID or external ID"},
        label="Key",
        description=(
            "Strava UUID or other service internal ID which can be used "
            "to uniquely identify this activity"
        ),
        validators=[],
        default="",
    )
    src_url = wtforms.StringField(
        render_kw={"placeholder": "https://..."},
        label="URL",
        description="URL of the activity source e.g. strava.com link",
        validators=[],
        default="",
    )

    ###

    sort_code = wtforms.IntegerField(
        render_kw={"placeholder": "1"},
        label="Activity order within workout",
        description=(
            "Order of the activity - like warm-up, run or cool-down - in the workout"
        ),
        validators=[validators.DataRequired()],
        default=1,
    )
    workout_sort_code = wtforms.IntegerField(
        render_kw={"placeholder": "1"},
        label="Workout order within day",
        description=(
            "Workout order in which this activity has been performed during the day"
        ),
        validators=[],
        default=1,
    )

    submit = wtforms.SubmitField("Create")


class UpdateActivityForm(CreateActivityForm):
    submit = wtforms.SubmitField("Save")


class DeleteActivityForm(flask_wtf.FlaskForm):
    submit = wtforms.SubmitField("Delete")


#
# Other
#


class ExtendToDateRangeActivityForm(flask_wtf.FlaskForm):
    from_year = wtforms.IntegerField(
        label="Year",
        validators=[validators.DataRequired()],
        default=datetime.now().year,
    )
    from_month = wtforms.IntegerField(
        label="Month",
        validators=[validators.DataRequired()],
        default=datetime.now().month,
    )
    from_day = wtforms.IntegerField(
        label="Day",
        validators=[validators.DataRequired()],
        default=datetime.now().day,
    )

    to_year = wtforms.IntegerField(
        label="Year",
        validators=[validators.DataRequired()],
        default=datetime.now().year,
    )
    to_month = wtforms.IntegerField(
        label="Month",
        validators=[validators.DataRequired()],
        default=datetime.now().month,
    )
    to_day = wtforms.IntegerField(
        label="Day",
        validators=[validators.DataRequired()],
        default=datetime.now().day,
    )

    submit = wtforms.SubmitField("Extend to Date Range")


#
# Blob store forms
#


class UploadRecordingForm(flask_wtf.FlaskForm):
    """Form for uploading an activity recording file (FIT / GPX / HRM)."""

    name = wtforms.StringField(
        label="Name",
        validators=[validators.Optional(), validators.Length(max=120)],
        description="Short name for this recording (optional).",
    )
    description = wtforms.TextAreaField(
        label="Description",
        validators=[validators.Optional(), validators.Length(max=1000)],
        description="Longer description (optional).",
    )
    keywords = wtforms.StringField(
        label="Keywords",
        validators=[validators.Optional(), validators.Length(max=500)],
        description="Comma-separated keywords.",
    )
    recording_file = flask_wtf.file.FileField(
        label="Recording file",
        validators=[flask_wtf.file.FileRequired()],
        description="Supported formats: .fit, .gpx, .hrm — max 64 MiB.",
    )
    submit = wtforms.SubmitField("Upload Recording")


class ImportFitForm(flask_wtf.FlaskForm):
    """Form for importing a FIT recording as a new activity."""

    recording_file = flask_wtf.file.FileField(
        label="FIT file",
        validators=[flask_wtf.file.FileRequired()],
        description="Supported format: .fit — max 64 MiB.",
    )
    activity_name = wtforms.StringField(
        label="Name",
        validators=[validators.Optional(), validators.Length(max=120)],
        description="Optional activity name override.",
    )
    activity_type = wtforms.SelectField(
        label="Activity type",
        choices=[],
        default="",
        validators=[validators.Optional()],
        validate_choice=False,
        description="Optional activity_type_key override.",
    )
    submit = wtforms.SubmitField("Import FIT")


class ImportGpxForm(flask_wtf.FlaskForm):
    """Form for importing a GPX recording as a new activity."""

    recording_file = flask_wtf.file.FileField(
        label="GPX file",
        validators=[flask_wtf.file.FileRequired()],
        description="Supported format: .gpx — max 64 MiB.",
    )
    activity_name = wtforms.StringField(
        label="Name",
        validators=[validators.Optional(), validators.Length(max=120)],
        description="Optional activity name override.",
    )
    activity_type = wtforms.SelectField(
        label="Activity type",
        choices=[],
        default="",
        validators=[validators.Optional()],
        validate_choice=False,
        description="Optional activity_type_key override.",
    )
    submit = wtforms.SubmitField("Import GPX")


class ImportGpxDirectoryForm(flask_wtf.FlaskForm):
    """Form for importing multiple GPX files from a directory.

    Desktop-only: requires a local filesystem path.
    """

    data_dir = wtforms.StringField(
        label="GPX directory",
        description=(
            "Absolute path to the directory containing .gpx files "
            "(e.g. /path/to/gpx/files/)."
        ),
        validators=[validators.DataRequired()],
    )
    sport_type = wtforms.SelectField(
        label="Sport",
        choices=[("", "Auto / unspecified")],
        default="",
        validators=[validators.Optional()],
        validate_choice=False,
        description="Optional sport override for all imported activities.",
    )
    on_conflict = wtforms.RadioField(
        label="If activity already exists",
        choices=[
            ("skip", "Skip"),
            ("override", "Override"),
            ("new_key", "Add as new"),
        ],
        default="skip",
    )
    submit = wtforms.SubmitField("Import GPX Directory")

    def validate_data_dir(self, field):
        """Validate data_dir is not empty after stripping and is absolute."""
        value = field.data.strip() if field.data else ""
        if not value:
            raise validators.ValidationError(
                "GPX directory path cannot be empty or whitespace-only."
            )
        if not os.path.isabs(value):
            raise validators.ValidationError(
                "GPX directory path must be an absolute path (e.g. /home/user/gpx)."
            )
        # update field data with stripped value
        field.data = value


class UploadActivityPhotosForm(flask_wtf.FlaskForm):
    """Form for uploading one or more activity photos."""

    name = wtforms.StringField(
        label="Name",
        validators=[validators.Optional(), validators.Length(max=120)],
        description="Applied to all uploaded photos.",
    )
    description = wtforms.TextAreaField(
        label="Description",
        validators=[validators.Optional(), validators.Length(max=1000)],
    )
    keywords = wtforms.StringField(
        label="Keywords",
        validators=[validators.Optional(), validators.Length(max=500)],
        description="Comma-separated keywords applied to all uploaded photos.",
    )
    photos = flask_wtf.file.MultipleFileField(
        label="Photos",
        validators=[flask_wtf.file.FileRequired()],
        description=(
            "Supported formats: .jpg, .jpeg, .png, .webp — "
            "max 25 MiB per photo, up to 50 photos per activity."
        ),
    )
    submit = wtforms.SubmitField("Upload Photos")


class UpdateActivityPhotoMetadataForm(flask_wtf.FlaskForm):
    """Form for editing photo blob metadata."""

    name = wtforms.StringField(
        label="Name",
        validators=[validators.Optional(), validators.Length(max=120)],
    )
    description = wtforms.TextAreaField(
        label="Description",
        validators=[validators.Optional(), validators.Length(max=1000)],
    )
    keywords = wtforms.StringField(
        label="Keywords",
        validators=[validators.Optional(), validators.Length(max=500)],
        description="Comma-separated keywords.",
    )
    submit = wtforms.SubmitField("Save")


def from_activity_form(
    form: "CreateActivityForm | UpdateActivityForm", ds, user_id: str
) -> entities.ActivityEntity:
    entity = entities.ActivityEntity()

    # activity_type_key choices
    activity_type_choices = ds.list_activity_types(user_id).choices()
    form.activity_type_key.choices = activity_type_choices
    form.activity_type_key.default = activity_type_choices[0][0]

    # outfit choices
    outfit_choices = [("", "")] + [
        (o.key, o.name) for o in ds.list_outfits(user_id).outfits
    ]
    form.outfit.choices = sorted(outfit_choices, key=lambda x: x[1].lower())

    entity.when_year = form.when_year.data or 0
    entity.when_month = form.when_month.data or 0
    entity.when_day = form.when_day.data or 0
    entity.when_hour = form.when_hour.data or 0
    entity.when_minute = form.when_minute.data or 0
    entity.when_second = form.when_second.data or 0
    entity.name = form.name.data or ""
    entity.description = form.description.data or ""
    entity.where = form.where.data or ""
    entity.activity_type_key = form.activity_type_key.data
    entity.intensity = form.intensity.data
    entity.gears = list(form.gears.data) if form.gears.data else []
    entity.outfit = form.outfit.data or ""
    entity.formula = form.formula.data or ""
    if form.exercises.entries:
        for exercise_form in form.exercises.entries:
            entity.exercises.append(from_activity_exercise_form(exercise_form))
    if form.sickness_symptoms.entries:
        for symptom_form in form.sickness_symptoms.entries:
            entity.sickness_symptoms.append(from_activity_symptom_form(symptom_form))
    if form.laps.entries:
        for lap_form in form.laps.entries:
            entity.laps.append(from_activity_lap_form(lap_form))
    entity.hours = form.hours.data or 0
    entity.minutes = form.minutes.data or 0
    entity.seconds = form.seconds.data or 0
    entity.distance = form.distance.data or 0
    entity.warm_up = form.warm_up.data
    entity.cool_down = form.cool_down.data
    entity.commute = form.commute.data
    entity.ranked = form.ranked.data
    entity.race = form.race.data
    entity.kcal = int(form.kcal.data) or 0
    entity.max_speed = float(form.max_speed.data) or 0.0
    entity.elevation_gain = form.elevation_gain.data or 0
    entity.elevation_min = form.elevation_min.data or 0
    entity.elevation_max = form.elevation_max.data or 0
    entity.avg_watts = float(form.avg_watts.data or 0.0)
    entity.max_watts = float(form.max_watts.data or 0.0)
    entity.avg_cadence = int(form.avg_cadence.data or 0)
    entity.max_cadence = int(form.max_cadence.data or 0)
    entity.avg_hr = int(form.avg_hr.data or 0)
    entity.max_hr = int(form.max_hr.data or 0)
    entity.min_hr = int(form.min_hr.data or 0)
    entity.weight = form.weight.data or 0.0
    entity.cost = form.cost.data or 0.0
    entity.weather = form.weather.data
    entity.temperature = form.temperature.data or 0
    entity.suffer_score = form.suffer_score.data or 0.0
    entity.fitness_score = form.fitness_score.data or 0.0
    entity.src = form.src.data or ""
    entity.src_descriptor = form.src_descriptor.data or ""
    entity.src_key = form.src_key.data or ""
    entity.src_url = form.src_url.data or ""
    entity.sort_code = form.sort_code.data or 0
    entity.workout_sort_code = form.workout_sort_code.data or 0

    return entity


class EmptyForm(flask_wtf.FlaskForm):
    """CSRF-protected form to pass it."""


class DeleteTaskForm(flask_wtf.FlaskForm):
    """CSRF-protected form for task deletion."""


class CancelTaskForm(flask_wtf.FlaskForm):
    """CSRF-protected form for task cancellation."""


class CleanupTasksForm(flask_wtf.FlaskForm):
    """CSRF-protected form for cleaning up finished tasks."""


class SubmitHelloWorldForm(flask_wtf.FlaskForm):
    """CSRF-protected form for submitting a hello world test task."""


class MigrateDataForm(flask_wtf.FlaskForm):
    """CSRF-protected form for triggering data migration from the login page."""


class ActivityTypeMigrationForm(flask_wtf.FlaskForm):
    """CSRF-protected form for migrating activities between activity types."""

    from_activity_type = wtforms.SelectField(
        label="From activity type",
        validators=[validators.DataRequired()],
        choices=[],
        validate_choice=False,
    )
    to_activity_type = wtforms.SelectField(
        label="To activity type",
        validators=[validators.DataRequired()],
        choices=[],
        validate_choice=False,
    )
    submit = wtforms.SubmitField("Migrate Activities")


class ImportGsheetsYearCsvForm(flask_wtf.FlaskForm):
    csv_file = flask_wtf.file.FileField(
        label="CSV File",
        validators=[
            flask_wtf.file.FileRequired(),
            flask_wtf.file.FileAllowed(["csv"], "Only .csv files are accepted."),
        ],
    )
    on_conflict = wtforms.RadioField(
        label="If entity already exists",
        choices=[
            ("skip", "Skip"),
            ("override", "Override"),
            ("new_key", "Add as new"),
        ],
        default="skip",
    )
    submit = wtforms.SubmitField("Import CSV")


class ImportGsheetsRacesCsvForm(flask_wtf.FlaskForm):
    csv_file = flask_wtf.file.FileField(
        label="CSV File",
        validators=[
            flask_wtf.file.FileRequired(),
            flask_wtf.file.FileAllowed(["csv"], "Only .csv files are accepted."),
        ],
    )
    on_conflict = wtforms.RadioField(
        label="If entity already exists",
        choices=[
            ("skip", "Skip"),
            ("override", "Override"),
            ("new_key", "Add as new"),
        ],
        default="skip",
    )
    submit = wtforms.SubmitField("Import CSV")


class ImportConcept2CsvForm(flask_wtf.FlaskForm):
    csv_file = flask_wtf.file.FileField(
        label="CSV File",
        validators=[
            flask_wtf.file.FileRequired(),
            flask_wtf.file.FileAllowed(["csv"], "Only .csv files are accepted."),
        ],
    )
    on_conflict = wtforms.RadioField(
        label="If entity already exists",
        choices=[
            ("skip", "Skip"),
            ("override", "Override"),
            ("new_key", "Add as new"),
        ],
        default="skip",
    )
    submit = wtforms.SubmitField("Import CSV")


class ImportGsheetsAllYearsCsvForm(flask_wtf.FlaskForm):
    csv_file = flask_wtf.file.FileField(
        label="CSV File",
        validators=[
            flask_wtf.file.FileRequired(),
            flask_wtf.file.FileAllowed(["csv"], "Only .csv files are accepted."),
        ],
    )
    on_conflict = wtforms.RadioField(
        label="If entity already exists",
        choices=[
            ("skip", "Skip"),
            ("override", "Override"),
            ("new_key", "Add as new"),
        ],
        default="skip",
    )
    submit = wtforms.SubmitField("Import CSV")


class ImportMytralJsonForm(flask_wtf.FlaskForm):
    json_file = flask_wtf.file.FileField(
        label="JSON File",
        validators=[
            flask_wtf.file.FileRequired(),
            flask_wtf.file.FileAllowed(["json"], "Only .json files are accepted."),
        ],
    )
    on_conflict = wtforms.RadioField(
        label="If entity already exists",
        choices=[
            ("skip", "Skip"),
            ("override", "Override"),
            ("new_key", "Add as new"),
        ],
        default="skip",
    )
    submit = wtforms.SubmitField("Import JSON")


class AiProviderForm(flask_wtf.FlaskForm):
    type = wtforms.SelectField(
        choices=[
            ("ollama", "Ollama (recommended — local, private)"),
            ("anthropic", "Anthropic (\u26a0 sends data to 3rd party)"),
            ("openai", "OpenAI (\u26a0 sends data to 3rd party)"),
        ]
    )
    url = wtforms.StringField()
    api_key = wtforms.TextAreaField()
    from_env = wtforms.BooleanField()


class AiModelForm(flask_wtf.FlaskForm):
    provider_key = wtforms.SelectField()
    model_name = wtforms.StringField(validators=[validators.DataRequired()])


class ACoachForm(flask_wtf.FlaskForm):
    name = wtforms.StringField(validators=[validators.DataRequired()])
    model_key = wtforms.SelectField()
    system_prompt = wtforms.TextAreaField(validators=[validators.DataRequired()])


class ACoachMessageForm(flask_wtf.FlaskForm):
    coach_key = wtforms.SelectField()
    content = wtforms.TextAreaField(validators=[validators.DataRequired()])


class UploadAvatarForm(flask_wtf.FlaskForm):
    """Form for uploading a single avatar photo."""

    photo = flask_wtf.file.FileField(
        label="Avatar Photo",
        validators=[flask_wtf.file.FileRequired()],
        description=(
            "Supported formats: .jpg, .jpeg, .png, .gif, .webp — max 10 MiB. "
            "Photo will be cropped to a square and resized to 200×200 pixels."
        ),
    )
    submit = wtforms.SubmitField("Upload Avatar")


class DeleteAvatarForm(flask_wtf.FlaskForm):
    """CSRF-protected form for deleting an avatar."""

    submit = wtforms.SubmitField("Delete Avatar")


class UploadEntityPhotoForm(flask_wtf.FlaskForm):
    """Form for uploading a single entity photo (gear, exercise, goal)."""

    photo = flask_wtf.file.FileField(
        label="Photo",
        validators=[
            flask_wtf.file.FileRequired(),
            flask_wtf.file.FileAllowed(["jpg", "jpeg", "png", "webp"], "Images only."),
        ],
    )
    name = wtforms.StringField(
        label="Name",
        validators=[validators.Optional()],
    )
    description = wtforms.TextAreaField(
        label="Description",
        validators=[validators.Optional()],
    )
    keywords = wtforms.StringField(
        label="Keywords",
        validators=[validators.Optional()],
    )
    submit = wtforms.SubmitField("Upload")


class DeleteEntityPhotoForm(flask_wtf.FlaskForm):
    """CSRF-protected form for deleting an entity photo."""

    submit = wtforms.SubmitField("Delete")


class AthleteMetricsForm(flask_wtf.FlaskForm):
    """Form for setting athlete performance metrics.

    All fields are optional. Leave as 0 to let MyTraL estimate the value.
    """

    # Phase 1: Performance thresholds
    max_hr = wtforms.IntegerField(
        label="Max Heart Rate (BPM)",
        description=(
            "Maximum heart rate measured during a max-effort test. "
            "Leave 0 to use Tanaka formula estimate (208 - 0.7 x age)."
        ),
        validators=[validators.Optional(), validators.NumberRange(0, 250)],
        default=0,
    )
    anaerobic_threshold_hr = wtforms.IntegerField(
        label="Anaerobic Threshold HR / LTHR (BPM)",
        description=(
            "Lactate Threshold Heart Rate - average HR over the last 20 minutes "
            "of a solo 30-minute all-out effort. Leave 0 to estimate."
        ),
        validators=[validators.Optional(), validators.NumberRange(0, 250)],
        default=0,
    )
    aerobic_threshold_hr = wtforms.IntegerField(
        label="Aerobic Threshold HR / LT1 (BPM)",
        description=(
            "Your all-day sustainable pace limit. Leave 0 to estimate "
            "(MAF formula: 180 - age)."
        ),
        validators=[validators.Optional(), validators.NumberRange(0, 250)],
        default=0,
    )
    ftp = wtforms.FloatField(
        label="FTP - Functional Threshold Power (Watts)",
        description=(
            "Maximum average power you can sustain for ~60 minutes. "
            "Leave 0 and MyTraL will estimate from your activity power data "
            "using a duration-scaled model (works for any ride/run 10-240 min)."
        ),
        validators=[validators.Optional(), validators.NumberRange(0.0, 3000.0)],
        default=0.0,
    )

    # Phase 2: Advanced metrics
    vo2max = wtforms.FloatField(
        label="VO2 Max (mL/kg/min)",
        description=(
            "Maximum oxygen uptake. Leave 0 to estimate using Uth-Sorensen formula."
        ),
        validators=[validators.Optional(), validators.NumberRange(0.0, 100.0)],
        default=0.0,
    )
    hrv_rmssd = wtforms.FloatField(
        label="HRV - Overnight RMSSD (ms)",
        description=(
            "Heart Rate Variability rMSSD measured overnight. "
            "Leave 0 to use age-regression baseline estimate."
        ),
        validators=[validators.Optional(), validators.NumberRange(0.0, 300.0)],
        default=0.0,
    )
    fat_max = wtforms.FloatField(
        label="FatMax (g/hr)",
        description="Peak fat oxidation rate. Leave 0 to estimate from body weight.",
        validators=[validators.Optional(), validators.NumberRange(0.0, 500.0)],
        default=0.0,
    )

    # HR Zones — athlete sets upper boundary of each zone (Z1-Z4).
    # Leave all at 0 to auto-estimate from LTHR.
    # All four must be set (> 0) for athlete values to be used.
    z1_high = wtforms.IntegerField(
        label="Z1 upper boundary (BPM)",
        description=(
            "Upper HR boundary of Zone 1 (Recovery). Leave 0 to estimate "
            "as 85% of your LTHR."
        ),
        validators=[validators.Optional(), validators.NumberRange(0, 250)],
        default=0,
    )
    z2_high = wtforms.IntegerField(
        label="Z2 upper boundary (BPM)",
        description=(
            "Upper HR boundary of Zone 2 (Aerobic). Leave 0 to estimate "
            "as 90% of your LTHR."
        ),
        validators=[validators.Optional(), validators.NumberRange(0, 250)],
        default=0,
    )
    z3_high = wtforms.IntegerField(
        label="Z3 upper boundary (BPM)",
        description=(
            "Upper HR boundary of Zone 3 (Tempo). Leave 0 to estimate "
            "as 95% of your LTHR."
        ),
        validators=[validators.Optional(), validators.NumberRange(0, 250)],
        default=0,
    )
    z4_high = wtforms.IntegerField(
        label="Z4 upper boundary (BPM)",
        description=(
            "Upper HR boundary of Zone 4 (Threshold). Leave 0 to estimate "
            "as 106% of your LTHR. Zone 5 always extends to your Max HR."
        ),
        validators=[validators.Optional(), validators.NumberRange(0, 250)],
        default=0,
    )

    # power zone fields (athlete-set boundaries, optional)
    pz1_high = wtforms.IntegerField(
        label="PZ1 upper boundary (W)",
        description=(
            "Upper power boundary of Zone 1 (Recovery). Leave 0 to estimate "
            "as 61% of your FTP."
        ),
        validators=[validators.Optional(), validators.NumberRange(0, 1000)],
        default=0,
    )
    pz2_high = wtforms.IntegerField(
        label="PZ2 upper boundary (W)",
        description=(
            "Upper power boundary of Zone 2 (Endurance). Leave 0 to estimate "
            "as 83% of your FTP."
        ),
        validators=[validators.Optional(), validators.NumberRange(0, 1000)],
        default=0,
    )
    pz3_high = wtforms.IntegerField(
        label="PZ3 upper boundary (W)",
        description=(
            "Upper power boundary of Zone 3 (Tempo). Leave 0 to estimate "
            "as 100% of your FTP."
        ),
        validators=[validators.Optional(), validators.NumberRange(0, 1000)],
        default=0,
    )
    pz4_high = wtforms.IntegerField(
        label="PZ4 upper boundary (W)",
        description=(
            "Upper power boundary of Zone 4 (Threshold). Leave 0 to estimate "
            "as 117% of your FTP."
        ),
        validators=[validators.Optional(), validators.NumberRange(0, 1000)],
        default=0,
    )
    pz5_high = wtforms.IntegerField(
        label="PZ5 upper boundary (W)",
        description=(
            "Upper power boundary of Zone 5 (VO2Max). Leave 0 to estimate "
            "as 133% of your FTP."
        ),
        validators=[validators.Optional(), validators.NumberRange(0, 1000)],
        default=0,
    )
    pz6_high = wtforms.IntegerField(
        label="PZ6 upper boundary (W)",
        description=(
            "Upper power boundary of Zone 6 (Anaerobic). Leave 0 to estimate "
            "as 167% of your FTP."
        ),
        validators=[validators.Optional(), validators.NumberRange(0, 1000)],
        default=0,
    )
    pz7_high = wtforms.IntegerField(
        label="PZ7 upper boundary (W)",
        description=(
            "Upper power boundary of Zone 7 (Neuromuscular). Leave 0 to estimate "
            "as no upper limit. Zone 7 always extends to very high watts."
        ),
        validators=[validators.Optional(), validators.NumberRange(0, 2000)],
        default=0,
    )

    # body composition fields (also editable on athlete metrics page)
    birthday_year = wtforms.IntegerField(
        label="Birth Year",
        description="Year of birth (e.g. 1985).",
        validators=[validators.Optional(), validators.NumberRange(1900, 2100)],
        default=2000,
    )
    birthday_month = wtforms.IntegerField(
        label="Birth Month",
        description="Month of birth (1–12).",
        validators=[validators.Optional(), validators.NumberRange(1, 12)],
        default=1,
    )
    birthday_day = wtforms.IntegerField(
        label="Birth Day",
        description="Day of birth (1–31).",
        validators=[validators.Optional(), validators.NumberRange(1, 31)],
        default=1,
    )
    height = wtforms.FloatField(
        label="Height (m)",
        description="Your height in metres (e.g. 1.75).",
        validators=[validators.Optional(), validators.NumberRange(0.5, 3.0)],
        default=1.75,
    )

    submit = wtforms.SubmitField("Save Metrics")


class ImportPolarHrmForm(flask_wtf.FlaskForm):
    """Form for importing activities from a Polar Precision Performance
    data directory.

    """

    data_dir = wtforms.StringField(
        label="Data directory",
        description=(
            "Absolute path to the directory that contains year sub-directories "
            "with .hrm and .pdd files (e.g. /path/to/John/)."
        ),
        validators=[validators.DataRequired()],
    )
    on_conflict = wtforms.RadioField(
        label="If activity already exists",
        choices=[
            ("skip", "Skip"),
            ("override", "Override"),
            ("new_key", "Add as new"),
        ],
        default="skip",
    )
    submit = wtforms.SubmitField("Import Polar HRM")
