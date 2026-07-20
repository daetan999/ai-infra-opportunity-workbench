from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from enum import Enum
from types import MappingProxyType

from sqlalchemy import select
from sqlalchemy.inspection import inspect

from .database import Database
from .models import Account, Base, EvidenceType, Opportunity, Signal
from .models import (
    DiscoveryRecord,
    NextAction,
    PoCPlan,
    QualificationScore,
    Risk,
    Stakeholder,
    WorkloadHypothesis,
)


class RecordNotFoundError(LookupError):
    """Raised when a requested persistent record does not exist."""


class RepositoryValidationError(ValueError):
    """Raised when caller-supplied record data violates the repository contract."""


Snapshot = Mapping[str, object]


def _freeze(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def _snapshot(record: Base) -> Snapshot:
    column_names = inspect(type(record)).columns.keys()
    values = {name: _freeze(getattr(record, name)) for name in column_names}
    return MappingProxyType(values)


_RELATED_MODELS: dict[str, type[Base]] = {
    "opportunity": Opportunity,
    "signal": Signal,
    "workload_hypothesis": WorkloadHypothesis,
    "stakeholder": Stakeholder,
    "discovery_record": DiscoveryRecord,
    "qualification_score": QualificationScore,
    "risk": Risk,
    "next_action": NextAction,
    "poc_plan": PoCPlan,
}

_REQUIRED_TEXT_FIELDS: dict[type[Base], tuple[str, ...]] = {
    Opportunity: ("name",),
    Signal: ("title",),
    WorkloadHypothesis: ("title",),
    Stakeholder: ("name",),
    DiscoveryRecord: ("question",),
    Risk: ("title",),
    NextAction: ("title",),
    PoCPlan: ("name",),
}


def _related_model(record_type: str) -> type[Base]:
    try:
        return _RELATED_MODELS[record_type]
    except (KeyError, TypeError) as exc:
        supported = ", ".join(sorted(_RELATED_MODELS))
        raise RepositoryValidationError(
            f"Unknown related record type {record_type!r}; expected one of: {supported}"
        ) from exc


def _validate_provenance(values: dict[str, object]) -> dict[str, object]:
    normalized = dict(values)
    if "evidence_type" in normalized:
        try:
            normalized["evidence_type"] = EvidenceType(normalized["evidence_type"])
        except (TypeError, ValueError) as exc:
            allowed = ", ".join(item.value for item in EvidenceType)
            raise RepositoryValidationError(
                f"evidence_type must be one of: {allowed}"
            ) from exc
    if "confidence" in normalized:
        confidence = normalized["confidence"]
        if (
            isinstance(confidence, bool)
            or not isinstance(confidence, (int, float))
            or not 0.0 <= confidence <= 1.0
        ):
            raise RepositoryValidationError("confidence must be between 0.0 and 1.0")
        normalized["confidence"] = float(confidence)
    if "source_date" in normalized:
        source_date = normalized["source_date"]
        if source_date is not None and not isinstance(source_date, date):
            raise RepositoryValidationError("source_date must be a date or None")
    return normalized


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
        if not isinstance(name, str) or not name.strip():
            raise RepositoryValidationError("Account name must not be blank")
        account = Account(
            name=name.strip(),
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

    def add_related(
        self,
        account_id: int,
        record_type: str,
        **values: object,
    ) -> Snapshot:
        model = _related_model(record_type)
        normalized_values = dict(values)
        writable_fields = set(inspect(model).columns.keys()) - {
            "id",
            "account_id",
            "created_at",
        }
        unexpected_fields = set(normalized_values) - writable_fields
        if unexpected_fields:
            fields = ", ".join(sorted(unexpected_fields))
            raise RepositoryValidationError(
                f"unexpected keyword argument(s) for {record_type}: {fields}"
            )
        for field in _REQUIRED_TEXT_FIELDS.get(model, ()):
            value = normalized_values.get(field)
            if not isinstance(value, str) or not value.strip():
                label = model.__name__.replace("Record", " record")
                raise RepositoryValidationError(f"{label} {field} must not be blank")
            normalized_values[field] = value.strip()
        if model in (Signal, DiscoveryRecord):
            normalized_values = _validate_provenance(normalized_values)
        with self._database.session() as session:
            if session.get(Account, account_id) is None:
                raise RecordNotFoundError(f"Account {account_id} was not found")
            opportunity_id = normalized_values.get("opportunity_id")
            if opportunity_id is not None:
                opportunity = session.get(Opportunity, opportunity_id)
                if opportunity is None:
                    raise RecordNotFoundError(
                        f"Opportunity {opportunity_id} was not found"
                    )
                if opportunity.account_id != account_id:
                    raise RepositoryValidationError(
                        f"Opportunity {opportunity_id} does not belong to account {account_id}"
                    )
            try:
                record = model(account_id=account_id, **normalized_values)
            except TypeError as exc:
                raise RepositoryValidationError(str(exc)) from exc
            session.add(record)
            session.flush()
            return _snapshot(record)

    def list_related(
        self,
        account_id: int,
        record_type: str,
    ) -> tuple[Snapshot, ...]:
        model = _related_model(record_type)
        with self._database.session() as session:
            if session.get(Account, account_id) is None:
                raise RecordNotFoundError(f"Account {account_id} was not found")
            account_id_column = getattr(model, "account_id")
            records = session.scalars(
                select(model).where(account_id_column == account_id).order_by(model.id)
            ).all()
            return tuple(_snapshot(record) for record in records)
