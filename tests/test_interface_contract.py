from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / "index.html"


def test_workbench_exposes_the_operator_journey():
    """The server-rendered shell exposes every decision surface without JavaScript."""
    markup = TEMPLATE.read_text(encoding="utf-8")

    assert 'href="#portfolio"' in markup
    assert 'href="#workspace"' in markup
    assert 'href="#evidence"' in markup
    assert 'href="#decision"' in markup

    for surface in (
        "Account portfolio",
        "Signal timeline",
        "Workload hypothesis",
        "Buying group",
        "Qualification scorecard",
        "Risk register",
        "Next best action",
        "PoC readiness",
        "Export brief",
    ):
        assert surface in markup
