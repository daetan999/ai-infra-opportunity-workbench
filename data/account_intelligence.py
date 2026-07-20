from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from data.catalog import get_company, get_solution_motion


@dataclass(frozen=True)
class AnalysisRequest:
    ticker: str
    solution_motion: str
    customer_segment: str
    region: str
    context: str = ""
    use_ai: bool = True


class AccountIntelligenceError(ValueError):
    pass


def _metric_pairs(company: dict, motion: dict) -> list[dict[str, str]]:
    pressures = company["commercial_signals"]
    focus = motion["technical_focus"]
    metrics = motion["business_metrics"]
    return [
        {
            "business_pressure": pressures[index % len(pressures)],
            "technical_hypothesis": f"Improve {focus[index % len(focus)]} for {company['workloads'][index % len(company['workloads'])]} workloads.",
            "solution_angle": f"Position {motion['label']} around a measured baseline and a controlled production-like evaluation.",
            "success_metric": metrics[index % len(metrics)],
        }
        for index in range(3)
    ]


def _stakeholder_map(company: dict) -> list[dict[str, str]]:
    buyers = company["buyers"]
    roles = [
        ("Economic buyer", buyers[0], "Owns the business case, funding, and strategic priority."),
        ("Technical buyer", buyers[1 % len(buyers)], "Validates architecture, integration, security, and operating fit."),
        ("Champion", buyers[2 % len(buyers)], "Feels the workload pain and can mobilize a technical evaluation."),
        ("Commercial gate", buyers[-1], "Controls procurement, risk, contractual terms, or cost validation."),
    ]
    return [{"role": role, "persona": persona, "priority": priority} for role, persona, priority in roles]


def _discovery_questions(company: dict, motion: dict) -> list[str]:
    workload = company["workloads"][0]
    return [
        f"Which {workload} workloads are constrained today, and what evidence shows the constraint?",
        f"How are you measuring {motion['technical_focus'][0]} and {motion['business_metrics'][0]} today?",
        "What capacity, migration, or governance decision must be made in the next two quarters?",
        "Which team owns the technical baseline, and which executive owns the economic outcome?",
        f"Where has the current approach failed: {', '.join(company['constraints'][:3])}?",
        "What would have to be proven in a PoC for the project to move into production procurement?",
    ]


def _poc_plan(company: dict, motion: dict) -> dict[str, Any]:
    return {
        "objective": f"Validate the {motion['label']} value hypothesis on one representative {company['workloads'][0]} workload.",
        "baseline": [
            motion["technical_focus"][0],
            motion["technical_focus"][1],
            motion["business_metrics"][0],
        ],
        "acceptance_criteria": [
            f"Improvement in {motion['technical_focus'][0]} against the agreed baseline",
            f"No regression in {motion['technical_focus'][1]} or service reliability",
            f"Documented unit economics for {motion['business_metrics'][0]}",
            "Named production owner and agreed deployment decision date",
        ],
        "duration": "2–4 weeks",
        "evidence": ["benchmark report", "cost model", "architecture review", "production-readiness decision"],
    }


def build_deterministic_brief(request: AnalysisRequest) -> dict[str, Any]:
    company = get_company(request.ticker)
    motion = get_solution_motion(request.solution_motion)
    if company is None:
        raise AccountIntelligenceError("Unsupported company. Select a company from the catalog.")
    if motion is None:
        raise AccountIntelligenceError("Unsupported solution motion.")

    opportunities = _metric_pairs(company, motion)
    return {
        "account": {
            "ticker": request.ticker.upper(),
            "name": company["name"],
            "role": company["role"],
            "customer_segment": request.customer_segment,
            "region": request.region,
        },
        "solution_motion": motion["label"],
        "account_snapshot": {
            "offerings": company["offerings"],
            "priority_workloads": company["workloads"],
            "commercial_signals": company["commercial_signals"],
            "competitive_context": company["competitors"],
            "execution_constraints": company["constraints"],
        },
        "commercial_thesis": (
            f"{company['name']} operates in {company['role'].lower()}. The initial sales hypothesis is to connect "
            f"{motion['label'].lower()} to measurable workload economics and delivery constraints rather than lead with product features."
        ),
        "opportunity_hypotheses": opportunities,
        "stakeholder_map": _stakeholder_map(company),
        "discovery_questions": _discovery_questions(company, motion),
        "poc_plan": _poc_plan(company, motion),
        "objection_map": [
            {"objection": "The current platform is good enough.", "response": "Agree on a baseline first; only proceed if the proposed architecture produces a material, measurable improvement."},
            {"objection": "Migration risk outweighs the benefit.", "response": "Use one bounded workload, explicit rollback criteria, and an integration plan that preserves the current operating path."},
            {"objection": "The economics are unclear.", "response": f"Build the model from the customer's inputs around {motion['business_metrics'][0]} and capacity growth."},
        ],
        "next_actions": [
            "Validate the account hypothesis with a technical champion.",
            "Collect workload, utilization, cost, and service-level baselines.",
            "Map the economic buyer and procurement path before proposing a PoC.",
            "Convert the strongest hypothesis into one quantified value statement.",
        ],
        "user_context": request.context.strip(),
        "provenance": {
            "mode": "deterministic",
            "source": "sanitized public company catalog and reusable solution-selling framework",
            "limitations": "This is an account-planning aid, not a substitute for verified customer discovery or current company filings.",
        },
    }


def _extract_json(text: str) -> dict[str, Any] | None:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:].strip()
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        return None


def enrich_with_gemini(brief: dict[str, Any]) -> dict[str, Any]:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return brief

    try:
        from google import genai

        client = genai.Client(api_key=api_key)
        prompt = f"""
You are preparing an enterprise AI-infrastructure account plan.
Use only the structured facts below. Do not invent deployments, customers, contracts, financial results, or current events.
Return JSON with exactly these keys:
- executive_summary: string
- refined_opportunity_hypotheses: array of 3 objects with business_pressure, technical_hypothesis, solution_angle, success_metric
- priority_discovery_questions: array of 5 strings
- deal_risks: array of 4 strings
- recommended_first_meeting: array of 4 strings

FACTS:
{json.dumps(brief, ensure_ascii=False)}
""".strip()
        response = client.models.generate_content(
            model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
            contents=prompt,
            config={"response_mime_type": "application/json", "temperature": 0.2},
        )
        parsed = _extract_json(getattr(response, "text", "") or "")
        if not parsed:
            return brief

        merged = dict(brief)
        merged["ai_enrichment"] = parsed
        merged["provenance"] = {
            **brief["provenance"],
            "mode": "deterministic + optional Gemini enrichment",
            "model": os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
            "guardrail": "The model receives only the deterministic brief and is instructed not to add external facts.",
        }
        return merged
    except Exception as exc:
        fallback = dict(brief)
        fallback["provenance"] = {**brief["provenance"], "ai_status": f"Enrichment unavailable: {type(exc).__name__}"}
        return fallback


def generate_account_brief(request: AnalysisRequest) -> dict[str, Any]:
    brief = build_deterministic_brief(request)
    return enrich_with_gemini(brief) if request.use_ai else brief
