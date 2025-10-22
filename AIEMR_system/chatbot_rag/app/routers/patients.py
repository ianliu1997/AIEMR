import time
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from app.deps import get_driver
from app.config import settings
from app.models import GraphResponse, GraphNode, GraphEdge
from app.services.visualize import fetch_patient_graph, to_pyvis_html

router = APIRouter(prefix="/patients", tags=["patients"])

@router.get("/{patient_id}/graph", response_model=GraphResponse)
def get_graph(patient_id: str, driver = Depends(get_driver)):
    G = fetch_patient_graph(driver, patient_id)
    if G.number_of_nodes() == 0:
        raise HTTPException(404, f"No graph found for {patient_id}")
    nodes = [GraphNode(id=str(n), attrs=dict(G.nodes[n])) for n in G.nodes]
    edges = [GraphEdge(source=str(u), target=str(v), attrs=dict(G.edges[u, v])) for u, v in G.edges]
    return GraphResponse(patient_id=patient_id, nodes=nodes, edges=edges)

@router.get("/{patient_id}/graph.html", response_class=FileResponse)
def get_graph_html(patient_id: str, driver = Depends(get_driver)):
    G = fetch_patient_graph(driver, patient_id)
    if G.number_of_nodes() == 0:
        raise HTTPException(404, f"No graph found for {patient_id}")
    fname = f"patient_{patient_id}_{int(time.time())}.html"
    out = settings.GRAPH_HTML_DIR / fname
    to_pyvis_html(G, str(out))
    return FileResponse(out, media_type="text/html")
