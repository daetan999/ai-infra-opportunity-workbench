---
name: ai-infra-opportunity-workbench-conventions
description: Development conventions and patterns for ai-infra-opportunity-workbench. Python Flask project with conventional commits.
---

# Ai Infra Opportunity Workbench Conventions

> Generated from [daetan999/ai-infra-opportunity-workbench](https://github.com/daetan999/ai-infra-opportunity-workbench) on 2026-07-21

## Overview

This skill teaches Claude the development patterns and conventions used in ai-infra-opportunity-workbench.

## Tech Stack

- **Primary Language**: Python
- **Framework**: Flask
- **Architecture**: hybrid module organization
- **Test Location**: separate

## When to Use This Skill

Activate this skill when:
- Making changes to this repository
- Adding new features following established patterns
- Writing tests that match project conventions
- Creating commits with proper message format

## Commit Conventions

Follow these commit message conventions based on 18 analyzed commits.

### Commit Style: Conventional Commits

### Prefixes Used

- `feat`
- `docs`
- `test`
- `build`
- `fix`

### Message Guidelines

- Average message length: ~45 characters
- Keep first line concise and descriptive
- Use imperative mood ("Add feature" not "Added feature")


*Commit message example*

```text
test: define opportunity workflow contract
```

*Commit message example*

```text
build: establish opportunity workbench runtime
```

*Commit message example*

```text
feat: add deterministic opportunity scoring (GREEN: 32 tests, 90% coverage)
```

*Commit message example*

```text
docs: add opportunity workbench visuals
```

*Commit message example*

```text
fix: restore responsive interface tails
```

*Commit message example*

```text
test: define optional narrative guardrails
```

*Commit message example*

```text
test: define opportunity scoring behavior (RED: missing domain package)
```

*Commit message example*

```text
feat: establish opportunity workbench interface
```

## Architecture

### Project Structure: Single Package

This project uses **hybrid** module organization.

### Configuration Files

- `.github/workflows/ci.yml`
- `Dockerfile`

### Guidelines

- This project uses a hybrid organization
- Follow existing patterns when adding new code

## Code Style

### Language: Python

### Naming Conventions

| Element | Convention |
|---------|------------|
| Files | camelCase |
| Functions | camelCase |
| Classes | PascalCase |
| Constants | SCREAMING_SNAKE_CASE |

### Import Style: Relative Imports

### Export Style: Named Exports


*Preferred import style*

```typescript
// Use relative imports
import { Button } from '../components/Button'
import { useAuth } from './hooks/useAuth'
```

*Preferred export style*

```typescript
// Use named exports
export function calculateTotal() { ... }
export const TAX_RATE = 0.1
export interface Order { ... }
```

## Testing

### Test Framework

No specific test framework detected — use the repository's existing test patterns.

### File Pattern: `*.test.ts`

### Test Types

- **Unit tests**: Test individual functions and components in isolation


## Error Handling

### Error Handling Style: Try-Catch Blocks


*Standard error handling pattern*

```typescript
try {
  const result = await riskyOperation()
  return result
} catch (error) {
  console.error('Operation failed:', error)
  throw new Error('User-friendly message')
}
```

## Common Workflows

These workflows were detected from analyzing commit patterns.

### Feature Development

Standard feature implementation workflow

**Frequency**: ~13 times per month

**Steps**:
1. Add feature implementation
2. Add tests for feature
3. Update documentation

**Files typically involved**:
- `**/*.test.*`
- `**/api/**`

**Example commit sequence**:
```
feat: persist opportunity accounts in SQLite
feat: establish opportunity workbench interface
build: establish opportunity workbench runtime
```

### Add Or Update Feature With Tests And Docs

Implements a new feature or significant enhancement, accompanied by tests and technical documentation.

**Frequency**: ~3 times per month

**Steps**:
1. Implement feature logic in one or more app/*.py files
2. Add or update corresponding tests in tests/test_*.py
3. Document the feature or its TDD in docs/testing/*.tdd.md

**Files typically involved**:
- `app/*.py`
- `tests/test_*.py`
- `docs/testing/*.tdd.md`

**Example commit sequence**:
```
Implement feature logic in one or more app/*.py files
Add or update corresponding tests in tests/test_*.py
Document the feature or its TDD in docs/testing/*.tdd.md
```

### Update Interface And Style

Updates the user interface and related styles, often in conjunction with interface contract tests.

**Frequency**: ~3 times per month

**Steps**:
1. Modify HTML templates in templates/index.html
2. Update or add CSS/JS in static/*.css and static/*.js
3. Optionally update or add interface contract tests in tests/test_interface_contract.py

**Files typically involved**:
- `templates/index.html`
- `static/*.css`
- `static/*.js`
- `tests/test_interface_contract.py`

**Example commit sequence**:
```
Modify HTML templates in templates/index.html
Update or add CSS/JS in static/*.css and static/*.js
Optionally update or add interface contract tests in tests/test_interface_contract.py
```

### Add Or Update Documentation And Assets

Adds or updates documentation files and visual assets to reflect new features or changes.

**Frequency**: ~3 times per month

**Steps**:
1. Edit or add markdown docs in docs/*.md or README.md
2. Add or update SVG/PNG assets in docs/assets/
3. Optionally update static assets or templates

**Files typically involved**:
- `README.md`
- `docs/*.md`
- `docs/assets/*`

**Example commit sequence**:
```
Edit or add markdown docs in docs/*.md or README.md
Add or update SVG/PNG assets in docs/assets/
Optionally update static assets or templates
```

### Add Or Update Persistence Layer

Implements or modifies data persistence logic, including models and repositories, with corresponding tests and TDD docs.

**Frequency**: ~2 times per month

**Steps**:
1. Edit or add models in app/models.py
2. Edit or add repository logic in app/repository.py
3. Update or add tests in tests/test_repository.py
4. Document persistence logic in docs/testing/opportunity-persistence.tdd.md

**Files typically involved**:
- `app/models.py`
- `app/repository.py`
- `tests/test_repository.py`
- `docs/testing/opportunity-persistence.tdd.md`

**Example commit sequence**:
```
Edit or add models in app/models.py
Edit or add repository logic in app/repository.py
Update or add tests in tests/test_repository.py
Document persistence logic in docs/testing/opportunity-persistence.tdd.md
```


## Best Practices

Based on analysis of the codebase, follow these practices:

### Do

- Use conventional commit format (feat:, fix:, etc.)
- Follow *.test.ts naming pattern
- Use camelCase for file names
- Prefer named exports

### Don't

- Don't write vague commit messages
- Don't skip tests for new features
- Don't deviate from established patterns without discussion

---

*This skill was auto-generated by [ECC Tools](https://ecc.tools). Review and customize as needed for your team.*
