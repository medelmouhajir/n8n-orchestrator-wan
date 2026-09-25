import os
import jwt
import httpx
import logging
from typing import Optional, Dict, Any, List
from fastapi import FastAPI, HTTPException, Request, Depends
from pydantic import BaseModel
from app.schemas import Workflow

logger = logging.getLogger("n8n-skill")
app = FastAPI(title="n8n Orchestrator WAN", version="1.2.0")

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

@app.get("/health")
async def health_check():
    return {"status": "ok"}

class WorkflowIdRequest(BaseModel):
    workflow_id: str

class UpdateWorkflowRequest(BaseModel):
    workflow_id: str
    name: str
    nodes: List[Dict[str, Any]]
    connections: Optional[Dict[str, Any]] = None
    settings: Optional[Dict[str, Any]] = None

class ExecutionIdRequest(BaseModel):
    execution_id: str

@app.post("/get_workflows", dependencies=[Depends(verify_jwt)])
async def get_workflows():
    async with httpx.AsyncClient(timeout=20.0) as client:
        try:
            resp = await client.get(f"{get_n8n_host()}/api/v1/workflows", headers=get_n8n_headers())
            if resp.status_code >= 400:
                raise HTTPException(status_code=resp.status_code, detail=resp.text)
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
                raise HTTPException(status_code=resp.status_code, detail=resp.text)
            return resp.json()
        except httpx.RequestError as exc:
            raise HTTPException(status_code=502, detail=f"Failed to connect to n8n: {exc}")

@app.post("/update_workflow", dependencies=[Depends(verify_jwt)])
async def update_workflow(payload: UpdateWorkflowRequest):
    body: Dict[str, Any] = {
        "name": payload.name,
        "nodes": payload.nodes,
    }
    if payload.connections is not None:
        body["connections"] = payload.connections
    if payload.settings is not None:
        body["settings"] = payload.settings
    async with httpx.AsyncClient(timeout=20.0) as client:
        try:
            resp = await client.put(
                f"{get_n8n_host()}/api/v1/workflows/{payload.workflow_id}",
                json=body,
                headers=get_n8n_headers()
            )
            if resp.status_code >= 400:
                raise HTTPException(status_code=resp.status_code, detail=resp.text)
            return resp.json()
        except httpx.RequestError as exc:
            raise HTTPException(status_code=502, detail=f"Failed to connect to n8n: {exc}")

@app.post("/activate_workflow", dependencies=[Depends(verify_jwt)])
async def activate_workflow(payload: WorkflowIdRequest):
    async with httpx.AsyncClient(timeout=20.0) as client:
        try:
            resp = await client.post(
                f"{get_n8n_host()}/api/v1/workflows/{payload.workflow_id}/activate",
                headers=get_n8n_headers()
            )
            if resp.status_code >= 400:
                raise HTTPException(status_code=resp.status_code, detail=resp.text)
            return resp.json()
        except httpx.RequestError as exc:
            raise HTTPException(status_code=502, detail=f"Failed to connect to n8n: {exc}")

@app.post("/deactivate_workflow", dependencies=[Depends(verify_jwt)])
async def deactivate_workflow(payload: WorkflowIdRequest):
    async with httpx.AsyncClient(timeout=20.0) as client:
        try:
            resp = await client.post(
                f"{get_n8n_host()}/api/v1/workflows/{payload.workflow_id}/deactivate",
                headers=get_n8n_headers()
            )
            if resp.status_code >= 400:
                raise HTTPException(status_code=resp.status_code, detail=resp.text)
            return resp.json()
        except httpx.RequestError as exc:
            raise HTTPException(status_code=502, detail=f"Failed to connect to n8n: {exc}")

@app.post("/trigger_execution", dependencies=[Depends(verify_jwt)])
async def trigger_execution(payload: WorkflowIdRequest):
    async with httpx.AsyncClient(timeout=20.0) as client:
        try:
            resp = await client.post(
                f"{get_n8n_host()}/api/v1/executions",
                json={"workflowId": payload.workflow_id},
                headers=get_n8n_headers()
            )
            if resp.status_code >= 400:
                raise HTTPException(status_code=resp.status_code, detail=resp.text)
            return resp.json()
        except httpx.RequestError as exc:
            raise HTTPException(status_code=502, detail=f"Failed to connect to n8n: {exc}")

@app.post("/get_execution", dependencies=[Depends(verify_jwt)])
async def get_execution(payload: ExecutionIdRequest):
    async with httpx.AsyncClient(timeout=20.0) as client:
        try:
            resp = await client.get(
                f"{get_n8n_host()}/api/v1/executions/{payload.execution_id}",
                headers=get_n8n_headers()
            )
            if resp.status_code >= 400:
                raise HTTPException(status_code=resp.status_code, detail=resp.text)
            return resp.json()
        except httpx.RequestError as exc:
            raise HTTPException(status_code=502, detail=f"Failed to connect to n8n: {exc}")
