from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from data.account_intelligence import (
    AccountIntelligenceError,
    AnalysisRequest,
    generate_account_brief,
)
from data.catalog import SOLUTION_MOTIONS, list_companies

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(
    title="AI Infrastructure Account Intelligence",
    version="1.0.0",
    description="Sanitized account-planning application for AI-infrastructure solution selling.",
)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


class AnalysisPayload(BaseModel):
    ticker: str = Field(min_length=1, max_length=12)
    solution_motion: str = Field(min_length=1, max_length=40)
    customer_segment: str = Field(default="Enterprise", max_length=80)
    region: str = Field(default="Global", max_length=80)
    context: str = Field(default="", max_length=2000)
    use_ai: bool = True


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "companies": list_companies(),
            "solution_motions": [
                {"key": key, "label": value["label"]}
                for key, value in SOLUTION_MOTIONS.items()
            ],
        },
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "ai-infra-account-intelligence"}


@app.get("/api/companies")
def companies() -> list[dict]:
    return list_companies()


@app.post("/api/analyze")
def analyze(payload: AnalysisPayload) -> dict:
    try:
        return generate_account_brief(
            AnalysisRequest(
                ticker=payload.ticker,
                solution_motion=payload.solution_motion,
                customer_segment=payload.customer_segment,
                region=payload.region,
                context=payload.context,
                use_ai=payload.use_ai,
            )
        )
    except AccountIntelligenceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
