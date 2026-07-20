from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from contextlib import asynccontextmanager
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Query, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.database import Database
from app.demo import seed_demo_data
from app.presentation import (
    poc_payload,
    recommended_next_action,
    score_account,
    score_payload,
)
from app.repository import (
    OpportunityRepository,
    RecordNotFoundError,
    RepositoryValidationError,
)
from app.schemas import (
    AccountCreate,
    DiscoveryCreate,
    SignalCreate,
    StakeholderCreate,
    WorkloadCreate,
)

BASE_DIR = Path(__file__).resolve().parents[1]
templates = Jinja2Templates(directory=BASE_DIR / "templates")


def _serialize(value: object) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _serialize(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_serialize(item) for item in value]
    return value


def _repository(request: Request) -> OpportunityRepository:
    return request.app.state.repository


def _latest(records: Sequence[Mapping[str, object]]) -> Mapping[str, object] | None:
    return records[-1] if records else None


def _score_and_store(
    repository: OpportunityRepository, account_id: int
) -> tuple[dict[str, object], dict[str, object], str]:
    result = score_account(repository, account_id)
    score = score_payload(result)
    poc = poc_payload(result)
    next_action = recommended_next_action(result)
    component_scores = {
        name: float(component["score"])
        for name, component in score["components"].items()
    }
    previous_scores = repository.list_related(account_id, "qualification_score")
    last_components = previous_scores[-1].get("component_scores") if previous_scores else None
    if last_components != component_scores:
        repository.add_related(
            account_id,
            "qualification_score",
            total_score=float(score["total"]),
            component_scores=component_scores,
            missing_evidence=list(score["missing_evidence"]),
            rationale="Deterministic evidence-based score; activity volume is excluded.",
            recommendation=str(score["recommendation"]),
        )
    actions = repository.list_related(account_id, "next_action")
    if not actions or actions[-1].get("title") != next_action:
        repository.add_related(
            account_id,
            "next_action",
            title=next_action,
            status="open",
            rationale=f"Derived from recommendation: {score['recommendation']}.",
        )
    return score, poc, next_action


def _account_card(
    repository: OpportunityRepository, account: Mapping[str, object]
) -> dict[str, object]:
    account_id = int(account["id"])
    result = score_account(repository, account_id)
    signals = repository.list_related(account_id, "signal")
    latest_signal = _latest(signals)
    return {
        **_serialize(account),
        "stage": result.recommendation.value,
        "score": result.total,
        "score_label": result.recommendation.value,
        "latest_signal": latest_signal.get("title") if latest_signal else "No signal recorded",
        "signal_date": _serialize(latest_signal.get("source_date")) if latest_signal else "—",
        "next_action": recommended_next_action(result),
    }


def _workspace_context(
    repository: OpportunityRepository, account_id: int
) -> dict[str, object]:
    account = repository.get_account(account_id)
    signals = repository.list_related(account_id, "signal")
    workloads = repository.list_related(account_id, "workload_hypothesis")
    stakeholders = repository.list_related(account_id, "stakeholder")
    discoveries = repository.list_related(account_id, "discovery_record")
    score, poc, next_action = _score_and_store(repository, account_id)
    workload = _latest(workloads)
    account_view = {
        **_serialize(account),
        "region": account.get("geography"),
        "stage": score["recommendation"],
        "hypothesis_status": (
            workload.get("status", "Needs validation") if workload else "Needs validation"
        ),
        "workload_hypothesis": workload.get("description") if workload else None,
        "workload": workload.get("title") if workload else None,
        "constraint": workload.get("technical_requirements") if workload else None,
        "business_impact": workload.get("business_metric") if workload else None,
        "success_metric": workload.get("success_metrics") if workload else None,
        "next_action": next_action,
        "next_action_owner": "Account team",
        "next_action_due": "Agree during the next customer interaction",
        "next_action_evidence": "Dated, attributable evidence that changes a score component",
    }
    signal_view = [
        {
            **_serialize(signal),
            "summary": signal.get("description"),
            "detail": signal.get("description"),
            "date": _serialize(signal.get("source_date")),
            "date_iso": _serialize(signal.get("source_date")),
            "type": str(signal.get("evidence_type") or "hypothesis").replace("_", " ").title(),
        }
        for signal in signals
    ]
    stakeholder_view = [
        {
            **_serialize(stakeholder),
            "status": str(stakeholder.get("relationship_status") or "unknown").title(),
            "decision_role": str(stakeholder.get("role") or "unknown").replace("_", " ").title(),
            "priority": "Validate influence and decision criteria",
        }
        for stakeholder in stakeholders
    ]
    discovery_view = [
        {
            **_serialize(record),
            "label": str(record.get("category") or "finding").replace("_", " ").title(),
            "value": record.get("answer"),
            "status": str(record.get("evidence_type") or "hypothesis").replace("_", " ").title(),
        }
        for record in discoveries
    ]
    return {
        "account": account_view,
        "signals": signal_view,
        "stakeholders": stakeholder_view,
        "discoveries": discovery_view,
        "score": score,
        "poc": poc,
        "questions": score["questions"],
    }


