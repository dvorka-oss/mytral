## Activity Normalization

## Activity Data Model

MyTraL normalizes all training activities from various sources into a unified JSON data structure. This normalization ensures consistency across different data sources and enables comprehensive analysis and visualization of your training history.

An **Activity** is the fundamental building block of a workout. A typical workout consists of multiple activities: warm-up, main workout, and cool-down. Activities are grouped into workouts using the `workout_sort_code` field.

## Core Entity Fields

All activities inherit base fields from the `DbEntity` class:

Field | Type | Default | Description
---|---|---|---
`key` | string | "" | Unique identifier for the activity
`name` | string | "" | Human-readable name of the activity
`description` | string | "" | Detailed description or notes about the activity
`when_year` | int | 0* | Year when the activity occurred
`when_month` | int | 0* | Month when the activity occurred (1-12)
`when_day` | int | 0* | Day when the activity occurred (1-31)
`when_hour` | int | 0* | Hour when the activity started (0-23)
`when_minute` | int | 0* | Minute when the activity started (0-59)
`when_second` | int | 0* | Second when the activity started (0-59)
`when` | string | "" | ISO formatted timestamp string (auto-generated from the components above)

\* Default is 0, but `__post_init__` fills in the current date/time when all components are zero.

## Activity-Specific Fields

## Workout Organization

Field | Type | Default | Description
---|---|---|---
`sort_code` | int | 1 | Order of this activity within the workout (1-based)
`workout_sort_code` | int | 1 | Identifier grouping activities into a workout. Morning workouts have lower codes than evening workouts
`tags` | list[str] | [] | User-defined tags for categorization and filtering
`is_plan` | bool | false | Indicates if this is a planned (future) activity rather than a completed one

## Basic Activity Information

Field | Type | Default | Description
---|---|---|---
`where` | string | "" | Location where the activity took place
`activity_type_key` | string | "run" | Type of sport: run, ride, rowing, ski, rollerski, swim, etc. (open enum)
`intensity` | string | "easy" | Intensity level: easy, hard, regen, LSD, fartlek, tempo, race, etc. (open enum)
`gears` | list[str] | [] | Equipment used (e.g., bike names, shoe models)
`outfit` | string | "" | Outfit/clothing worn during the activity
`formula` | string | "" | Workout formula using DSL: e.g., "3*(2k/r30s + 3k/r20s)" or "3*(10*squats + 5*crunches)"

## Duration and Distance

Field | Type | Default | Description
---|---|---|---
`hours` | int | 0 | Duration hours component
`minutes` | int | 0 | Duration minutes component (0-59)
`seconds` | int | 0 | Duration seconds component (0-59)
`distance` | int | 0 | Distance covered in meters

## Activity Flags

Field | Type | Default | Description
---|---|---|---
`warm_up` | bool | false | Indicates if this is a warm-up activity
`cool_down` | bool | false | Indicates if this is a cool-down activity
`commute` | bool | false | Indicates if this was a commute activity
`race` | bool | false | Indicates if this was a race/competition
`ranked` | bool | false | Indicates if this activity is used for personal records (like Concept2 rankings)

## Performance Metrics

Field | Type | Default | Description
---|---|---|---
`kcal` | int | 0 | Calories burned (kcal)
`max_speed` | float | 0.0 | Maximum speed in km/h
`elevation_gain` | int | 0 | Total elevation gain in meters
`elevation_min` | int | 0 | Minimum elevation in meters
`elevation_max` | int | 0 | Maximum elevation in meters
`avg_watts` | float | 0.0 | Average power output in watts
`max_watts` | float | 0.0 | Maximum power output in watts
`avg_cadence` | float | 0.0 | Average cadence in revolutions/strokes per minute
`max_cadence` | float | 0.0 | Maximum cadence in revolutions/strokes per minute
`avg_hr` | float | 0.0 | Average heart rate in bpm
`max_hr` | float | 0.0 | Maximum heart rate in bpm
`min_hr` | float | 0.0 | Minimum/resting heart rate in bpm (day-level metric, not activity-specific)
`fitness_score` | float | 0.0 | Fitness/form score

## Body Metrics & Environment

Field | Type | Default | Description
---|---|---|---
`weight` | float | 0.0 | Body weight in kg at time of activity
`cost` | float | 0.0 | Monetary cost of the activity (e.g., gym entry, sauna, race fee)
`weather` | string | "" | Weather conditions: cloudy, sunny, windy, rainy, etc.
`temperature` | int | 18 | Temperature in Celsius

## Source Tracking

Field | Type | Default | Description
---|---|---|---
`src` | string | "manual" | Data source: manual, strava-import, concept2-import, paper-import, etc.
`src_descriptor` | string | "" | Additional source information (e.g., "green paper log book '97")
`src_key` | string | "" | External service ID (e.g., Strava activity UUID)
`src_url` | string | "" | Link to original activity (e.g., Strava activity URL)

## Recording & Media Blobs

