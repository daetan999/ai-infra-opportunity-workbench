# Architecture and Controls

## Request Flow

1. The browser submits a company, solution motion, customer segment, region, and optional account context.
2. FastAPI validates the payload with Pydantic.
3. The deterministic engine loads a sanitized company record and solution-motion framework.
4. The engine creates opportunity hypotheses, stakeholder mapping, discovery questions, objections, and PoC acceptance criteria.
5. Gemini enrichment is attempted only when an API key is configured. Failure degrades to deterministic output rather than failing the request.
6. The UI renders structured sections and displays provenance and limitations.

## Reliability Controls

- No network dependency is required for the core workflow.
- Unsupported company and solution identifiers return HTTP 422 responses.
- Optional AI enrichment is isolated behind exception handling.
- Tests remove the Gemini key and validate the complete API path offline.
- User context is bounded by request validation.

## AI Guardrail

The model receives the already-generated deterministic brief. The prompt prohibits adding external facts, current events, customer deployments, contracts, and financial outcomes. This limits enrichment to prioritization and wording rather than factual invention.

## Extension Path

A production version could replace the static catalog with approved public-source ingestion, CRM account data, product telemetry, and an enterprise semantic layer. Those integrations are intentionally excluded from the public repository.
