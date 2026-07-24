from pathlib import Path
from struct import unpack

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
        for path in (
            STYLES,
            ROOT / "static" / "workspace.css",
            ROOT / "static" / "forms.css",
            ROOT / "static" / "responsive.css",
        )
    )
    script = SCRIPT.read_text(encoding="utf-8")

    assert 'src="https://' not in markup
    assert 'href="https://' not in markup
    assert "url(https://" not in styles
    assert 'class="skip-link"' in markup
    assert ":focus-visible" in styles
    assert "prefers-reduced-motion" in styles
    assert "data-account-search" in script
    assert "data-sidebar-toggle" in script
    assert "data-print" in script
    assert "analysis-form" not in markup


def test_documentation_visuals_are_self_contained_and_readable():
    expected = {
        "opportunity-workflow.svg": "Evidence to decision",
        "qualification-model.svg": "Qualification model",
    }

    for filename, title in expected.items():
        svg = (ROOT / "docs" / "assets" / filename).read_text(encoding="utf-8")
        assert svg.startswith("<svg")
        assert title in svg
        assert 'role="img"' in svg
        assert "<title>" in svg
        assert "<desc>" in svg
        assert 'href="http://' not in svg
        assert 'href="https://' not in svg

    for filename in (
        "opportunity-dashboard.png",
        "opportunity-account-workspace.png",
    ):
        png = (ROOT / "docs" / "assets" / filename).read_bytes()
        assert png.startswith(b"\x89PNG\r\n\x1a\n")
        assert unpack(">II", png[16:24]) == (1440, 900)


def test_user_can_create_an_account_from_the_portfolio():
    markup = TEMPLATE.read_text(encoding="utf-8")
    script = SCRIPT.read_text(encoding="utf-8")

    assert 'data-open-workflow="account"' in markup
    assert 'id="account-form"' in markup
    for field in ("name", "industry", "geography", "segment", "fictional"):
        assert f'name="{field}"' in markup
    assert 'data-workflow-form="account"' in markup
    assert "'/api/accounts'" in script
    assert "window.location.assign(`/accounts/${result.id}`)" in script


def test_user_can_capture_a_dated_signal_with_provenance():
    markup = TEMPLATE.read_text(encoding="utf-8")
    script = SCRIPT.read_text(encoding="utf-8")

    assert 'data-open-workflow="signal"' in markup
    assert 'id="signal-form"' in markup
    for field in (
        "summary",
        "source",
        "source_url",
        "source_date",
        "evidence_type",
        "confidence",
        "notes",
    ):
        assert f'name="{field}"' in markup
    assert 'type="url"' in markup
    assert 'type="date"' in markup
    assert "`/api/accounts/${currentAccountId}/signals`" in script


def test_user_can_define_the_selected_accounts_workload():
    markup = TEMPLATE.read_text(encoding="utf-8")
    script = SCRIPT.read_text(encoding="utf-8")

    assert 'data-open-workflow="workload"' in markup
    assert 'id="workload-form"' in markup
    for field in (
        "name",
        "workload_type",
        "description",
        "business_metric",
        "success_metrics",
        "technical_requirements",
        "confidence",
        "deployment_pattern",
    ):
        assert f'name="{field}"' in markup
    assert "`/api/accounts/${currentAccountId}/workload`" in script
    assert "method: 'PUT'" in script


def test_user_can_map_stakeholders_from_the_browser():
    markup = TEMPLATE.read_text(encoding="utf-8")
    script = SCRIPT.read_text(encoding="utf-8")

    assert 'data-open-workflow="stakeholder"' in markup
    assert 'id="stakeholder-form"' in markup
    for field in ("name", "title", "role", "engagement_status", "confidence"):
        assert f'name="{field}"' in markup
    assert 'value="economic_buyer"' in markup
    assert 'value="technical_buyer"' in markup
    assert "`/api/accounts/${currentAccountId}/stakeholders`" in script


def test_user_can_record_discovery_evidence_from_the_browser():
    markup = TEMPLATE.read_text(encoding="utf-8")
    script = SCRIPT.read_text(encoding="utf-8")

    assert 'data-open-workflow="discovery"' in markup
    assert 'id="discovery-form"' in markup
    for field in (
        "category",
        "question",
        "answer",
        "source",
        "source_url",
        "source_date",
        "evidence_type",
        "confidence",
        "notes",
    ):
        assert f'name="{field}"' in markup
    assert 'value="poc_success"' in markup
    assert 'value="buying_process"' in markup
    assert "`/api/accounts/${currentAccountId}/discovery`" in script


def test_user_can_trigger_qualification_with_visible_request_states():
    markup = TEMPLATE.read_text(encoding="utf-8")
    script = SCRIPT.read_text(encoding="utf-8")

    assert "data-run-qualification" in markup
    assert "data-qualification-status" in markup
    assert "`/api/accounts/${currentAccountId}/qualification`" in script
    assert "Running evidence-based qualification…" in script
    assert "Qualification complete." in script
    assert "setActionStatus(qualificationStatus, 'error'" in script


def test_user_can_export_markdown_or_json_with_visible_request_states():
    markup = TEMPLATE.read_text(encoding="utf-8")
    script = SCRIPT.read_text(encoding="utf-8")

    assert 'data-export-format="markdown"' in markup
    assert 'data-export-format="json"' in markup
    assert "data-export-status" in markup
    assert "`/api/accounts/${currentAccountId}/export?format=${format}`" in script
    assert "URL.createObjectURL" in script
    assert "Preparing ${format.toUpperCase()} export…" in script
    assert "Export ready." in script
    assert "setActionStatus(exportStatus, 'error'" in script


def test_form_payload_is_captured_before_loading_disables_controls():
    script = SCRIPT.read_text(encoding="utf-8")
    submit_handler = script.split("form.addEventListener('submit'", maxsplit=1)[1]

    assert submit_handler.index("const payload = payloadFromForm(form)") < submit_handler.index(
        "setFormBusy(form, true)"
    )


def test_same_account_mutations_reload_the_server_rendered_workspace():
    script = SCRIPT.read_text(encoding="utf-8")

    assert "function refreshWorkspace(anchor)" in script
    assert "window.location.reload()" in script
    assert "complete: () => refreshWorkspace('#evidence')" in script
    assert "complete: () => refreshWorkspace('#workspace')" in script
    assert "refreshWorkspace('#decision')" in script
