# Opportunity persistence TDD evidence

## Contract

`Database` owns SQLAlchemy engine, schema, transaction, rollback, session-close,
SQLite foreign-key, and disposal behavior. `OpportunityRepository` is the caller
seam and never returns live ORM instances.

```python
database = Database("sqlite:///opportunities.db")
database.create_schema()
repository = OpportunityRepository(database)

account = repository.create_account(
    name="Northstar Health (Fictional)",
    industry="Healthcare",
    geography="Singapore",
    segment="Enterprise",
)
repository.get_account(account["id"])
repository.list_accounts()
repository.add_related(account["id"], "signal", title="...", ...)
repository.list_related(account["id"], "signal")
database.dispose()
```

Account methods return a read-only mapping or a tuple of read-only mappings.
Related methods use these stable record-type keys:

- `opportunity`
- `signal`
- `workload_hypothesis`
- `stakeholder`
- `discovery_record`
- `qualification_score`
- `risk`
- `next_action`
- `poc_plan`

Signals and discovery records accept `source`, `source_date`, `evidence_type`,
`confidence`, and `notes`. Evidence type is one of `verified_fact`,
`user_provided`, `hypothesis`, or `generated_suggestion`; confidence is from
0.0 through 1.0. JSON values in returned score and PoC snapshots are frozen
recursively.

`RecordNotFoundError` reports missing accounts and opportunities.
`RepositoryValidationError` reports blank required fields, unknown record types
or fields, invalid provenance, and cross-account opportunity references.

## RED checkpoints

Initial account contract:

```text
$ python -m pytest tests/test_repository.py -q
ModuleNotFoundError: No module named 'app.database'; 'app' is not a package
```

Related-record tracer:

```text
$ python -m pytest tests/test_repository.py::test_opportunity_can_be_added_to_an_account -q
AttributeError: 'OpportunityRepository' object has no attribute 'add_related'
```

Provenance validation was also observed failing with raw SQLAlchemy
`StatementError`/`IntegrityError` before repository-level validation was added.

## GREEN verification

Run the isolated temporary-SQLite suite and owned-module coverage:

```bash
python -m pytest tests/test_repository.py -q
```

The project test configuration enforces at least 80% coverage. Tests create a
new file-backed SQLite database under pytest's `tmp_path` for every case and
dispose the engine after each case.

## Integration notes

- Add `SQLAlchemy>=2.0,<3.0` to the project's runtime dependencies.
- Construct one process-level `Database`, call `create_schema()` during startup,
  inject an `OpportunityRepository` into routes, and call `dispose()` on
  shutdown.
- Convert `RecordNotFoundError` to HTTP 404 and
  `RepositoryValidationError` to HTTP 422 at the FastAPI edge.
- Repository snapshots contain `date` and `datetime` values; FastAPI/Pydantic
  can serialize them directly.
