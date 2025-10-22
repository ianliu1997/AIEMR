import networkx as nx
from pyvis.network import Network
from neo4j import Driver
from app.graph.cypher import RETRIEVE_PATIENT_CYPHER
from IPython.core.display import display, HTML

# Styling functions
def style_for_node(node):
    labs = set(node.labels); props = dict(node)
    if "Patient" in labs:
        return dict(label=f"Patient {props.get('patientID')}", color="#1f77b4", shape="ellipse", size=35)
    if "SectionTable" in labs:
        return dict(label=props.get("name","Section"), color="#2ca02c", shape="box", size=26)
    if "Schema" in labs:
        lbl = props.get("field") or props.get("section") or "Schema"
        return dict(label=lbl, color="#9467bd", shape="dot", size=18)
    if "Value" in labs:
        lbl = f"Entry {props.get('value')}" if props.get("valueType") == "dict" else str(props.get("value","value"))
        return dict(label=lbl, color="#ff7f0e", shape="diamond", size=14)
    return dict(label="/".join(labs), shape="dot", size=12)


def style_for_edge(rel):
    colors = {
        "HAS_GENERAL_INFORMATION": "#8c564b",
        "HAS_MENSTRUAL_HISTORY":   "#8c564b",
        "HAS_MEDICAL_HISTORY":     "#8c564b",
        "HAS_OBSTETRICS_HISTORY":  "#8c564b",
        "HAS_PAST_MEDICATION":     "#8c564b",
        "HAS_PAST_TESTING":        "#8c564b",
        "HAS_SEXUAL_HISTORY":      "#8c564b",
        "HAS_INFORMATION_OF":      "#17becf",
        "HAS_VALUE":               "#bcbd22",
    }
    return dict(label=rel.type, color=colors.get(rel.type, "#999"), arrows="to")


def fetch_patient_graph(driver: Driver, pid: str) -> nx.DiGraph:
    G = nx.DiGraph()
    seen = set()
    with driver.session() as s:
        rec = s.run(RETRIEVE_PATIENT_CYPHER, pid=pid).single()
        if not rec: return G
        for n in rec["nodes"]:
            nid = n.element_id
            if nid not in G:
                G.add_node(nid, **style_for_node(n))
        for r in rec["rels"]:
            sid, tid, t = r.start_node.element_id, r.end_node.element_id, r.type
            key = (sid, tid, t)
            if key in seen: continue
            G.add_edge(sid, tid, **style_for_edge(r)); seen.add(key)
    return G


def to_pyvis_html(G: nx.DiGraph, out_path: str):
    net = Network(height="750px", width="100%", bgcolor="#fff", font_color="#222",
                  directed=True, notebook=True, cdn_resources="in_line")
    net.barnes_hut(gravity=-16000, spring_length=180, central_gravity=0.0)
    net.from_nx(G)  # PyVis understands node/edge attrs
    
    # Generate HTML and write with UTF-8 encoding to avoid Windows cp1252 issues
    html_content = net.generate_html()
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    
    # For Jupyter notebooks
    display(HTML(open(out_path, "r", encoding="utf-8").read()))
