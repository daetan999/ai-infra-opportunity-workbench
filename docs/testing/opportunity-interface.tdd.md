# Opportunity interface TDD record

This note records the small contract-test cycles used to replace the legacy account-intelligence page with the Opportunity Workbench presentation seam.

## Contract under test

The template is server-rendered and remains useful without JavaScript. Its public interface is the Jinja context supplied by the web route:

| Context key | Expected shape | Used for |
|---|---|---|
| `accounts` | list of account mappings | Portfolio list and summary count |
| `account` | selected account mapping | Workspace identity, workload hypothesis, and next action |
| `score` | mapping with `overall`, `dimensions`, and `risks` | Qualification scorecard and risk register |
| `poc` | mapping with `ready`, `label`, and `criteria` | PoC readiness gate |
| `questions` | list of strings or question mappings | Priority discovery questions |
| `signals` | list of dated evidence mappings | Signal timeline and provenance |
| `stakeholders` | list of stakeholder mappings | Buying-group coverage |
| `discoveries` | list of finding mappings | Validated findings and open evidence gaps |

Every key has a safe empty-state default in the template. JavaScript only enhances account filtering, mobile navigation, active-section state, and the browser print dialog.

## Cycle 1 — operator journey

RED: `test_workbench_exposes_the_operator_journey` failed because the legacy single-form page did not expose portfolio, workspace, evidence, decision, risk, readiness, or export surfaces.

GREEN: replaced the page shell with semantic navigation and the complete evidence-to-decision workflow. Checkpoint: `9b022a0`.

## Cycle 2 — accessibility and progressive enhancement

RED: `test_interface_is_local_accessible_and_progressively_enhanced` failed because the inherited styles had no explicit focus-visible or reduced-motion behavior and the inherited script required the deleted analysis form.

GREEN: added local system-font styling, responsive navigation, visible focus states, reduced-motion handling, print output, account filtering, and null-safe JavaScript. Checkpoint: `8046bd2`.

## Cycle 3 — documentation visuals

RED: `test_documentation_visuals_are_self_contained_and_readable` failed while the required Opportunity Workbench assets were absent.

GREEN: added accessible, self-contained workflow and qualification SVGs with descriptive titles and no remote image or font dependencies:

- `docs/assets/opportunity-workflow.svg`
- `docs/assets/qualification-model.svg`

The original synthetic hero SVG was later replaced by two tracked 1440×900 screenshots captured from the seeded application. The interface contract now verifies their PNG signatures and dimensions:

- `docs/assets/opportunity-dashboard.png`
- `docs/assets/opportunity-account-workspace.png`

## Verification

Run the isolated interface contract with the main worktree virtual environment:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
  /path/to/main-worktree/.venv/bin/python -m pytest \
  -c /dev/null -o cache_dir=/tmp/opportunity-interface-pytest \
  -q tests/test_interface_contract.py
```

The isolated configuration is intentional: the parent worktree may be changing its coverage configuration concurrently, while this branch owns only the presentation seam. Also run:

```bash
node --check static/app.js
git diff --check
```

The inherited full test suite could not be collected in the shared virtual environment at the start of this seam because FastAPI and Jinja2 were not installed there. This is an environment baseline limitation rather than an interface-contract failure.
