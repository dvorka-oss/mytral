# Feature: Sport Data Recordings datasets
 Status | Reviewers | Last updated | Comment
 --- |  --- |  --- | ---
 DONE | @reviewer | YYYY-MM-DD | .

**Table of contents**

* [Analysis](#analysis)
    * [Why](#why)
    * [Functional Requirements](#functional-requirements)
    * [Functional Non-requirements](#functional-non-requirements)
    * [Technical Requirements](#technical-requirements)
    * [Technical Non-requirements](#technical-non-requirements)
* [Design](#design)
    * [Implementation](#implementation)
    * [Tests](#tests)
    * [Benchmarks](#benchmarks)
* [References](#references)
* [Appendices](#appendices)


# Analysis
_[... abstract ...]_

## Why
_[... motivation and value proposition...]_

## Functional Requirements
_[... functional requirements (feature scope) and user stories...]_

**As** ... **I want to** ... **so that** ...

* Acceptance criteria:
    * _[... optional acceptance criteria...]_

**As** ... **I want to** ... **so that** ...

* Acceptance criteria:
    * _[... optional acceptance criteria...]_

## Functional Non-requirements
_[... functional non-requirements within the scope of this feature - what we will not deliver...]_

## Technical Requirements
_[... technical requirements (including security and performance) and user stories (feature scope)...]_

**As** ... **I want to** ... **so that** ...

* _[... optional acceptance criteria...]_

**As** ... **I want to** ... **so that** ...

* _[... optional acceptance criteria...]_

## Technical Non-requirements
_[... technical non-requirements within the scope of this feature - what will not be implemented...]_

# Design
_[... a design introduction / abstract / high-level highlights]_


## GoldenCheetah OpenData Project
From GC OSF web:

From mid-2018 users of the popular sports analysis desktop application GoldenCheetah have been able to share their workout data to this repository.

Each athlete’s data is shared as a single zip file that contains a summary level description (aggregates, metrics and so on) as a JSON file and additionally, all workout files are stored as CSV files.

The CSV files contain second by second sample data from athlete workouts for; Heartrate, Cadence, Power, Distance and Altitude.

* The data does not contain any PII information.
* The unique id is anonymous, except to the original user.
* The data does not contain any GPS information.
* The data is in the raw format provided by the user.
*  The data is shared for anyone to use.

We are developing tools for working with these data sets, and these can be found on the GoldenCheetah OpenData Github repository.

* [Golde Cheetah OSF dataset Overview](https://osf.io/6hfpz/overview)
   * [Golden Cheetak dataset files](https://osf.io/6hfpz/files/osfstorage)
      * Use "Download As Zip" to download all the files

## Implementation
_[... a brief implementation description and/or diagrams...]_


## Tests
_[... a brief description of unit, integration, load, longevity, regression, manual and smoke tests...]_
## Benchmarks
_[... benchmark(s) and their result...]_
# References
_[... relevant resources...]_

* [Golde Cheetah OSF dataset Overview](https://osf.io/6hfpz/overview)

# Appendices
_[... appendice sections...]_

