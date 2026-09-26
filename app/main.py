import os
import jwt
import httpx
import logging
from typing import Optional, Dict, Any, List
from fastapi import FastAPI, HTTPException, Request, Depends
from pydantic import BaseModel
from app.schemas import Workflow

logger = logging.getLogger("n8n-skill")
app = FastAPI(title="n8n Orchestrator WAN", version="1.3.0")

def get_n8n_host() -> str:
    return os.getenv("N8N_HOST", os.getenv("n8n-host", "http://host.docker.internal:5678")).rstrip("/")

def get_n8n_api_key() -> str:
    return os.getenv("N8N_API_KEY", os.getenv("X-N8n-Api-Key", ""))

def get_jwt_secret() -> Optional[str]:
    return os.getenv("JWT_SECRET")

async def verify_jwt(request: Request):
    jwt_secret = get_jwt_secret()
    if not jwt_secret:
        return
    auth_header = request.headers.get("X-Internal-Auth")
    if not auth_header:
        raise HTTPException(status_code=401, detail="Missing authorization header")
    try:
        return jwt.decode(auth_header, jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")

def get_n8n_headers():
    headers = {"Accept": "application/json"}
    api_key = get_n8n_api_key()
    if api_key:
        headers["X-N8n-Api-Key"] = api_key
    return headers

def parse_n8n_error(resp: httpx.Response) -> str:
    try:
        data = resp.json()
        if isinstance(data, dict):
            return data.get("message") or data.get("detail") or data.get("errorMessage") or resp.text
        return str(data)
    except Exception:
        return resp.text

@app.get("/health")
async def health_check():
    return {"status": "ok"}

class WorkflowIdRequest(BaseModel):
    workflow_id: str

class UpdateWorkflowRequest(BaseModel):
    workflow_id: str
    name: Optional[str] = None
    nodes: Optional[List[Dict[str, Any]]] = None
    connections: Optional[Dict[str, Any]] = None
    settings: Optional[Dict[str, Any]] = None

class TriggerExecutionRequest(BaseModel):
    workflow_id: str
    payload: Optional[Dict[str, Any]] = None

class ExecutionIdRequest(BaseModel):
    execution_id: str

@app.post("/get_workflows", dependencies=[Depends(verify_jwt)])
async def get_workflows():
    async with httpx.AsyncClient(timeout=20.0) as client:
        try:
            resp = await client.get(f"{get_n8n_host()}/api/v1/workflows", headers=get_n8n_headers())
            if resp.status_code >= 400:
                raise HTTPException(status_code=resp.status_code, detail=parse_n8n_error(resp))
            return resp.json()
        except httpx.RequestError as exc:
            raise HTTPException(status_code=502, detail=f"Failed to connect to n8n at {get_n8n_host()}: {exc}")

@app.post("/create_workflow", dependencies=[Depends(verify_jwt)])
async def create_workflow(workflow: Workflow):
    async with httpx.AsyncClient(timeout=20.0) as client:
        try:
            resp = await client.post(
                f"{get_n8n_host()}/api/v1/workflows",
                json=workflow.model_dump(exclude={"active"}, exclude_unset=True),
                headers=get_n8n_headers()
            )
            if resp.status_code >= 400:
                raise HTTPException(status_code=resp.status_code, detail=parse_n8n_error(resp))
            return resp.json()
        except httpx.RequestError as exc:
            raise HTTPException(status_code=502, detail=f"Failed to connect to n8n: {exc}")

@app.post("/update_workflow", dependencies=[Depends(verify_jwt)])
async def update_workflow(payload: UpdateWorkflowRequest):
    async with httpx.AsyncClient(timeout=20.0) as client:
        # Step 1: Fetch existing workflow to perform Smart Merge
        try:
            get_resp = await client.get(
                f"{get_n8n_host()}/api/v1/workflows/{payload.workflow_id}",
                headers=get_n8n_headers()
            )
            if get_resp.status_code >= 400:
                raise HTTPException(status_code=get_resp.status_code, detail=parse_n8n_error(get_resp))
            existing_wf = get_resp.json()
        except httpx.RequestError as exc:
            raise HTTPException(status_code=502, detail=f"Failed to connect to n8n: {exc}")

        # Step 2: Merge fields, ensuring nodes, connections, and settings are strictly valid objects/lists
        name = payload.name if payload.name is not None else existing_wf.get("name", "")
        nodes = payload.nodes if payload.nodes is not None else existing_wf.get("nodes", [])

        connections = payload.connections if payload.connections is not None else existing_wf.get("connections")
        if not isinstance(connections, dict):
            connections = {}

        settings = payload.settings if payload.settings is not None else existing_wf.get("settings")
        if not isinstance(settings, dict):
            settings = {}

        body: Dict[str, Any] = {
            "name": name,
            "nodes": nodes,
            "connections": connections,
            "settings": settings,
        }

        # Step 3: PUT merged workflow
        try:
            resp = await client.put(
                f"{get_n8n_host()}/api/v1/workflows/{payload.workflow_id}",
                json=body,
                headers=get_n8n_headers()
            )
            if resp.status_code >= 400:
                raise HTTPException(status_code=resp.status_code, detail=parse_n8n_error(resp))
            return resp.json()
        except httpx.RequestError as exc:
            raise HTTPException(status_code=502, detail=f"Failed to connect to n8n: {exc}")

@app.post("/activate_workflow", dependencies=[Depends(verify_jwt)])
async def activate_workflow(payload: WorkflowIdRequest):
    async with httpx.AsyncClient(timeout=20.0) as client:
        try:
            # In n8n 2.x, activation is done via /publish. Fallback to /activate for 1.x if needed.
            resp = await client.post(
                f"{get_n8n_host()}/api/v1/workflows/{payload.workflow_id}/publish",
                headers=get_n8n_headers()
            )
            if resp.status_code in (404, 405):
                resp = await client.post(
                    f"{get_n8n_host()}/api/v1/workflows/{payload.workflow_id}/activate",
                    headers=get_n8n_headers()
                )
            if resp.status_code >= 400:
                raise HTTPException(status_code=resp.status_code, detail=parse_n8n_error(resp))
            return resp.json()
        except httpx.RequestError as exc:
            raise HTTPException(status_code=502, detail=f"Failed to connect to n8n: {exc}")

@app.post("/deactivate_workflow", dependencies=[Depends(verify_jwt)])
async def deactivate_workflow(payload: WorkflowIdRequest):
    async with httpx.AsyncClient(timeout=20.0) as client:
        try:
            # In n8n 2.x, deactivation is done via /unpublish. Fallback to /deactivate for 1.x if needed.
            resp = await client.post(
                f"{get_n8n_host()}/api/v1/workflows/{payload.workflow_id}/unpublish",
                headers=get_n8n_headers()
            )
            if resp.status_code in (404, 405):
                resp = await client.post(
                    f"{get_n8n_host()}/api/v1/workflows/{payload.workflow_id}/deactivate",
                    headers=get_n8n_headers()
                )
            if resp.status_code >= 400:
                raise HTTPException(status_code=resp.status_code, detail=parse_n8n_error(resp))
            return resp.json()
        except httpx.RequestError as exc:
            raise HTTPException(status_code=502, detail=f"Failed to connect to n8n: {exc}")

@app.post("/trigger_execution", dependencies=[Depends(verify_jwt)])
async def trigger_execution(payload: TriggerExecutionRequest):
    async with httpx.AsyncClient(timeout=20.0) as client:
        # Step 1: Fetch workflow to find Webhook node
        try:
            wf_resp = await client.get(
                f"{get_n8n_host()}/api/v1/workflows/{payload.workflow_id}",
                headers=get_n8n_headers()
            )
            if wf_resp.status_code >= 400:
                raise HTTPException(status_code=wf_resp.status_code, detail=parse_n8n_error(wf_resp))
            workflow_data = wf_resp.json()
        except httpx.RequestError as exc:
            raise HTTPException(status_code=502, detail=f"Failed to connect to n8n: {exc}")

        # Step 2: Inspect nodes for a Webhook node
        nodes = workflow_data.get("nodes", [])
        webhook_node = None
        for node in nodes:
            node_type = str(node.get("type", ""))
            if node_type == "n8n-nodes-base.webhook" or "webhook" in node_type.lower():
                webhook_node = node
                break

        if not webhook_node:
            raise HTTPException(
                status_code=400,
                detail=f"Workflow '{payload.workflow_id}' cannot be triggered: no Webhook node found. In n8n, workflows must contain a Webhook node to be triggered on demand via API."
            )

        parameters = webhook_node.get("parameters", {})
        path = parameters.get("path") or webhook_node.get("webhookId")
        if not path:
            raise HTTPException(
                status_code=400,
                detail=f"Webhook node in workflow '{payload.workflow_id}' has no path configured."
            )

        path = str(path).lstrip("/")
        webhook_url = f"{get_n8n_host()}/webhook/{path}"
        http_method = parameters.get("httpMethod", "POST").upper()

        # Step 3: Trigger the webhook
        try:
            if http_method == "GET" and not payload.payload:
                trigger_resp = await client.get(webhook_url, headers=get_n8n_headers())
            else:
                trigger_resp = await client.post(webhook_url, json=payload.payload or {}, headers=get_n8n_headers())

            if trigger_resp.status_code >= 400:
                raise HTTPException(status_code=trigger_resp.status_code, detail=parse_n8n_error(trigger_resp))

            try:
                return trigger_resp.json()
            except Exception:
                return {"message": "Workflow was started", "response": trigger_resp.text}
        except httpx.RequestError as exc:
            raise HTTPException(status_code=502, detail=f"Failed to trigger webhook at {webhook_url}: {exc}")

@app.post("/get_execution", dependencies=[Depends(verify_jwt)])
async def get_execution(payload: ExecutionIdRequest):
    async with httpx.AsyncClient(timeout=20.0) as client:
        try:
            resp = await client.get(
                f"{get_n8n_host()}/api/v1/executions/{payload.execution_id}",
                headers=get_n8n_headers()
            )
            if resp.status_code >= 400:
                raise HTTPException(status_code=resp.status_code, detail=parse_n8n_error(resp))
            return resp.json()
        except httpx.RequestError as exc:
            raise HTTPException(status_code=502, detail=f"Failed to connect to n8n: {exc}")
