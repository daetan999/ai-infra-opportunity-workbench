---
name: update-interface-and-style
description: Workflow command scaffold for update-interface-and-style in ai-infra-opportunity-workbench.
allowed_tools: ["Bash", "Read", "Write", "Grep", "Glob"]
---

# /update-interface-and-style

Use this workflow when working on **update-interface-and-style** in `ai-infra-opportunity-workbench`.

## Goal

Updates the user interface and related styles, often in conjunction with interface contract tests.

## Common Files

- `templates/index.html`
- `static/*.css`
- `static/*.js`
- `tests/test_interface_contract.py`

## Suggested Sequence

1. Understand the current state and failure mode before editing.
2. Make the smallest coherent change that satisfies the workflow goal.
3. Run the most relevant verification for touched files.
4. Summarize what changed and what still needs review.

## Typical Commit Signals

- Modify HTML templates in templates/index.html
- Update or add CSS/JS in static/*.css and static/*.js
- Optionally update or add interface contract tests in tests/test_interface_contract.py

## Notes

- Treat this as a scaffold, not a hard-coded script.
- Update the command if the workflow evolves materially.