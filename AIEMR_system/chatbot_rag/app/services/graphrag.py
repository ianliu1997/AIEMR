# app/services/graphrag.py
from typing import Dict, Any
from neo4j import Driver
from langchain_neo4j import GraphCypherQAChain, Neo4jGraph
from langchain_openai import ChatOpenAI
from app.config import settings

def graph_answer(driver: Driver, question: str) -> Dict[str, Any]:
    """
    Graph-based QA using LangChain's GraphCypherQAChain.
    Automatically generates Cypher queries to answer questions about the knowledge graph.
    """
    # Initialize Neo4j graph connection (reuse driver connection info)
    kg = Neo4jGraph(
        url=settings.NEO4J_URI, 
        username=settings.NEO4J_USER, 
        password=settings.NEO4J_PASS
    )
    kg.refresh_schema()
    
    # Create GraphCypherQAChain with OpenAI models
    grag_chain = GraphCypherQAChain.from_llm(
        cypher_llm=ChatOpenAI(
            model='gpt-5', 
            temperature=0,
            api_key=settings.OPENAI_API_KEY
        ),
        qa_llm=ChatOpenAI(
            model=settings.CHAT_MODEL,  # Use configured chat model (gpt-4o-mini by default)
            temperature=0.2,
            api_key=settings.OPENAI_API_KEY
        ),
        graph=kg,
        verbose=True,
        allow_dangerous_requests=True,
        return_intermediate_steps=True
    )
    
    result = grag_chain.invoke({"query": question})
    return {
        "answer": result['result'], 
        "intermediate_steps": result['intermediate_steps']
    }
    '''
        rows = [dict(r) for r in s.run(PATIENT_FACTS, pid=pid)]
    if not rows:
        return {"answer": f"No facts found for patientID {pid}."}
    return {"answer": f"Facts for patientID {pid}", "facts": rows}
    '''