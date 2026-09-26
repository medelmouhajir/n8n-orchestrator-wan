# n8n-orchestrator-wan

A standalone Dockerized HTTP microservice skill designed for the **ISLI v2.0 Universal Skill Runtime**. This skill transforms an ISLI AI agent into a meta-orchestrator capable of programmatically designing, deploying, activating, and monitoring n8n automations on a client's behalf.

## Key Features

- **Workflow Validation**: Prevents the community-reported "empty nodes" issue when creating workflows via the API by strictly validating the workflow JSON schema (nodes, connections, settings) before sending it to n8n.
- **ISLI Core RPC Contract**: Conforms to ISLI Core proxy dispatching by implementing flat top-level `POST` endpoints with request body parameter binding.
- **Workflow Management**: Create, read, update, activate, and deactivate workflows.
- **Execution Monitoring**: Trigger executions and fetch status or detailed execution logs.
- **Containerized Auth**: Seamless credential ingestion via container environment variables and internal JWT token verification (`X-Internal-Auth`).

---

## Repository Structure

```text
n8n-orchestrator-wan/
├── app/
│   ├── __init__.py
│   ├── main.py        # FastAPI server RPC endpoints & proxies
│   └── schemas.py     # Pydantic schemas validating n8n workflows
├── tests/
│   └── test_main.py   # Comprehensive automated test suite
├── Dockerfile         # Docker recipe for the skill microservice
├── docker-compose.yml # Test environment with local n8n setup
├── isli-skill.yaml    # ISLI v2.0 Skill Manifest
├── requirements.txt   # Python dependencies
└── README.md          # This file
```

---

## Configuration & Environment Variables

Credentials and configuration are injected into the skill container via environment variables:

| Variable | Required | Default | Description |
|---|---|---|---|
| `N8N_API_KEY` | Yes | `""` | Personal API Key for the target n8n instance |
| `N8N_HOST` | No | `http://host.docker.internal:5678` | Base URL of the target n8n instance |
| `JWT_SECRET` | Optional | `None` | Shared secret to verify incoming `X-Internal-Auth` JWT tokens |

---

## Local Development & Setup

### 1. Run the n8n Test Environment
To spin up a local instance of n8n for development and testing:
```bash
docker compose up -d
```
This starts n8n at `http://127.0.0.1:5678`.
- Open the UI and complete the initial owner account setup.
- Go to **Settings > n8n API** and generate a new API key.

### 2. Install Dependencies & Run the Skill Proxy
Install Python dependencies (Python 3.10+ recommended) and run the FastAPI server:
```bash
pip install -r requirements.txt
export N8N_API_KEY="your-n8n-api-key"
export N8N_HOST="http://localhost:5678"
python -m uvicorn app.main:app --port 8000 --reload
```
The skill endpoint proxy will be available at `http://127.0.0.1:8000`.

### 3. Running Automated Tests
```bash
pytest tests -v
```

---

## RPC Actions & Tool Contract

All skill tools receive `POST` requests forwarded by ISLI Core:

### Workflows

#### Get All Workflows
- **Method**: `POST`
- **Path**: `/get_workflows`
- **Body**: `{}`

#### Create a Workflow
- **Method**: `POST`
- **Path**: `/create_workflow`
- **Body**: A validated n8n workflow payload (`name`, `nodes`, `connections`, `settings`).
  
*Note: The `active` status is stripped automatically during creation payload transfer since n8n treats it as a read-only property on workflow registration.*

#### Update a Workflow
- **Method**: `POST`
- **Path**: `/update_workflow`
- **Body**: `{ "workflow_id": "...", "name": "...", "nodes": [...], "connections": {...}, "settings": {...} }`
  
*Note: Implements a Smart Merge. Partial payloads are supported (e.g. name only or node list update). The skill fetches the current workflow state, merges changes, and guarantees `connections: {}` and `settings: {}` are provided to satisfy n8n's strict PUT schema.*

#### Activate Workflow
- **Method**: `POST`
- **Path**: `/activate_workflow`
- **Body**: `{ "workflow_id": "..." }`
  
*Note: In n8n 2.x, this calls `/publish` (with fallback to `/activate`). n8n requires workflows to have at least one trigger node (Schedule, Webhook, Polling) to activate; descriptive error messages from n8n are surfaced.*

#### Deactivate Workflow
- **Method**: `POST`
- **Path**: `/deactivate_workflow`
- **Body**: `{ "workflow_id": "..." }`
  
*Note: In n8n 2.x, this calls `/unpublish` (with fallback to `/deactivate`).*

### Executions

#### Trigger Execution
- **Method**: `POST`
- **Path**: `/trigger_execution`
- **Body**: `{ "workflow_id": "...", "payload": { ... } }`
  
*Note: In n8n's Public API, executions are triggered on-demand via Webhooks. The skill automatically inspects the target workflow for an active Webhook node, resolves its path, and triggers it via `/webhook/{path}` passing the optional JSON payload.*

#### Get Execution Details
- **Method**: `POST`
- **Path**: `/get_execution`
- **Body**: `{ "execution_id": "..." }`

---

## Schema Validation Rules
The Pydantic models in `app/schemas.py` enforce validation checks on:
1. **Nodes**: Each node must specify an `id`, `name`, `type`, `typeVersion`, `position` (X, Y canvas coordinates), and a `parameters` object (even if empty).
2. **Connections**: Connection references are strictly formatted (`node`, `type`, `index`).
