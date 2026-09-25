# Changelog

All notable changes to this project will be documented in this file.

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
