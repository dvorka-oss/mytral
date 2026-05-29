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
"""User onboarding management.

Handles onboarding state tracking, progress calculation,
and automatic completion detection for new users.
"""

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mytral import settings

ONBOARDING_PHASE_GETTING_STARTED = "getting_started"
ONBOARDING_PHASE_ADVANCED = "advanced"
ONBOARDING_PHASE_COMPLETED = "completed"

# checklist item keys
ITEM_PROFILE_COMPLETE = "profile_complete"
ITEM_IMPORT_ACTIVITIES = "import_activities"
ITEM_FIRST_ACTIVITY = "first_activity"
ITEM_FIRST_GOAL = "first_goal"
ITEM_FIRST_GEAR = "first_gear"
ITEM_STRAVA_CONNECTED = "strava_connected"
ITEM_ACTIVITY_TYPES_CONFIGURED = "activity_types_configured"
ITEM_EXERCISES_CONFIGURED = "exercises_configured"
ITEM_SYMPTOMS_CONFIGURED = "symptoms_configured"

# basic checklist items (phase 1)
BASIC_CHECKLIST_ITEMS = [
    ITEM_PROFILE_COMPLETE,
    ITEM_IMPORT_ACTIVITIES,
    ITEM_FIRST_ACTIVITY,
    ITEM_FIRST_GOAL,
    ITEM_FIRST_GEAR,
    ITEM_ACTIVITY_TYPES_CONFIGURED,
    ITEM_EXERCISES_CONFIGURED,
    ITEM_SYMPTOMS_CONFIGURED,
]


def get_default_onboarding_state() -> dict:
    """Get default onboarding state for new users.

    Returns
    -------
    dict
        default onboarding state

    """
    return {
        "onboarding_enabled": True,
        "onboarding_dismissed": False,
        "onboarding_dismissed_at": None,
        "onboarding_started_at": int(time.time()),
        "onboarding_phase": ONBOARDING_PHASE_GETTING_STARTED,
        "checklist_items": {
            ITEM_PROFILE_COMPLETE: False,
            ITEM_IMPORT_ACTIVITIES: False,
            ITEM_FIRST_ACTIVITY: False,
            ITEM_FIRST_GOAL: False,
            ITEM_FIRST_GEAR: False,
            ITEM_STRAVA_CONNECTED: False,
            ITEM_ACTIVITY_TYPES_CONFIGURED: False,
            ITEM_EXERCISES_CONFIGURED: False,
            ITEM_SYMPTOMS_CONFIGURED: False,
        },
        "completion_percentage": 0,
    }


def is_onboarding_active(user_profile: "settings.UserProfile") -> bool:
    """Check if onboarding is active for user.

    Parameters
    ----------
    user_profile : UserProfile
        user profile

    Returns
    -------
    bool
        True if onboarding should be shown

    """
    state = user_profile.onboarding_state or {}

    if not state.get("onboarding_enabled", True):
        return False

    if state.get("onboarding_dismissed", False):
        return False

    # check if completed
    if state.get("completion_percentage", 0) >= 100:
        return False

    return True


def get_onboarding_state(user_profile: "settings.UserProfile") -> dict:
    """Get current onboarding state for user.

    Parameters
    ----------
    user_profile : UserProfile
        user profile

    Returns
    -------
    dict
        onboarding state

    """
    if (
        not hasattr(user_profile, "onboarding_state")
        or not user_profile.onboarding_state
    ):
        return get_default_onboarding_state()

    return user_profile.onboarding_state


def update_checklist_item(
    user_profile: "settings.UserProfile", item_key: str, completed: bool
) -> None:
    """Update single checklist item.

    Parameters
    ----------
    user_profile : UserProfile
        user profile
    item_key : str
        checklist item key
    completed : bool
        completion status

    """
    state = get_onboarding_state(user_profile)
    state["checklist_items"][item_key] = completed
    state["completion_percentage"] = calculate_completion_percentage(state)

    user_profile.onboarding_state = state


def calculate_completion_percentage(onboarding_state: dict) -> int:
    """Calculate completion percentage based on checklist items.

    Parameters
    ----------
    onboarding_state : dict
        onboarding state

    Returns
    -------
    int
        completion percentage (0-100)

    """
    items = onboarding_state.get("checklist_items", {})

    # count only basic items for getting_started phase
    total_items = len(BASIC_CHECKLIST_ITEMS)
    completed_items = sum(1 for key in BASIC_CHECKLIST_ITEMS if items.get(key, False))

    if total_items == 0:
        return 100

    return int((completed_items / total_items) * 100)


def dismiss_onboarding(user_profile: "settings.UserProfile") -> None:
    """Permanently dismiss onboarding.

    Parameters
    ----------
    user_profile : UserProfile
        user profile

    """
    state = get_onboarding_state(user_profile)
    state["onboarding_dismissed"] = True
    state["onboarding_dismissed_at"] = int(time.time())

    user_profile.onboarding_state = state


def reset_onboarding(user_profile: "settings.UserProfile") -> None:
    """Reset onboarding to initial state.

    Parameters
    ----------
    user_profile : UserProfile
        user profile

    """
    user_profile.onboarding_state = get_default_onboarding_state()


