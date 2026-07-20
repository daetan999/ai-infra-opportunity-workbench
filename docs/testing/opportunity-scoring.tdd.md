# Opportunity scoring TDD evidence

## Source and journeys

No external plan file was used. The acceptance criteria were derived from the
Opportunity Workbench build brief.

- As an account team, we can score all ten qualification areas from explicit
  evidence and understand every component score.
- As a reviewer, we can compare current and prior scores without a model call or
  non-deterministic behavior.
- As a sales leader, we receive a stable Advance, Reshape, Nurture, or Disqualify
  recommendation plus PoC readiness and single-threading risk.
- As a discovery lead, we receive questions assigned to the stakeholder role
  best able to close each evidence gap.
- As a governance reviewer, we can confirm that activity volume never stands in
  for qualifying evidence and that invalid ranges and roles fail at the boundary.

## RED and GREEN evidence

### RED

Command:

```text
python -m pytest -q tests/test_scoring.py
```

Result: collection failed with `ModuleNotFoundError: No module named
'app.domain'; 'app' is not a package`. This was the intended missing-domain
failure before any production module was added. The checkpoint is commit
`41b9dd4`.

### GREEN

Focused command:

```text
COVERAGE_FILE=.coverage.scoring python -m pytest tests/test_scoring.py -q \
  --cov=app.domain --cov=app.scoring --cov-report=term-missing --cov-fail-under=80
```

Result: `32 passed`; total coverage for the owned `app` modules was `90.45%`
(`app/domain.py` 96%, `app/scoring.py` 98%; the compatibility package loader was
44% in the focused test process).

Full regression command:

```text
python -m pytest -q --no-cov
```

Result: `36 passed`. One upstream `StarletteDeprecationWarning` reports that the
existing FastAPI test client should eventually use `httpx2`; it does not affect
the scoring seam.

## Test specification

| Guarantee | Test type | Result |
|---|---|---|
| All ten evidence-backed components total to 100 maximum and produce reasons | Unit | PASS |
| High, medium, low, and exact Advance-boundary opportunities route deterministically | Unit | PASS |
| Unsupported activity does not increase a component or recommendation | Unit | PASS |
| Complete history produces component and total deltas; partial history avoids a misleading total delta | Unit | PASS |
| Engaged role breadth produces High, Medium, or Low single-threading risk | Unit | PASS |
| PoC readiness requires technical fit, evidence access, timing, process clarity, and a technical partner | Unit | PASS |
| Discovery questions are typed, role-specific, and ordered with weakest evidence first | Unit | PASS |
| Scores, prior scores, activity counts, roles, evidence, duplicate areas, and duplicate stakeholders are validated | Unit | PASS |
| Inputs and results reject attribute mutation | Unit | PASS |
| Existing health and deterministic account-intelligence API behavior remains intact | Integration | PASS |

## Integration API

Call `score_opportunity(assessment: OpportunityAssessment) -> OpportunityScore`.
Construct exactly one frozen `QualificationSignal` for every member of
`ALL_QUALIFICATION_AREAS` and optionally provide one frozen
`StakeholderEngagement` per role. Each `evidence_score` is a qualification
strength from 0 through 10. For `PROCUREMENT_FRICTION`, a higher strength means
the friction is understood and mitigated, not that more friction is desirable.

If a signal has no evidence items, its effective score is zero even when its
reported activity count or proposed evidence score is high. All returned values
are frozen typed records and enums, and scoring performs no I/O or model call.

## Coverage and known gaps

The focused 90.45% result exceeds the required 80%; the integrated suite later
reached 96% branch coverage across the complete application. Browser validation
belongs to the workbench interface layer rather than this pure domain seam.
