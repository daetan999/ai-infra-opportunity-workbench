# Opportunity workflow TDD evidence

## Source and journeys

Journeys were derived from the portfolio brief supplied for this build.

1. A BDR creates an account, records attributable buying signals, defines a workload, and maps the buying group.
2. An AE reviews an evidence-based score, missing information, single-threading risk, and a deterministic progression recommendation.
3. A technical seller assesses PoC readiness and exports a structured BDR-to-AE handoff without an external model or API key.
4. A reviewer can distinguish fictional demonstrations, user-provided information, hypotheses, verified facts, and generated suggestions.

## RED evidence

Command:

```bash
.venv/bin/python -m pytest -vv tests/test_workflow_api.py
```

Expected result: collection failed with `ModuleNotFoundError: No module named 'app.main'; 'app' is not a package`. The failing contract was committed as `test: define opportunity workflow contract` before production implementation.

The optional narrative guardrail contract separately failed on the missing `app.enrichment` module before implementation.

## GREEN evidence

The environment-provided pytest-cov plugin stalled, so coverage was collected with coverage.py directly while disabling the plugin:

```bash
SEED_DEMO_DATA=false \
DATABASE_URL=sqlite:////tmp/opportunity-coverage-full.db \
PYTHONPATH=/path/to/isolated/dependencies \
python -m coverage run --branch --source=app \
  -m pytest -q -p no:pytest_cov -o addopts=''

COVERAGE_FILE=/tmp/opportunity.coverage.full \
python -m coverage report --show-missing --fail-under=80
```

Result: `66 passed`; total branch coverage `96%`.

Lint:

```bash
ruff check app
ruff check tests
```

Result: both commands reported `All checks passed!`.

## Guarantee index

| Guarantee | Evidence | Type | Result |
|---|---|---|---|
| Account, signal, workload, stakeholder, and discovery records persist in SQLite | `tests/test_repository.py` | Unit/integration | PASS |
| Evidence provenance and confidence reject unsupported values | `tests/test_repository.py`, `tests/test_workflow_api.py` | Boundary/API | PASS |
| Activity volume cannot increase an unsupported qualification score | `tests/test_scoring.py` | Unit | PASS |
| Score components, changes, missing evidence, risk, recommendation, PoC readiness, and questions are explainable | `tests/test_scoring.py` | Unit | PASS |
| A complete account workflow produces a structured handoff and Markdown export | `tests/test_workflow_api.py` | API/workflow | PASS |
| Three seeded demonstrations are explicitly fictional | `tests/test_workflow_api.py` | Integration | PASS |
| The server-rendered interface exposes the required decision surfaces | `tests/test_interface_contract.py` | Smoke/contract | PASS |
| Optional narrative output is labelled and falls back offline | `tests/test_enrichment.py` | Unit/error path | PASS |

## Known gaps

- Browser screenshots and browser-level smoke checks are performed after the integrated application is launched.
- Docker cannot be executed in the current environment because a Docker runtime is unavailable; the image definition is still reviewed and CI-ready.
- Optional model wording cannot guarantee factuality on its own; generated text remains labelled as a suggestion and never alters deterministic scores.
