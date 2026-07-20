from __future__ import annotations

from datetime import date
from types import MappingProxyType

import pytest
from sqlalchemy.exc import IntegrityError

from app.database import Database
from app.models import Account, Signal
from app.repository import (
    OpportunityRepository,
    RecordNotFoundError,
    RepositoryValidationError,
)


@pytest.fixture
def database(tmp_path):
    database = Database(f"sqlite:///{tmp_path / 'opportunities.db'}")
    database.create_schema()
    try:
        yield database
    finally:
        database.dispose()


def test_account_can_be_created_and_loaded_as_an_immutable_snapshot(database):
    repository = OpportunityRepository(database)

    created = repository.create_account(
        name="Northstar Health (Fictional)",
        industry="Healthcare",
        geography="Singapore",
        segment="Enterprise",
    )
    loaded = OpportunityRepository(database).get_account(created["id"])

    assert isinstance(loaded, MappingProxyType)
    assert loaded == {
        "id": created["id"],
        "name": "Northstar Health (Fictional)",
        "industry": "Healthcare",
        "geography": "Singapore",
        "segment": "Enterprise",
        "created_at": created["created_at"],
    }
    with pytest.raises(TypeError):
        loaded["name"] = "Changed"


def test_blank_account_name_is_rejected(database):
    repository = OpportunityRepository(database)

    with pytest.raises(RepositoryValidationError, match="name"):
        repository.create_account(name="   ")


def test_accounts_are_listed_in_creation_order(database):
    repository = OpportunityRepository(database)
    repository.create_account(name="First Fictional Account")
    repository.create_account(name="Second Fictional Account")

    accounts = repository.list_accounts()

    assert isinstance(accounts, tuple)
    assert [account["name"] for account in accounts] == [
        "First Fictional Account",
        "Second Fictional Account",
    ]


def test_get_account_raises_explicit_not_found_error(database):
    repository = OpportunityRepository(database)

    with pytest.raises(RecordNotFoundError, match="Account 404"):
        repository.get_account(404)


def test_opportunity_can_be_added_to_an_account(database):
    repository = OpportunityRepository(database)
    account = repository.create_account(name="Northstar Health (Fictional)")

    created = repository.add_related(
        account["id"],
        "opportunity",
        name="Private AI inference deployment",
        stage="discovery",
        recommendation="reshape",
    )

    assert created["account_id"] == account["id"]
    assert created["name"] == "Private AI inference deployment"
    assert repository.list_related(account["id"], "opportunity") == (created,)


def test_signal_provenance_round_trips_through_read_only_snapshots(database):
    repository = OpportunityRepository(database)
    account = repository.create_account(name="Northstar Health (Fictional)")

    created = repository.add_related(
        account["id"],
        "signal",
        title="Public data-center expansion notice",
        description="A fictional public signal used for demonstration.",
        source="https://example.com/fictional-notice",
        source_date=date(2026, 7, 1),
        evidence_type="verified_fact",
        confidence=0.85,
        notes="Verify scope during discovery.",
    )

    assert created["source"] == "https://example.com/fictional-notice"
    assert created["source_date"] == date(2026, 7, 1)
    assert created["evidence_type"] == "verified_fact"
    assert created["confidence"] == pytest.approx(0.85)
    assert created["notes"] == "Verify scope during discovery."
    assert repository.list_related(account["id"], "signal") == (created,)
    with pytest.raises(TypeError):
        created["confidence"] = 1.0


