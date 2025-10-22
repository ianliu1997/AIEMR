from pydantic import BaseModel, Field
from typing import List, Dict, Any

class GraphNode(BaseModel):
    id: str
    attrs: Dict[str, Any]

class GraphEdge(BaseModel):
    source: str
    target: str
    attrs: Dict[str, Any]

class GraphResponse(BaseModel):
    patient_id: str
    nodes: List[GraphNode]
    edges: List[GraphEdge]
