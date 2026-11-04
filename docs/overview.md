# Overview

FPO Parakh rates farmer producer organisations (FPOs). An FPO fills in a yearly assessment in the [mobile app](https://github.com/intellecap-weia-fpo/fpo-parakh-mobile) or on the web, and gets a weighted score and a report. Administrators verify FPOs and review the results.

## Use cases

- **FPO officer:** registers the FPO, completes the yearly assessment, uploads documents and downloads the report.
- **Administrator:** verifies FPOs, reviews submissions, manages users and exports data.
- **Support agency or programme team:** compares FPOs by theme, state and year on the reports and map pages.

## Scoring

The total score is out of 100. It combines four themes, weighted by the FPO's age (`fpo/score_calculator.py`):

| FPO age | Governance and management | Business and operations | Processes and systems | Financial performance |
|---|---|---|---|---|
| Below 1 year | 40% | 20% | 25% | 15% |
| 1 to 3 years | 35% | 20% | 25% | 20% |
| 3 to 5 years | 30% | 25% | 20% | 25% |
| 5 years and above | 25% | 30% | 15% | 30% |

The assessment sections are defined as JSON schemas in `fpo/json_schemas/`.

## Architecture

| Part | Role |
|---|---|
| `fpo/` | FPOs, yearly submissions, scoring, reports, map, exports |
| `auth_app/`, `management/` | Accounts, roles and user management |
| `neo/` | Shared site configuration, language and email helpers |
| `one/` | Django settings, URLs and the combined GraphQL schema |

It is a Django application with a Graphene GraphQL API at `/graphql/`, using SQLite or PostgreSQL. Configuration comes from the environment; see `.env.example`.

## Getting data out

- **CSV:** `fpos/export/` for FPO lists and scores, and `fpos/<id>/export/` for one FPO.
- **JSON:** `api/fpo-listing/`, `api/fpo-detail/`, `api/fpo-locations/`, `api/fpo-state-counts/`, `api/state-stats/` and others in `fpo/urls.py`. Public endpoints leave out email, phone and address.
- **PDF:** a report per submission.
- **GraphQL:** `/graphql/`.
