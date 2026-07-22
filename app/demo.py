from __future__ import annotations

from datetime import date

from app.repository import OpportunityRepository

_DEMO_DATE = date(2026, 7, 20)

_SCENARIOS = (
    {
        "name": "Northstar Mutual (Fictional)",
        "industry": "Insurance",
        "geography": "Singapore",
        "segment": "Enterprise",
        "workload": "Private enterprise RAG inference",
        "workload_type": "rag_inference",
        "signal": (
            "A synthetic platform team supplied a peak-latency baseline "
            "for a private assistant."
        ),
        "pain": "Peak response latency exceeds the fictional service target.",
        "impact": "Slow responses increase review time for the synthetic analyst workflow.",
        "metric": "Cost per grounded response",
        "success_metrics": (
            "45 peak RPS at or below the 900 ms latency target, with grounded-answer quality "
            "measured against an approved baseline."
        ),
        "technical_requirements": (
            "70B model class; 18 TB governed data; 35% annual growth; private or hybrid "
            "deployment posture."
        ),
        "workload_notes": (
            "Fictional case northstar-private-rag-v1; all requirements remain hypotheses "
            "until benchmark validation."
        ),
    },
    {
        "name": "Bluehaven Compute (Fictional)",
        "industry": "Specialized cloud services",
        "geography": "Australia",
        "segment": "Growth enterprise",
        "workload": "Specialized GPU cloud capacity expansion",
        "workload_type": "batch_ai",
        "signal": (
            "A fictional capacity review identified demand variability "
            "across accelerator pools."
        ),
        "pain": "Idle capacity and demand spikes complicate the synthetic expansion plan.",
        "impact": (
            "Utilization uncertainty weakens the fictional commercial case "
            "for added capacity."
        ),
        "metric": "Productive accelerator hours",
    },
    {
        "name": "Harborline Manufacturing (Fictional)",
        "industry": "Advanced manufacturing",
        "geography": "Germany",
        "segment": "Global enterprise",
        "workload": "AI networking and data-center modernization",
        "workload_type": "vision_inference",
        "signal": (
            "A fictional architecture workshop recorded east-west traffic "
            "and storage constraints."
        ),
        "pain": "The synthetic vision pipeline experiences data-movement bottlenecks.",
        "impact": "Inspection queues delay the fictional production-quality feedback loop.",
        "metric": "Time from image capture to inspection result",
    },
)


def seed_demo_data(repository: OpportunityRepository) -> None:
    """Seed three explicitly fictional, deterministic portfolio scenarios once."""
    if repository.list_accounts():
        return

    for index, scenario in enumerate(_SCENARIOS, start=1):
        account = repository.create_account(
            name=scenario["name"],
            industry=scenario["industry"],
            geography=scenario["geography"],
            segment=scenario["segment"],
            fictional=True,
        )
        account_id = int(account["id"])
        repository.add_related(
            account_id,
            "opportunity",
            name=f"{scenario['workload']} discovery",
            description="Clearly fictional demonstration opportunity.",
            stage="discovery",
        )
        repository.add_related(
            account_id,
            "signal",
            title=scenario["signal"],
            description=scenario["signal"],
            source="Synthetic demonstration fixture",
            source_url=f"https://example.com/fictional-opportunity-{index}",
            source_date=_DEMO_DATE,
            evidence_type="user_provided",
            confidence=0.8,
            notes="Fictional data; not a customer signal or buying-intent claim.",
        )
        repository.add_related(
            account_id,
            "workload_hypothesis",
            title=scenario["workload"],
            workload_type=scenario["workload_type"],
            description="Synthetic workload used to demonstrate qualification workflow behavior.",
            business_metric=scenario["metric"],
            success_metrics=scenario.get(
                "success_metrics",
                "Baseline throughput, latency, utilization, and outcome quality.",
            ),
            technical_requirements=scenario.get(
                "technical_requirements",
                "Representative data, bounded test window, and observable baseline.",
            ),
            confidence=0.75,
            status="hypothesis",
            notes=scenario.get("workload_notes", "Requires benchmark validation."),
        )
        for name, title, role, relationship_status in (
            ("Alex Morgan", "AI Platform Lead", "champion", "engaged"),
            ("Sam Rivera", "Infrastructure Director", "technical_buyer", "engaged"),
            ("Taylor Okafor", "Business Unit Executive", "economic_buyer", "identified"),
        ):
            repository.add_related(
                account_id,
                "stakeholder",
                name=name,
                title=title,
                role=role,
                relationship_status=relationship_status,
                is_champion=role == "champion",
                notes="Fictional stakeholder persona.",
            )
        for category, question, answer in (
            ("measurable_pain", "What is the current constraint?", scenario["pain"]),
            ("business_impact", "What business outcome is affected?", scenario["impact"]),
            (
                "urgency",
                "Why evaluate now?",
                "A fictional quarterly planning gate creates a dated review.",
            ),
            (
                "buying_process",
                "How will a decision be made?",
                "Technical evidence precedes a fictional security and commercial review.",
            ),
            (
                "competitive_position",
                "Which alternatives are being compared?",
                "The fictional team will compare two deployment patterns and no action.",
            ),
            (
                "poc_success",
                "What must a PoC prove?",
                f"Measure {scenario['metric'].lower()} against a documented baseline.",
            ),
        ):
            repository.add_related(
                account_id,
                "discovery_record",
                category=category,
                question=question,
                answer=answer,
                source="Synthetic discovery fixture",
                source_date=_DEMO_DATE,
                evidence_type="user_provided",
                confidence=0.8,
                notes="Fictional portfolio scenario.",
            )
        repository.add_related(
            account_id,
            "poc_plan",
            name=f"{scenario['workload']} validation",
            objective=(
                f"Test {scenario['metric'].lower()} using a representative synthetic workload."
            ),
            workload=scenario["workload"],
            scope="One bounded workload, baseline comparison, and decision review.",
            success_criteria=[scenario["metric"], "Documented technical baseline"],
            readiness_score=60,
            status="draft",
            notes="Illustrative plan; formal validation is still required.",
        )
