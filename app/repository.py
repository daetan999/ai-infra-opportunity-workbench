from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from sqlalchemy import select

from .database import Database
from .models import Account


class RecordNotFoundError(LookupError):
    """Raised when a requested persistent record does not exist."""


class RepositoryValidationError(ValueError):
    """Raised when caller-supplied record data violates the repository contract."""


Snapshot = Mapping[str, object]


def _snapshot(record: Account) -> Snapshot:
    return MappingProxyType(
        {
            "id": record.id,
            "name": record.name,
            "industry": record.industry,
            "geography": record.geography,
            "segment": record.segment,
            "created_at": record.created_at,
        }
    )


class OpportunityRepository:
    """Persist workbench records without leaking live ORM objects to callers."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def create_account(
        self,
        *,
        name: str,
        industry: str | None = None,
        geography: str | None = None,
        segment: str | None = None,
    ) -> Snapshot:
        account = Account(
            name=name,
            industry=industry,
            geography=geography,
            segment=segment,
        )
        with self._database.session() as session:
            session.add(account)
            session.flush()
            result = _snapshot(account)
        return result

    def get_account(self, account_id: int) -> Snapshot:
        with self._database.session() as session:
            account = session.get(Account, account_id)
            if account is None:
                raise RecordNotFoundError(f"Account {account_id} was not found")
            return _snapshot(account)

    def list_accounts(self) -> tuple[Snapshot, ...]:
        with self._database.session() as session:
            accounts = session.scalars(select(Account).order_by(Account.id)).all()
            return tuple(_snapshot(account) for account in accounts)
