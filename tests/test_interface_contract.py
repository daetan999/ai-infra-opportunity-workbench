from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / "index.html"
STYLES = ROOT / "static" / "styles.css"
SCRIPT = ROOT / "static" / "app.js"


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


def test_interface_is_local_accessible_and_progressively_enhanced():
    markup = TEMPLATE.read_text(encoding="utf-8")
    styles = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (STYLES, ROOT / "static" / "workspace.css", ROOT / "static" / "responsive.css")
    )
    script = SCRIPT.read_text(encoding="utf-8")

    assert "https://" not in markup
    assert "http://" not in markup
    assert 'class="skip-link"' in markup
    assert ":focus-visible" in styles
    assert "prefers-reduced-motion" in styles
    assert "data-account-search" in script
    assert "data-sidebar-toggle" in script
    assert "data-print" in script
    assert "analysis-form" not in markup
