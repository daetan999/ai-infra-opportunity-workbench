from fastapi.testclient import TestClient

from app import app
from data.account_intelligence import AnalysisRequest, build_deterministic_brief

client = TestClient(app)


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_deterministic_brief_has_sales_artifacts():
    brief = build_deterministic_brief(
        AnalysisRequest(
            ticker="NVDA",
            solution_motion="networking",
            customer_segment="Cloud service provider",
            region="North America",
            use_ai=False,
        )
    )
    assert brief["account"]["name"] == "NVIDIA"
    assert len(brief["opportunity_hypotheses"]) == 3
    assert len(brief["stakeholder_map"]) == 4
    assert len(brief["discovery_questions"]) >= 5
    assert "acceptance_criteria" in brief["poc_plan"]


def test_analyze_endpoint_rejects_unknown_company():
    response = client.post(
        "/api/analyze",
        json={
            "ticker": "UNKNOWN",
            "solution_motion": "gpu_compute",
            "customer_segment": "Enterprise",
            "region": "Global",
            "use_ai": False,
        },
    )
    assert response.status_code == 422


def test_analyze_endpoint_works_without_api_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    response = client.post(
        "/api/analyze",
        json={
            "ticker": "VRT",
            "solution_motion": "data_center",
            "customer_segment": "Enterprise",
            "region": "Asia Pacific",
            "context": "High-density rack deployment",
            "use_ai": True,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["provenance"]["mode"] == "deterministic"
    assert body["user_context"] == "High-density rack deployment"