Field | Type | Default | Description
---|---|---|---
`recorded_blob_keys` | list[str] | [] | Blobstore keys pointing to original recording files (.fit, .gpx, .hrm, etc.) in `UUID.ext` format
`recorded_parquet_keys` | dict[str, str] | {} | Map from recording blob UUID (without suffix) to Parquet blob key for efficient data querying
`photo_blob_keys` | list[str] | [] | Blobstore keys pointing to activity photos
`highlight_photo_blob_key` | string | "" | Blobstore key pointing to the activity's highlight/featured photo

## Calculated Fields (Transient)

These fields are calculated from input values and are not stored in the database:

Field | Type | Default | Description
---|---|---|---
`duration` | string | "" | Formatted duration string: "HHhMMmSSs"
`duration_seconds` | int | 0 | Total duration in seconds
`exercise_kgs` | float | 0.0 | Total weight lifted (kg) from exercises
`avg_speed` | float | 0.0 | Average speed in km/h
`pace` | string | "" | Pace as min/km
`bmi` | float | 0.0 | Body Mass Index calculated from weight and height
`burnt_fat` | float | 0.0 | Estimated fat burned in grams

## Nested Entities

## Exercises

Activities can contain multiple exercise entities for strength training:

Field | Type | Default | Description
---|---|---|---
`activity_key` | string | "" | Reference to parent activity
`name` | string | "" | Exercise name (e.g., "squats", "bench press")
`weight` | float | 0.0 | Weight used in kg
`series` | int | 0 | Number of sets
`repetitions` | int | 0 | Repetitions per set
`duration` | int | 0 | Exercise duration in seconds
`rest` | int | 0 | Rest period in seconds

## Laps

Activities can contain multiple lap entities for interval training:

Field | Type | Default | Description
---|---|---|---
`activity_key` | string | "" | Reference to parent activity
`order` | int | 0 | Order of the lap within the activity (1, 2, 3, ...)
`name` | string | "" | Reference to standalone lap type or custom name
`distance` | int | 0 | Distance in meters (overrides default from lap type if set)
`duration` | int | 0 | Duration in seconds (overrides default from lap type if set)
`comment` | string | "" | Additional notes for this specific lap
`ranked` | bool | false | Ranked lap used to build personal bests/records

## Sickness Symptoms

Activities can track illness or injury symptoms:

Field | Type | Default | Description
---|---|---|---
`activity_key` | string | "" | Reference to parent activity
`symptom` | string | "" | Symptom description (injury or disease)
`side` | string | "" | Body side affected: "left", "right", or "" for both/general
`body_part` | string | "" | Affected body part (e.g., "knee", "shoulder")
`health` | int | 0 | Health percentage: 100 = fully healthy, 0 = severely sick/injured

## JSON Example

Example of a normalized running activity in JSON format:
```
{
  "key": "2024-01-15-123456",
  "name": "Morning Run",
  "description": "Easy recovery run along the river",
  "when_year": 2024,
  "when_month": 1,
  "when_day": 15,
  "when_hour": 7,
  "when_minute": 30,
  "when_second": 0,
  "when": "2024-01-15 07:30:00",
  "sort_code": 1,
  "workout_sort_code": 1,
  "tags": ["recovery", "aerobic"],
  "is_plan": false,
  "where": "Prague riverside",
  "activity_type_key": "run",
  "intensity": "easy",
  "gears": ["Nike Pegasus 40"],
  "outfit": "",
  "hours": 0,
  "minutes": 45,
  "seconds": 30,
  "distance": 8500,
  "kcal": 650,
  "max_speed": 14.2,
  "elevation_gain": 85,
  "avg_watts": 0.0,
  "avg_cadence": 0.0,
  "avg_hr": 145.0,
  "max_hr": 162.0,
  "min_hr": 0.0,
  "weight": 75.5,
  "cost": 0.0,
  "weather": "cloudy",
  "temperature": 8,
  "src": "strava-import",
  "src_key": "1234567890",
  "src_url": "https://www.strava.com/activities/1234567890",
  "recorded_blob_keys": [],
  "recorded_parquet_keys": {},
  "photo_blob_keys": [],
  "highlight_photo_blob_key": "",
  "duration": "00h45m30s",
  "duration_seconds": 2730,
  "avg_speed": 11.2,
  "pace": "5:21",
  "exercises": [],
  "laps": [],
  "sickness_symptoms": []
}
```

## Conventions and Best Practices

  * **Zero as unused value:** 0 represents an unused or unset value for numeric fields
  * **1-based indexing:** Sort codes and workout identifiers start from 1, not 0
  * **Open enums:** Fields like `activity_type_key`, `intensity`, and `src` use open enumeration - new values are automatically accepted
  * **Sparse storage:** Only non-default values are persisted to disk using `to_sparse_dict()` method
  * **Transient fields:** Calculated fields are marked in `ACTIVITY_TRANSIENT_FIELDS` set and excluded from database storage
  * **Metric units:** All measurements use metric units (meters, kg, Celsius, km/h)
  * **Time components:** Duration is stored as separate hour/minute/second components for easier querying and display