@pytest.mark.parametrize(
    ("record_type", "values", "assertion"),
    [
        (
            "workload_hypothesis",
            {
                "title": "Private RAG inference",
                "workload_type": "rag_inference",
                "description": "Fictional discovery hypothesis.",
            },
            ("workload_type", "rag_inference"),
        ),
        (
            "stakeholder",
            {
                "name": "Fictional Infrastructure Director",
                "role": "technical_evaluator",
                "influence": "high",
            },
            ("role", "technical_evaluator"),
        ),
        (
            "discovery_record",
            {
                "question": "What latency target is required?",
                "answer": "Not yet confirmed",
                "evidence_type": "user_provided",
                "confidence": 0.6,
            },
            ("answer", "Not yet confirmed"),
        ),
        (
            "qualification_score",
            {
                "total_score": 62.0,
                "component_scores": {"technical_fit": 7.0},
                "missing_evidence": ["executive sponsor"],
                "recommendation": "reshape",
            },
            ("recommendation", "reshape"),
        ),
        (
            "risk",
            {
                "title": "Single-threaded technical relationship",
                "severity": "high",
                "mitigation": "Map an economic buyer.",
            },
            ("severity", "high"),
        ),
        (
            "next_action",
            {
                "title": "Validate peak concurrency",
                "owner": "Account executive",
                "status": "open",
            },
            ("status", "open"),
        ),
        (
            "poc_plan",
            {
                "name": "Private inference validation",
                "objective": "Measure latency under synthetic load.",
                "success_criteria": ["p95 latency measured", "cost range documented"],
                "status": "draft",
            },
            ("status", "draft"),
        ),
    ],
)
def test_each_workbench_record_type_can_be_added_and_listed(
    database, record_type, values, assertion
):
    repository = OpportunityRepository(database)
    account = repository.create_account(name="Northstar Health (Fictional)")

    created = repository.add_related(account["id"], record_type, **values)

    field, expected = assertion
    assert created[field] == expected
    assert repository.list_related(account["id"], record_type) == (created,)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("evidence_type", "assumed_fact"),
        ("confidence", -0.01),
        ("confidence", 1.01),
        ("source_date", "2026-07-01"),
    ],
)
def test_invalid_signal_provenance_is_rejected_explicitly(database, field, value):
    repository = OpportunityRepository(database)
    account = repository.create_account(name="Northstar Health (Fictional)")
    values = {
        "title": "Fictional signal",
        "evidence_type": "hypothesis",
        "confidence": 0.5,
        "source_date": date(2026, 7, 1),
        field: value,
    }

    with pytest.raises(RepositoryValidationError, match=field):
        repository.add_related(account["id"], "signal", **values)


def test_related_record_cannot_reference_another_accounts_opportunity(database):
    repository = OpportunityRepository(database)
    first_account = repository.create_account(name="First Fictional Account")
    second_account = repository.create_account(name="Second Fictional Account")
    opportunity = repository.add_related(
        first_account["id"], "opportunity", name="First opportunity"
    )

    with pytest.raises(RepositoryValidationError, match="does not belong"):
        repository.add_related(
            second_account["id"],
            "risk",
            opportunity_id=opportunity["id"],
            title="Invalid cross-account risk",
        )


def test_sqlite_foreign_keys_are_enabled_for_every_session(database):
    with pytest.raises(IntegrityError):
        with database.session() as session:
            session.add(Signal(account_id=999, title="Orphan signal"))


def test_database_session_rolls_back_and_closes_after_failure(database):
    with pytest.raises(RuntimeError, match="abort transaction"):
        with database.session() as session:
            session.add(Account(name="Rolled-back account"))
            raise RuntimeError("abort transaction")

    assert OpportunityRepository(database).list_accounts() == ()


def test_missing_account_errors_are_explicit_for_related_operations(database):
    repository = OpportunityRepository(database)

    with pytest.raises(RecordNotFoundError, match="Account 404"):
        repository.add_related(404, "risk", title="Unreachable")
    with pytest.raises(RecordNotFoundError, match="Account 404"):
        repository.list_related(404, "risk")


def test_unknown_record_types_and_fields_are_explicit_validation_errors(database):
    repository = OpportunityRepository(database)
    account = repository.create_account(name="Northstar Health (Fictional)")

    with pytest.raises(RepositoryValidationError, match="Unknown related record"):
        repository.add_related(account["id"], "memo", title="Unsupported")
    with pytest.raises(RepositoryValidationError, match="unexpected keyword"):
        repository.add_related(
            account["id"], "risk", title="Known field", confidential_value="no"
        )


def test_json_values_are_deeply_immutable_snapshots(database):
    repository = OpportunityRepository(database)
    account = repository.create_account(name="Northstar Health (Fictional)")

    score = repository.add_related(
        account["id"],
        "qualification_score",
        total_score=62.0,
        component_scores={"technical_fit": 7.0},
        missing_evidence=["executive sponsor"],
    )

    assert isinstance(score["component_scores"], MappingProxyType)
    assert score["missing_evidence"] == ("executive sponsor",)
    with pytest.raises(TypeError):
        score["component_scores"]["technical_fit"] = 10.0


def test_discovery_records_preserve_the_full_evidence_contract(database):
    repository = OpportunityRepository(database)
    account = repository.create_account(name="Northstar Health (Fictional)")

    record = repository.add_related(
        account["id"],
        "discovery_record",
        question="Who owns the latency target?",
        answer="The fictional platform team",
        source="User discovery call",
        source_date=date(2026, 7, 2),
        evidence_type="user_provided",
        confidence=0.7,
        notes="Synthetic demonstration record.",
    )

    assert {
        key: record[key]
        for key in ("source", "source_date", "evidence_type", "confidence", "notes")
    } == {
        "source": "User discovery call",
        "source_date": date(2026, 7, 2),
        "evidence_type": "user_provided",
        "confidence": 0.7,
        "notes": "Synthetic demonstration record.",
    }
