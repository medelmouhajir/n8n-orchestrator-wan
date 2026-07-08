from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

class Node(BaseModel):
    id: str = Field(..., description="Unique identifier for the node")
    name: str = Field(..., description="Name of the node")
    type: str = Field(..., description="Type of the node, e.g. n8n-nodes-base.httpRequest")
    typeVersion: float = Field(default=1, description="Version of the node type")
    position: List[float] = Field(..., description="X, Y coordinates on the canvas")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Node configuration parameters")

class ConnectionTarget(BaseModel):
    node: str
    type: str
    index: int

class WorkflowSettings(BaseModel):
    saveDataErrorExecution: str = Field(default="all")
    saveDataSuccessExecution: str = Field(default="all")
    saveExecutionProgress: bool = Field(default=True)
    saveManualExecutions: bool = Field(default=False)
    callerPolicy: str = Field(default="workflowsFromSameOwner")

class Workflow(BaseModel):
    name: str = Field(..., description="Name of the workflow")
    nodes: List[Node] = Field(..., description="List of nodes in the workflow")
    connections: Dict[str, Dict[str, List[List[ConnectionTarget]]]] = Field(
        default_factory=dict, 
        description="Connections between nodes"
    )
    settings: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Workflow settings")
    active: bool = Field(default=False, description="Whether the workflow is active")
