---
name: add-or-update-feature-with-tests-and-docs
description: Workflow command scaffold for add-or-update-feature-with-tests-and-docs in ai-infra-opportunity-workbench.
allowed_tools: ["Bash", "Read", "Write", "Grep", "Glob"]
---

# /add-or-update-feature-with-tests-and-docs

Use this workflow when working on **add-or-update-feature-with-tests-and-docs** in `ai-infra-opportunity-workbench`.

## Goal

Implements a new feature or significant enhancement, accompanied by tests and technical documentation.

## Common Files

- `app/*.py`
- `tests/test_*.py`
- `docs/testing/*.tdd.md`

## Suggested Sequence

1. Understand the current state and failure mode before editing.
2. Make the smallest coherent change that satisfies the workflow goal.
3. Run the most relevant verification for touched files.
4. Summarize what changed and what still needs review.

## Typical Commit Signals

- Implement feature logic in one or more app/*.py files
- Add or update corresponding tests in tests/test_*.py
- Document the feature or its TDD in docs/testing/*.tdd.md

## Notes

- Treat this as a scaffold, not a hard-coded script.
- Update the command if the workflow evolves materially.