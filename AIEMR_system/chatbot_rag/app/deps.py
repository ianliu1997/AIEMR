from neo4j import GraphDatabase, Driver
from app.config import settings

_driver: Driver | None = None

def get_driver() -> Driver:
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USER, settings.NEO4J_PASS)
        )
    return _driver

def close_driver():
    global _driver
    if _driver:
        _driver.close()
        _driver = None
