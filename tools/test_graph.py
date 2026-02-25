#!/usr/bin/env python3
"""Test script for Neo4j graph queries."""
import os
from neo4j import GraphDatabase

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

class GraphTest:
    def __init__(self):
        if not NEO4J_PASSWORD:
            raise ValueError("NEO4J_PASSWORD environment variable not set")
        self.driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    
    def close(self):
        self.driver.close()
    
    def test_connection(self):
        with self.driver.session() as session:
            result = session.run("RETURN 1 as test")
            return result.single()["test"] == 1

if __name__ == "__main__":
    gt = GraphTest()
    print(f"Connection test: {gt.test_connection()}")
    gt.close()
