# Changelog

All notable changes to this project will be documented in this file.

## [1.3.1]
### Fixed
- **`trigger_execution` n8n 2.x Architecture & Auto-Activation**:
  - Inspected both `activeVersion.nodes` and canvas `nodes` to locate Webhook trigger nodes in n8n 2.x versioned workflows.
  - Automatically activated/published the workflow prior to dispatching if inactive, ensuring n8n registers the production webhook URL.
  - Standardized response format to `{"status": "triggered", "workflow_id": ..., "webhook_path": ..., "response": ...}`.
- **`update_workflow` Node Sanitization & Active Protection**:
  - Implemented `sanitize_nodes()` to alias hallucinated node types (e.g. `nodes.none`, `noop` -> `n8n-nodes-base.noOp`), inject UUIDs for missing node IDs, and guarantee valid default positions, `typeVersion`, and `parameters`.
  - Added active-state protection: if an active workflow is updated with a node list lacking a trigger, automatically unpublishes/deactivates the workflow before `PUT` so n8n does not reject the update.

## [1.3.0]
### Fixed
- **`activate_workflow` & `deactivate_workflow` (n8n 2.x Publishing)**:
  - Transitioned activation to `POST /api/v1/workflows/{id}/publish` (and deactivation to `POST /api/v1/workflows/{id}/unpublish`) with automatic fallback to `/activate` and `/deactivate` for n8n 1.x compatibility.
  - Implemented `parse_n8n_error` to unpack and surface n8n's descriptive error messages (such as `"Workflow cannot be activated because it has no trigger node..."`) rather than returning opaque error strings or nested JSON dumps.
- **`update_workflow` Smart Merge**:
  - Resolved strict PUT 400 rejection (`request/body/connections must be object` and `request/body must have required property 'settings'`) by fetching the existing workflow via `GET /api/v1/workflows/{id}` and merging fields.
  - Allowed partial updates (such as name-only or node changes) and guaranteed that `connections` and `settings` are always populated as JSON objects `{}`.
- **`trigger_execution` Webhook-Based On-Demand Trigger**:
  - Resolved 405/502 errors caused by invoking the non-existent `POST /api/v1/executions` public endpoint.
  - Dynamically inspects workflow nodes for a Webhook trigger node (`n8n-nodes-base.webhook`), extracts its path, and triggers the workflow directly via `POST /webhook/{path}`.
  - Added optional `payload` parameter to pass data to the webhook execution.

## [1.2.0]
### Fixed
- **ISLI Core Proxy RPC Protocol**: Converted all REST endpoints (`GET /workflows`, `PUT /workflows/{id}`, etc.) to flat top-level `POST` actions (`/get_workflows`, `/create_workflow`, `/update_workflow`, `/activate_workflow`, `/deactivate_workflow`, `/trigger_execution`, `/get_execution`) conforming to ISLI Core router specifications.
- **Path Templating Bug**: Resolved 404 router errors caused by template variables (`/workflows/{workflow_id}`) in `isli-skill.yaml` by accepting identifiers (`workflow_id`, `execution_id`) in request bodies.
- **`get_workflows` 422 Unprocessable Entity**: Prevented validation clashes where empty POST requests from ISLI SDK hit workflow creation schemas.
- **Configuration & Auth Defect**: Switched credential retrieval from incoming HTTP request headers to container environment variables (`N8N_HOST`, `N8N_API_KEY`).
- **Internal Security**: Added `X-Internal-Auth` JWT verification via `JWT_SECRET`.

### Changed
- Default `N8N_HOST` updated to `http://host.docker.internal:5678` with fallback to `http://localhost:5678`.
- Updated `requirements.txt` to include `pyjwt`.

## [1.1.1]
### Added
- Added `/health` endpoint for ISLI Universal Skill Runtime health probes.
- Skill updated to conform to the ISLI v2.0 Universal Skill Runtime (USR) requirements.
- Config section added to `isli-skill.yaml` to securely store n8n credentials.
- Tools explicitly defined in `isli-skill.yaml` with corresponding endpoints for workflow and execution management.