def _handoff(repository: OpportunityRepository, account_id: int) -> dict[str, object]:
    account = repository.get_account(account_id)
    workload = _latest(repository.list_related(account_id, "workload_hypothesis"))
    score, poc, next_action = _score_and_store(repository, account_id)
    return {
        "account": _serialize(account),
        "workload": _serialize(workload) if workload else None,
        "signals": _serialize(repository.list_related(account_id, "signal")),
        "stakeholders": _serialize(repository.list_related(account_id, "stakeholder")),
        "discovery": _serialize(repository.list_related(account_id, "discovery_record")),
        "qualification": score,
        "poc_readiness": poc,
        "recommended_next_action": next_action,
        "guardrail": "Fictional and user-supplied evidence must be validated before customer use.",
    }


def _markdown_handoff(handoff: Mapping[str, object]) -> str:
    account = handoff["account"]
    qualification = handoff["qualification"]
    workload = handoff.get("workload") or {}
    missing = qualification.get("missing_evidence", [])
    return "\n".join(
        (
            "# BDR-to-AE Handoff",
            "",
            f"## {account['name']}",
            f"- Industry: {account.get('industry') or 'Not recorded'}",
            f"- Geography: {account.get('geography') or 'Not recorded'}",
            f"- Segment: {account.get('segment') or 'Not recorded'}",
            f"- Fictional demonstration: {'Yes' if account.get('fictional') else 'No'}",
            "",
            "## Workload hypothesis",
            f"- Workload: {workload.get('title') or 'Not established'}",
            f"- Type: {workload.get('workload_type') or 'Not established'}",
            f"- Success measures: {workload.get('success_metrics') or 'Not established'}",
            "",
            "## Qualification",
            f"- Score: {qualification['total']}/100",
            f"- Recommendation: {qualification['recommendation']}",
            f"- Single-threading risk: {qualification['single_threading_risk']}",
            f"- Missing evidence: {', '.join(missing) if missing else 'None recorded'}",
            "",
            "## Recommended next action",
            str(handoff["recommended_next_action"]),
            "",
            "> This report is a structured opportunity hypothesis, not verified customer intent.",
        )
    )


