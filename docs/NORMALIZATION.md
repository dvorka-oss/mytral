## Activity Normalization

## Activity Data Model

MyTraL normalizes all training activities from various sources (Strava, Concept2, Google Sheets, paper logs) into a unified JSON data structure. This normalization ensures consistency across different data sources and enables comprehensive analysis and visualization of your training history.

An **Activity** is the fundamental building block of a workout. A typical workout consists of multiple activities: warm-up, main workout, and cool-down. Activities are grouped into workouts using the `workout_sort_code` field.

## Core Entity Fields

All activities inherit base fields from the `DbEntity` class:

Field | Type | Default | Description
---|---|---|---
`key` | string | "" | Unique identifier for the activity
`name` | string | "" | Human-readable name of the activity
`description` | string | "" | Detailed description or notes about the activity
`when_year` | int | current year | Year when the activity occurred
`when_month` | int | current month | Month when the activity occurred (1-12)
`when_day` | int | current day | Day when the activity occurred (1-31)
`when_hour` | int | current hour | Hour when the activity started (0-23)
`when_minute` | int | current minute | Minute when the activity started (0-59)
`when_second` | int | current second | Second when the activity started (0-59)
`when` | string | "" | ISO formatted timestamp string (auto-generated)

## Activity-Specific Fields

## Workout Organization

Field | Type | Default | Description
---|---|---|---
`sort_code` | int | 1 | Order of this activity within the workout (1-based)
`workout_sort_code` | int | 1 | Identifier grouping activities into a workout. Morning workouts have lower codes than evening workouts

## Basic Activity Information

Field | Type | Default | Description
---|---|---|---
`where` | string | "" | Location where the activity took place
`sport` | string | "run" | Type of sport: run, ride, rowing, ski, rollerski, swim, etc. (open enum)
`intensity` | string | "easy" | Intensity level: easy, hard, regen, LSD, fartlek, tempo, race, etc. (open enum)
`gear` | string | "" | Equipment used (e.g., bike name, shoe model)
`formula` | string | "" | Workout formula using DSL: e.g., "3*(2k/r30s + 3k/r20s)" or "3*(10*squats + 5*crunches)"

## Duration and Distance

Field | Type | Default | Description
---|---|---|---
`hours` | int | 0 | Duration hours component
`minutes` | int | 30 | Duration minutes component (0-59)
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
`avg_watts` | int | 0 | Average power output in watts
`max_watts` | int | 0 | Maximum power output in watts
`avg_hr` | int | 0 | Average heart rate in bpm
`max_hr` | int | 0 | Maximum heart rate in bpm
`min_hr` | int | 0 | Minimum heart rate in bpm
`suffer_score` | float | 0.0 | Strava's suffer score metric
`fitness_score` | float | 0.0 | Fitness/form score

## Body Metrics & Environment

Field | Type | Default | Description
---|---|---|---
`weight` | float | 0.0 | Body weight in kg at time of activity
`weather` | string | "" | Weather conditions: cloudy, sunny, windy, rainy, etc.
`temperature` | int | 18 | Temperature in Celsius

## Source Tracking

Field | Type | Default | Description
---|---|---|---
`src` | string | "manual" | Data source: manual, strava-import, concept2-import, paper-import, etc.
`src_descriptor` | string | "" | Additional source information (e.g., "green paper log book '97")
`src_key` | string | "" | External service ID (e.g., Strava activity UUID)
`src_url` | string | "" | Link to original activity (e.g., Strava activity URL)

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
  "when": "2024-01-15T07:30:00",
  "sort_code": 1,
  "workout_sort_code": 1,
  "where": "Prague riverside",
  "sport": "run",
  "intensity": "easy",
  "gear": "Nike Pegasus 40",
  "hours": 0,
  "minutes": 45,
  "seconds": 30,
  "distance": 8500,
  "kcal": 650,
  "max_speed": 14.2,
  "elevation_gain": 85,
  "avg_hr": 145,
  "max_hr": 162,
  "weight": 75.5,
  "weather": "cloudy",
  "temperature": 8,
  "src": "strava-import",
  "src_key": "1234567890",
  "src_url": "https://www.strava.com/activities/1234567890",
  "duration": "00h45m30s",
  "duration_seconds": 2730,
  "avg_speed": 11.2,
  "pace": "5:21",
  "exercises": [],
  "sickness_symptoms": []
}
```

## Conventions and Best Practices

  * **Zero as unused value:** 0 represents an unused or unset value for numeric fields
  * **1-based indexing:** Sort codes and workout identifiers start from 1, not 0
  * **Open enums:** Fields like `sport`, `intensity`, and `src` use open enumeration - new values are automatically accepted
  * **Sparse storage:** Only non-default values are persisted to disk using `to_sparse_dict()` method
  * **Transient fields:** Calculated fields are marked in `transient_fields` dictionary and excluded from database storage
  * **Metric units:** All measurements use metric units (meters, kg, Celsius, km/h)
  * **Time components:** Duration is stored as separate hour/minute/second components for easier querying and display
