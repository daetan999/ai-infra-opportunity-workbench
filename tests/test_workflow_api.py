from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client(tmp_path) -> TestClient:
    database_url = f"sqlite:///{tmp_path / 'opportunities.db'}"
    return TestClient(create_app(database_url=database_url, seed_demo=False))


def create_account(client: TestClient) -> int:
    response = client.post(
        "/api/accounts",
        json={
            "name": "Northstar Research Systems",
            "industry": "Life sciences",
            "geography": "Singapore",
            "segment": "Enterprise",
            "fictional": True,
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_complete_workflow_produces_explainable_score_and_handoff(client: TestClient) -> None:
    account_id = create_account(client)
    today = date.today().isoformat()

    signal = client.post(
        f"/api/accounts/{account_id}/signals",
        json={
            "summary": "Platform team supplied an inference latency baseline.",
            "source": "User-provided discovery note",
            "source_url": "https://example.com/fictional-signal",
            "source_date": today,
            "evidence_type": "user_provided",
            "confidence": 0.9,
            "notes": "Fictional portfolio scenario.",
        },
    )
    assert signal.status_code == 201

    workload = client.put(
        f"/api/accounts/{account_id}/workload",
        json={
            "name": "Private RAG inference",
            "workload_type": "rag_inference",
            "description": "Governed assistant over synthetic research records.",
            "business_metric": "Cost per grounded response",
            "success_metrics": "p95 latency and grounded-answer rate",
            "technical_requirements": "Data residency and auditable retrieval",
            "confidence": 0.85,
        },
    )
    assert workload.status_code == 200

    for stakeholder in (
        {
            "name": "Avery Chen",
            "title": "VP, Platform",
            "role": "technical_buyer",
            "engagement_status": "engaged",
            "confidence": 0.9,
        },
        {
            "name": "Morgan Ellis",
            "title": "Chief Operating Officer",
            "role": "economic_buyer",
            "engagement_status": "identified",
            "confidence": 0.75,
        },
        {
            "name": "Jordan Reyes",
            "title": "AI Platform Lead",
            "role": "champion",
            "engagement_status": "engaged",
            "confidence": 0.9,
        },
    ):
        response = client.post(f"/api/accounts/{account_id}/stakeholders", json=stakeholder)
        assert response.status_code == 201

    discovery_records = (
        ("measurable_pain", "Current p95 latency misses the target during peak demand."),
        ("business_impact", "Slow responses delay analyst review and increase serving cost."),
        ("urgency", "A controlled evaluation is required this quarter."),
        ("buying_process", "Technical validation precedes security and procurement review."),
        ("competitive_position", "The team will compare two deployment patterns."),
        ("poc_success", "Measure p95 latency, groundedness, and cost per response."),
        ("poc_timeline", "Decision review is scheduled after a three-week evaluation."),
    )
    for category, answer in discovery_records:
        response = client.post(
            f"/api/accounts/{account_id}/discovery",
            json={
                "category": category,
                "question": f"What evidence supports {category.replace('_', ' ')}?",
                "answer": answer,
                "source": "User-provided discovery note",
                "source_date": today,
                "evidence_type": "user_provided",
                "confidence": 0.85,
                "notes": "Synthetic demonstration record.",
            },
        )
        assert response.status_code == 201

    score_response = client.get(f"/api/accounts/{account_id}/qualification")
    assert score_response.status_code == 200
    score = score_response.json()
    assert 0 <= score["total"] <= 100
    assert len(score["components"]) == 10
    assert score["recommendation"] in {"Advance", "Reshape", "Nurture", "Disqualify"}
    assert "missing_evidence" in score
    assert "single_threading_risk" in score
    assert all(component["reason"] for component in score["components"].values())

    handoff_response = client.get(f"/api/accounts/{account_id}/handoff")
    assert handoff_response.status_code == 200
    handoff = handoff_response.json()
    assert handoff["account"]["name"] == "Northstar Research Systems"
    assert handoff["workload"]["workload_type"] == "rag_inference"
    assert handoff["qualification"]["total"] == score["total"]
    assert handoff["poc_readiness"]["score"] >= 0
    assert handoff["recommended_next_action"]

    export_response = client.get(f"/api/accounts/{account_id}/export?format=markdown")
    assert export_response.status_code == 200
    assert export_response.headers["content-type"].startswith("text/markdown")
    assert "BDR-to-AE Handoff" in export_response.text
    assert "Northstar Research Systems" in export_response.text


def test_demo_seed_contains_three_clearly_fictional_accounts(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'demo.db'}"
    with TestClient(create_app(database_url=database_url, seed_demo=True)) as demo_client:
        response = demo_client.get("/api/accounts")
        accounts = response.json()
        northstar = next(account for account in accounts if "Northstar" in account["name"])
        handoff_response = demo_client.get(f"/api/accounts/{northstar['id']}/handoff")

    assert response.status_code == 200
    assert handoff_response.status_code == 200
    assert len(accounts) >= 3
    assert all(account["fictional"] is True for account in accounts)
    handoff = handoff_response.json()
    assert handoff["workload"]["success_metrics"] == (
        "45 peak RPS at or below the 900 ms latency target, with grounded-answer quality "
        "measured against an approved baseline."
    )
    assert handoff["workload"]["technical_requirements"] == (
        "70B model class; 18 TB governed data; 35% annual growth; private or hybrid "
        "deployment posture."
    )
    assert handoff["workload"]["notes"] == (
        "Fictional case northstar-private-rag-v1; all requirements remain hypotheses until "
        "benchmark validation."
    )


def test_rendered_interface_and_error_states(client: TestClient) -> None:
    account_id = create_account(client)

    dashboard = client.get("/")
    assert dashboard.status_code == 200
    assert "AI Infrastructure Opportunity &amp; Discovery Workbench" in dashboard.text

    workspace = client.get(f"/accounts/{account_id}")
    assert workspace.status_code == 200
    assert "Northstar Research Systems" in workspace.text
    assert "Qualification scorecard" in workspace.text

    missing = client.get("/api/accounts/999999")
    assert missing.status_code == 404

    invalid_signal = client.post(
        f"/api/accounts/{account_id}/signals",
        json={
            "summary": "Invalid evidence type must be rejected.",
            "source": "Test",
            "source_date": date.today().isoformat(),
            "evidence_type": "confirmed_intent",
            "confidence": 0.7,
            "notes": "",
        },
    )
    assert invalid_signal.status_code == 422


def test_health_uses_final_product_identity(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "ai-infra-opportunity-workbench",
    }


def test_api_rejects_whitespace_only_business_evidence(client: TestClient) -> None:
    invalid_account = client.post(
        "/api/accounts",
        json={
            "name": "Whitespace Validation Account",
            "industry": "   ",
            "geography": "Singapore",
            "segment": "Enterprise",
            "fictional": True,
        },
    )
    assert invalid_account.status_code == 422

    account_id = create_account(client)
    invalid_signal = client.post(
        f"/api/accounts/{account_id}/signals",
        json={
            "summary": "A syntactically valid signal with an invalid source.",
            "source": "   ",
            "source_date": date.today().isoformat(),
            "evidence_type": "hypothesis",
            "confidence": 0.4,
            "notes": "",
        },
    )
    assert invalid_signal.status_code == 422

    invalid_discovery = client.post(
        f"/api/accounts/{account_id}/discovery",
        json={
            "category": "measurable_pain",
            "question": "What is the measurable constraint?",
            "answer": "   ",
            "source": "Synthetic discovery note",
            "source_date": date.today().isoformat(),
            "evidence_type": "user_provided",
            "confidence": 0.5,
            "notes": "",
        },
    )
    assert invalid_discovery.status_code == 422