def create_app(
    *, database_url: str | None = None, seed_demo: bool | None = None
) -> FastAPI:
    resolved_url = database_url or os.getenv(
        "DATABASE_URL", "sqlite:///./data/opportunity_workbench.db"
    )
    if resolved_url.startswith("sqlite:///./"):
        (BASE_DIR / "data").mkdir(parents=True, exist_ok=True)
    database = Database(resolved_url)
    database.create_schema()
    repository = OpportunityRepository(database)
    should_seed = seed_demo
    if should_seed is None:
        should_seed = os.getenv("SEED_DEMO_DATA", "true").lower() in {"1", "true", "yes"}
    if should_seed:
        seed_demo_data(repository)

    @asynccontextmanager
    async def lifespan(_application: FastAPI):
        yield
        database.dispose()

    application = FastAPI(
        title="AI Infrastructure Opportunity & Discovery Workbench",
        version="2.0.0",
        description="Evidence-based opportunity qualification for enterprise AI infrastructure.",
        lifespan=lifespan,
    )
    application.state.repository = repository
    application.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

    @application.exception_handler(RecordNotFoundError)
    async def not_found_handler(_request: Request, exc: RecordNotFoundError):
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @application.exception_handler(RepositoryValidationError)
    async def validation_handler(_request: Request, exc: RepositoryValidationError):
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @application.get("/", response_class=HTMLResponse)
    def dashboard(request: Request, account: int | None = None):
        repo = _repository(request)
        accounts = repo.list_accounts()
        selected_id = account or (int(accounts[0]["id"]) if accounts else None)
        context: dict[str, object] = {
            "request": request,
            "accounts": [_account_card(repo, item) for item in accounts],
        }
        if selected_id is not None:
            context.update(_workspace_context(repo, selected_id))
        return templates.TemplateResponse(request=request, name="index.html", context=context)

    @application.get("/accounts/{account_id}", response_class=HTMLResponse)
    def account_workspace(request: Request, account_id: int):
        repo = _repository(request)
        context = {
            "request": request,
            "accounts": [_account_card(repo, item) for item in repo.list_accounts()],
            **_workspace_context(repo, account_id),
        }
        return templates.TemplateResponse(request=request, name="index.html", context=context)

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "ai-infra-opportunity-workbench"}

    @application.get("/api/accounts")
    def list_accounts(request: Request):
        return _serialize(_repository(request).list_accounts())

    @application.post("/api/accounts", status_code=status.HTTP_201_CREATED)
    def create_account(payload: AccountCreate, request: Request):
        return _serialize(_repository(request).create_account(**payload.model_dump()))

    @application.get("/api/accounts/{account_id}")
    def get_account(account_id: int, request: Request):
        return _serialize(_repository(request).get_account(account_id))

    @application.post(
        "/api/accounts/{account_id}/signals", status_code=status.HTTP_201_CREATED
    )
    def add_signal(account_id: int, payload: SignalCreate, request: Request):
        values = payload.model_dump()
        values["title"] = values.pop("summary")
        values["description"] = values["title"]
        return _serialize(_repository(request).add_related(account_id, "signal", **values))

    @application.put("/api/accounts/{account_id}/workload")
    def add_workload(account_id: int, payload: WorkloadCreate, request: Request):
        values = payload.model_dump()
        values["title"] = values.pop("name")
        return _serialize(
            _repository(request).add_related(account_id, "workload_hypothesis", **values)
        )

    @application.post(
        "/api/accounts/{account_id}/stakeholders", status_code=status.HTTP_201_CREATED
    )
    def add_stakeholder(account_id: int, payload: StakeholderCreate, request: Request):
        values = payload.model_dump()
        confidence = values.pop("confidence")
        values["relationship_status"] = values.pop("engagement_status")
        values["is_champion"] = values["role"] == "champion"
        values["notes"] = f"User confidence: {confidence:.0%}."
        return _serialize(
            _repository(request).add_related(account_id, "stakeholder", **values)
        )

    @application.post(
        "/api/accounts/{account_id}/discovery", status_code=status.HTTP_201_CREATED
    )
    def add_discovery(account_id: int, payload: DiscoveryCreate, request: Request):
        return _serialize(
            _repository(request).add_related(
                account_id, "discovery_record", **payload.model_dump()
            )
        )

    @application.get("/api/accounts/{account_id}/qualification")
    def qualification(account_id: int, request: Request):
        score, _poc, _action = _score_and_store(_repository(request), account_id)
        return jsonable_encoder(score)

    @application.get("/api/accounts/{account_id}/handoff")
    def handoff(account_id: int, request: Request):
        return jsonable_encoder(_handoff(_repository(request), account_id))

    @application.get("/api/accounts/{account_id}/export")
    def export_handoff(
        account_id: int,
        request: Request,
        format: str = Query(default="markdown", pattern="^(markdown|json)$"),
    ):
        payload = _handoff(_repository(request), account_id)
        if format == "json":
            return JSONResponse(content=jsonable_encoder(payload))
        return PlainTextResponse(
            _markdown_handoff(payload),
            media_type="text/markdown",
            headers={
                "Content-Disposition": f'attachment; filename="account-{account_id}-handoff.md"'
            },
        )

    return application


app = create_app()