def auto_check_progress(user_id: str, user_profile: "settings.UserProfile") -> dict:
    """Automatically check onboarding progress based on user data.

    Parameters
    ----------
    user_id : str
        user identifier
    user_profile : UserProfile
        user profile

    Returns
    -------
    dict
        updated onboarding state

    """
    from mytral import app_user_ds as ds
    from mytral import commons

    state = get_onboarding_state(user_profile)
    items = state["checklist_items"]

    # check profile completeness - ensure not bootstrap/default values
    # if ALL defaults are present together, it's bootstrap data
    is_all_bootstrap_defaults = (
        user_profile.born_year == commons.BOOTSTRAP_BORN_YEAR
        and user_profile.born_month == commons.BOOTSTRAP_BORN_MONTH
        and user_profile.born_day == commons.BOOTSTRAP_BORN_DAY
        and user_profile.height == commons.BOOTSTRAP_HEIGHT_CM
    )

    items[ITEM_PROFILE_COMPLETE] = (
        user_profile.height > 0
        and user_profile.born_year > 0
        and user_profile.born_month > 0
        and user_profile.born_day > 0
        and not is_all_bootstrap_defaults  # all values must be changed from defaults
    )

    # check first activity
    activities = ds.list_activities(
        user_id=user_id,
        dataset_name=user_profile.dataset_name,
    )
    items[ITEM_FIRST_ACTIVITY] = len(activities) > 0

    # import activities step: completed once at least one activity exists
    items[ITEM_IMPORT_ACTIVITIES] = len(activities) > 0

    # check first goal
    goals = ds.list_goals(user_id=user_id)
    items[ITEM_FIRST_GOAL] = len(goals.goals_by_key) > 0

    # check first gear OR strava
    gear = ds.list_gear(user_id=user_id, dataset_name=user_profile.dataset_name)
    items[ITEM_FIRST_GEAR] = len(gear.gear_by_key) > 0

    # check strava connected
    items[ITEM_STRAVA_CONNECTED] = bool(
        user_profile.strava_access_token and user_profile.strava_refresh_token
    )

    # check exercises configured
    exercises = ds.list_exercises(user_id=user_id)
    items[ITEM_EXERCISES_CONFIGURED] = not exercises.is_bootstrap_only()

    # check activity types configured
    activity_types = ds.list_activity_types(user_id=user_id)
    items[ITEM_ACTIVITY_TYPES_CONFIGURED] = not activity_types.is_bootstrap_only()

    # check symptoms configured
    symptoms = ds.list_symptoms(user_id=user_id)
    items[ITEM_SYMPTOMS_CONFIGURED] = not symptoms.is_bootstrap_only()

    # update percentage
    state["completion_percentage"] = calculate_completion_percentage(state)

    return state


def get_checklist_display_items(onboarding_state: dict) -> list:
    """Get formatted checklist items for display.

    Parameters
    ----------
    onboarding_state : dict
        onboarding state

    Returns
    -------
    list[dict]
        list of checklist items with display info

    """
    items = onboarding_state.get("checklist_items", {})

    return [
        {
            "key": ITEM_PROFILE_COMPLETE,
            "label": "Complete your profile - birthday and height",
            "completed": items.get(ITEM_PROFILE_COMPLETE, False),
            "url": "/athlete/metrics",
            "icon": "user",
        },
        {
            "key": ITEM_IMPORT_ACTIVITIES,
            "label": "Import your activities",
            "completed": items.get(ITEM_IMPORT_ACTIVITIES, False),
            "url": "/app/tools/import",
            "icon": "file-import",
        },
        {
            "key": ITEM_FIRST_ACTIVITY,
            "label": "Log your first activity",
            "completed": items.get(ITEM_FIRST_ACTIVITY, False),
            "url": "/app/activities/create",
            "icon": "activity",
        },
        {
            "key": ITEM_FIRST_GOAL,
            "label": "Set a training goal",
            "completed": items.get(ITEM_FIRST_GOAL, False),
            "url": "/settings/goals/create",
            "icon": "target",
        },
        {
            "key": ITEM_FIRST_GEAR,
            "label": "Add your first gear",
            "completed": items.get(ITEM_FIRST_GEAR, False),
            "url": "/settings/gears/create",
            "icon": "shoe",
        },
        {
            "key": ITEM_ACTIVITY_TYPES_CONFIGURED,
            "label": "Add your custom activity types",
            "completed": items.get(ITEM_ACTIVITY_TYPES_CONFIGURED, False),
            "url": "/settings/activity-types",
            "icon": "list",
        },
        {
            "key": ITEM_EXERCISES_CONFIGURED,
            "label": "Add your favorite exercises",
            "completed": items.get(ITEM_EXERCISES_CONFIGURED, False),
            "url": "/settings/exercises",
            "icon": "barbell",
        },
        {
            "key": ITEM_SYMPTOMS_CONFIGURED,
            "label": "Review and customize injury symptoms",
            "completed": items.get(ITEM_SYMPTOMS_CONFIGURED, False),
            "url": "/settings/symptoms",
            "icon": "first-aid-kit",
        },
    ]
