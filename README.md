# FPO Parakh (FPO Rating Tool)

FPO Parakh helps assess farmer producer organisations across governance, business operations, processes and financial performance. This repository contains the Django administration and web application for managing FPO information, verification, ratings and reports. The FPO mobile app is a separate component.

## Relevance to the Sustainable Development Goals

- **SDG 2, Zero Hunger (target 2.3):** farmer producer organisations aggregate smallholders. Rating their governance, business, systems and finances helps support agencies strengthen them.
- **SDG 8, Decent Work and Economic Growth (target 8.3):** the tool supports the formalisation of farmer-owned enterprises and their access to finance.

## Features

- Manage FPO profiles and annual submissions.
- Review and verify FPO registrations and information.
- Calculate ratings and generate reports.
- Manage access through user roles.
- Expose GraphQL and selected HTTP endpoints for supported clients.
- Use optional services for document processing and mapping.

## Requirements

- Python 3.12 or later and [uv](https://docs.astral.sh/uv/).
- SQLite for basic local development or PostgreSQL when configured through `DATABASE_URL`.
- External services and credentials only for the integrations your deployment uses.

## Local setup

```bash
git clone https://github.com/intellecap-weia-fpo/fpo-parakh.git
cd fpo-parakh
uv sync
cp .env.example .env
```

Configure `SECRET_KEY`, `DEBUG`, allowed hosts and any required service credentials in the environment or `.env`. Never commit credentials. The application uses SQLite if `DATABASE_URL` is not set; use a PostgreSQL connection string when deploying with PostgreSQL. See `one/settings.py` and `.env.example` for the available settings.

Apply migrations, create an administrator and start the development server:

```bash
uv run python manage.py migrate
uv run python manage.py createsuperuser
uv run python manage.py runserver
```

The GraphQL endpoint is available at `/graphql/` when the application is running. Configure any AI provider and other external integrations separately if your deployment uses them.

## Data and integrations

This repository contains no real FPO data, credentials or map boundary files. Each deployment supplies its own data.

| Service | Used for | Required? | Open alternative |
|---|---|---|---|
| Any OpenAI-compatible LLM endpoint (`OPENAI_API_BASE_URL`, `OPENAI_API_KEY`) | Document pre-fill | No | A self-hosted server such as Ollama or vLLM |
| Mapbox GL JS (`MAPBOX_ACCESS_TOKEN`) | Reports map | No, but the reports map needs it today | None configured yet |

Set `DEBUG=True` in `.env` for local development; outside DEBUG the app will not start without `SECRET_KEY`.

## Accounts

Self-registration is off by default. Set `ALLOW_SIGNUP=True` to turn it on; otherwise administrators create accounts.

## Data export

Administrators export FPO lists and scores as CSV, and supported clients read data through the GraphQL API at `/graphql/` and the JSON endpoints in `fpo/urls.py`.

## Development

Use Django's management commands through `uv run python manage.py`. For example, run `uv run python manage.py check` to check the project configuration. Review security, access control and external-service settings before production deployment.

## Community

See the [privacy notice](PRIVACY.md), [CONTRIBUTING.md](CONTRIBUTING.md), [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md), [SECURITY.md](SECURITY.md) and the [content policy](docs/content-policy.md).

## Copyright and licence

Copyright (C) 2025-2026 IntelleCap Advisory Services Pvt. Ltd. Licensed under the GNU Affero General Public License v3.0 only; see [LICENSE](LICENSE) and [NOTICE](NOTICE). The documentation is licensed under CC BY 4.0.
