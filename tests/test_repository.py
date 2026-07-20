from __future__ import annotations

from types import MappingProxyType

import pytest

from app.database import Database
from app.repository import OpportunityRepository


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
