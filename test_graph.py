#!/usr/bin/env python3
"""
North Star Knowledge Graph Quality Analyzer
Robust version with safer property access
"""

from neo4j import GraphDatabase
import time

# Configuration
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "BowserNodes"

class NorthStarGraphAnalyzer:
    def __init__(self):
        self.driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        
    def close(self):
        """Close the Neo4j driver connection"""
        if hasattr(self, 'driver'):
            self.driver.close()
            
    def run_query(self, query, description):
        """Run a query with timeout and error handling"""
        print(f"  {description}...", end=" ")
        start_time = time.time()
        
        try:
            with self.driver.session(database="neo4j") as session:
                result = session.run(query)
                record = result.single()
                elapsed = time.time() - start_time
                
                if record:
                    value = record.values()[0]
                    print(f"✅ {value} (took {elapsed:.2f}s)")
                    return value
                else:
                    print("⚠️  No results")
                    return None
                    
        except Exception as e:
            elapsed = time.time() - start_time
            print(f"❌ Error after {elapsed:.2f}s: {e}")
            return None
    
    def analyze_connectivity_metrics(self):
        """Analyze connectivity metrics from North Star goal #1"""
        print("\n--- Connectivity Metrics (North Star #1) ---")
        
        # Basic connectivity
        avg_degree = self.run_query("MATCH (n) RETURN avg(size((n)--())) AS avg", "Average degree")
        max_degree = self.run_query("MATCH (n) RETURN max(size((n)--())) AS max", "Maximum degree")
        min_degree = self.run_query("MATCH (n) RETURN min(size((n)--())) AS min", "Minimum degree")
        
        # Network density (simplified calculation)
        node_count = self.run_query("MATCH (n) RETURN count(n) AS count", "Node count")
        rel_count = self.run_query("MATCH ()-->() RETURN count(*) AS count", "Relationship count")
        
        if node_count and node_count > 1:
            max_possible_edges = node_count * (node_count - 1) / 2
            density = rel_count / max_possible_edges if max_possible_edges > 0 else 0
            print(f"  Network density: {density:.8f}")
        
        # Degree distribution
        print("\n  Degree Distribution:")
        with self.driver.session(database="neo4j") as session:
            result = session.run("""
                MATCH (n) 
                WITH size((n)--()) AS degree
                RETURN degree, count(*) AS count
                ORDER BY degree
            """)
            
            degrees = []
            for record in result:
                degrees.append(record["degree"])
            
            if degrees:
                import statistics
                print(f"    Median degree: {statistics.median(degrees)}")
                print(f"    95th percentile: {sorted(degrees)[int(len(degrees)*0.95)]}")
    
    def analyze_completeness_metrics(self):
        """Analyze completeness metrics from North Star goal #2"""
        print("\n--- Completeness Metrics (North Star #2) ---")
        
        # RxNorm coverage - how many of the expected 82,020 RxCUIs do we have?
        rxcui_count = self.run_query("MATCH (n:Tier1) RETURN count(DISTINCT n.rxcui) AS count", "Unique RxCUIs in graph")
        expected_rxcuis = 82020
        coverage = (rxcui_count / expected_rxcuis * 100) if rxcui_count else 0
        print(f"  RxNorm coverage: {coverage:.2f}% ({rxcui_count}/{expected_rxcuis})")
        
        # Property completeness
        print("\n  Property Completeness:")
        with self.driver.session(database="neo4j") as session:
            properties = ['name', 'tty', 'sab', 'tier', 'primary_tty', 'rxnorm_hierarchy_level']
            for prop in properties:
                result = session.run(f"MATCH (n) RETURN count(n) AS total, count(n.{prop}) AS with_prop")
                record = result.single()
                total = record["total"]
                with_prop = record["with_prop"]
                percentage = (with_prop / total * 100) if total > 0 else 0
                print(f"    {prop}: {percentage:.2f}%")
        
        # Relationship type coverage
        print("\n  Relationship Type Coverage:")
        with self.driver.session(database="neo4j") as session:
            result = session.run("MATCH ()-[r]->() RETURN count(DISTINCT type(r)) AS count")
            record = result.single()
            rel_types = record["count"]
            print(f"    Unique relationship types: {rel_types}")
            
            # Show all relationship types
            result = session.run("MATCH ()-[r]->() RETURN type(r) AS type, count(r) AS count ORDER BY count DESC")
            for record in result:
                rel_type = record["type"]
                count = record["count"]
                print(f"      {rel_type}: {count}")
    
    def analyze_structural_quality_metrics(self):
        """Analyze structural quality metrics from North Star goal #3"""
        print("\n--- Structural Quality Metrics (North Star #3) ---")
        
        # Component analysis (without GDS)
        print("  Component Analysis:")
        with self.driver.session(database="neo4j") as session:
            # Simple component analysis using Cypher
            result = session.run("""
                MATCH (n)
                WHERE size((n)--()) = 0
                RETURN count(*) AS isolated_nodes
            """)
            record = result.single()
            isolated_nodes = record["isolated_nodes"]
            print(f"    Isolated nodes (degree 0): {isolated_nodes}")
            
            # Check for potential small components (fixed syntax)
            result = session.run("""
                MATCH (n)
                WHERE size((n)--()) >= 1 AND size((n)--()) <= 5
                RETURN count(*) AS low_degree_nodes
            """)
            record = result.single()
            low_degree_nodes = record["low_degree_nodes"]
            print(f"    Low degree nodes (1-5 connections): {low_degree_nodes}")
        
        # Centrality measures (sample for performance)
        print("\n  Centrality Measures (Top 10 nodes):")
        with self.driver.session(database="neo4j") as session:
            # Betweenness centrality (sample)
            result = session.run("""
                MATCH (n)
                WITH n, size((n)--()) AS degree
                ORDER BY degree DESC
                LIMIT 10
                RETURN n.rxcui, n.name, degree
            """)
            print("    Top 10 nodes by degree (proxy for centrality):")
            for record in result:
                try:
                    rxcui = record["rxcui"]
                    name = record["name"]
                    degree = record["degree"]
                    print(f"      {rxcui} ({name}): {degree} connections")
                except KeyError:
                    # Handle case where properties might be missing
                    degree = record["degree"]
                    print(f"      Unknown node: {degree} connections")
        
        # RxNorm Hierarchy Depth
        print("\n  RxNorm Hierarchy Depth:")
        with self.driver.session(database="neo4j") as session:
            result = session.run("""
                MATCH (n)-[:isa*1..5]->(m)
                WHERE n.tier = 'Ingredient' AND m.tier = 'ClinicalDrug'
                RETURN count(*) AS paths
            """)
            record = result.single()
            paths = record["paths"]
            print(f"    Ingredient to Clinical Drug paths: {paths}")
            
            # Check max depth
            result = session.run("""
                MATCH path = (n)-[:isa*]->(m)
                RETURN max(length(path)) AS max_depth
            """)
            record = result.single()
            max_depth = record["max_depth"]
            print(f"    Maximum hierarchy depth: {max_depth}")
    
    def analyze_semantic_quality_metrics(self):
        """Analyze semantic quality metrics from North Star goal #4"""
        print("\n--- Semantic Quality Metrics (North Star #4) ---")
        
        # Schema consistency
        print("  Schema Consistency:")
        with self.driver.session(database="neo4j") as session:
            # Check if nodes have expected properties for their tier
            result = session.run("""
                MATCH (n)
                WHERE n.tier IS NOT NULL
                RETURN n.tier, count(n) AS count, count(n.name) AS with_name, count(n.primary_tty) AS with_primary_tty
                ORDER BY count DESC
            """)
            for record in result:
                # Safely access properties by index instead of key
                try:
                    values = record.values()
                    tier = values[0] if len(values) > 0 else "Unknown"
                    count = values[1] if len(values) > 1 else 0
                    with_name = values[2] if len(values) > 2 else 0
                    with_primary_tty = values[3] if len(values) > 3 else 0
                    
                    name_pct = (with_name / count * 100) if count > 0 else 0
                    tty_pct = (with_primary_tty / count * 100) if count > 0 else 0
                    print(f"    {tier}: {name_pct:.1f}% have name, {tty_pct:.1f}% have primary_tty")
                except Exception as e:
                    print(f"    Error processing record: {e}")
                    continue
        
        # Relationship type appropriateness
        print("\n  Relationship Type Appropriateness:")
        with self.driver.session(database="neo4j") as session:
            # Check if relationships connect appropriate node types
            result = session.run("""
                MATCH (n1)-[r]->(n2)
                RETURN type(r) AS rel_type, n1.tier AS source_tier, n2.tier AS target_tier, count(*) AS count
                ORDER BY count DESC
                LIMIT 10
            """)
            print("    Top 10 relationship type patterns:")
            for record in result:
                try:
                    # Safely access properties by index
                    values = record.values()
                    rel_type = values[0] if len(values) > 0 else "Unknown"
                    source_tier = values[1] if len(values) > 1 else "Unknown"
                    target_tier = values[2] if len(values) > 2 else "Unknown"
                    count = values[3] if len(values) > 3 else 0
                    
                    print(f"      {source_tier} -[{rel_type}]-> {target_tier}: {count}")
                except Exception as e:
                    print(f"    Error processing record: {e}")
                    continue
        
        # Property coherence
        print("\n  Property Coherence:")
        with self.driver.session(database="neo4j") as session:
            # Check if property values make sense for their node types
            result = session.run("""
                MATCH (n)
                WHERE n.tier = 'Ingredient' AND n.name CONTAINS ' '
                RETURN count(*) AS count
            """)
            record = result.single()
            multi_word_ingredients = record["count"]
            print(f"    Ingredients with multi-word names: {multi_word_ingredients}")
            
            # Check for potential data quality issues
            result = session.run("""
                MATCH (n)
                WHERE n.tier = 'Ingredient' AND (n.name =~ '[0-9]' OR n.name =~ '[^a-zA-Z ]')
                RETURN count(*) AS count
            """)
            record = result.single()
            suspicious_ingredients = record["count"]
            print(f"    Ingredients with suspicious names: {suspicious_ingredients}")
    
    def analyze_graph(self):
        """Analyze the graph with all North Star metrics"""
        print("=== North Star Knowledge Graph Quality Analyzer ===")
        
        # Run all metric categories
        self.analyze_connectivity_metrics()
        self.analyze_completeness_metrics()
        self.analyze_structural_quality_metrics()
        self.analyze_semantic_quality_metrics()
        
        print("\n=== Analysis Complete ===")
        return True

if __name__ == "__main__":
    try:
        analyzer = NorthStarGraphAnalyzer()
        analyzer.analyze_graph()
    except KeyboardInterrupt:
        print("\n❌ Analysis interrupted by user")
    except Exception as e:
        print(f"\n❌ Analysis failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if 'analyzer' in locals():
            analyzer.close()
