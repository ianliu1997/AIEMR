"""AIEMR Gateway BFF package."""

from __future__ import annotations

import os

# Provide safe defaults so that importing the underlying GraphRAG modules does not
# raise validation errors in environments where secrets are not configured yet.
os.environ.setdefault("NEO4J_URI", "bolt://localhost:7687")
os.environ.setdefault("NEO4J_USER", "neo4j")
os.environ.setdefault("NEO4J_PASS", "password")
os.environ.setdefault("QDRANT_URL", "http://localhost:6333")
os.environ.setdefault("QDRANT_API_KEY", "placeholder")
os.environ.setdefault("OPENAI_API_KEY", "placeholder")
