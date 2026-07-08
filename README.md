# n8n-orchestrator-wan

A standalone Dockerized HTTP microservice skill designed for the **ISLI v2.0 Universal Skill Runtime**. This skill transforms an ISLI AI agent into a meta-orchestrator capable of programmatically designing, deploying, activating, and monitoring n8n automations on a client's behalf.

## Key Features

- **Workflow Validation**: Prevents the community-reported "empty nodes" issue when creating workflows via the API by strictly validating the workflow JSON schema (nodes, connections, settings) before sending it to n8n.
- **Workflow Management**: Create, read, update, activate, and deactivate workflows.
- **Execution Monitoring**: Trigger executions and fetch status or detailed execution logs.

---

## Repository Structure

```text
n8n-orchestrator-wan/
├── app/
│   ├── __init__.py
│   ├── main.py        # FastAPI server endpoints & proxies
│   └── schemas.py     # Pydantic schemas validating n8n workflows
├── Dockerfile         # Docker recipe for the skill microservice
├── docker-compose.yml # Test environment with local n8n setup
├── isli-skill.yaml    # ISLI v2.0 Skill Manifest
├── requirements.txt   # Python dependencies
└── README.md          # This file
```

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
python -m uvicorn app.main:app --port 8000 --reload
```
The skill endpoint proxy will be available at `http://127.0.0.1:8000`.

---

## API Endpoints & Usage

All requests to the orchestrator require the following HTTP headers:
- `X-N8n-Api-Key`: Your n8n Personal API Key.
- `n8n-host` (Optional): The host URL of the target n8n instance (defaults to `http://localhost:5678`).

### Workflows

#### Get All Workflows
- **Method**: `GET`
- **Path**: `/workflows`

#### Create a Workflow
- **Method**: `POST`
- **Path**: `/workflows`
- **Body**: A validated n8n workflow payload.
  
*Note: The `active` status is stripped automatically during creation payload transfer since n8n treats it as a read-only property on workflow registration.*

#### Update a Workflow
- **Method**: `PUT`
- **Path**: `/workflows/{workflow_id}`
- **Body**: The updated workflow payload.

#### Activate Workflow
- **Method**: `POST`
- **Path**: `/workflows/{workflow_id}/activate`

#### Deactivate Workflow
- **Method**: `POST`
- **Path**: `/workflows/{workflow_id}/deactivate`

### Executions

#### Trigger Execution
- **Method**: `POST`
- **Path**: `/executions/{workflow_id}`

#### Get Execution Details
- **Method**: `GET`
- **Path**: `/executions/{execution_id}`

---

## Schema Validation Rules
The Pydantic models in `app/schemas.py` enforce validation checks on:
1. **Nodes**: Each node must specify an `id`, `name`, `type`, `typeVersion`, `position` (X, Y canvas coordinates), and a `parameters` object (even if empty).
2. **Connections**: Connection references are strictly formatted (`node`, `type`, `index`).
