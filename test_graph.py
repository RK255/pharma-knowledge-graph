#!/usr/bin/env python3
"""
Dynamic Knowledge Graph Quality Analyzer - Final Version
Analyzes graph quality against selected RxNorm source files
"""

from neo4j import GraphDatabase
import time
import os
import re
import glob

# Configuration
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "BowserNodes"
RXNORM_BASE_PATH = "/mnt/fast_raid/server_projects/Geo/graph_workshop/data/raw_data/extracted_rrf"

class DynamicGraphAnalyzer:
    def __init__(self):
        self.driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        
    def close(self):
        """Close the Neo4j driver connection"""
        if hasattr(self, 'driver'):
            self.driver.close()
    
    def select_rxnorm_dataset(self):
        """Prompt user to select which RxNorm dataset to test against"""
        print("\n--- Available RxNorm Datasets ---")
        
        # Find all RxNorm datasets
        datasets = []
        rxnorm_paths = glob.glob(os.path.join(RXNORM_BASE_PATH, "RxNorm*_extracted"))
        
        if not rxnorm_paths:
            print("No RxNorm datasets found in the expected path.")
            return None
        
        # Sort datasets by date (newest first)
        rxnorm_paths.sort(reverse=True)
        
        # Display options to user
        for i, path in enumerate(rxnorm_paths):
            dirname = os.path.basename(path)
            # Extract date from directory name
            match = re.search(r'RxNorm(\d+)_extracted', dirname)
            if match:
                date_str = match.group(1)
                formatted_date = f"{date_str[:2]}-{date_str[2:4]}-{date_str[4:]}"
                print(f"  {i+1}. RxNorm from {formatted_date}")
            else:
                print(f"  {i+1}. {dirname}")
            datasets.append(path)
        
        # Get user selection
        while True:
            try:
                choice = input(f"\nSelect RxNorm dataset (1-{len(datasets)}) or press Enter for newest: ")
                if not choice:
                    selected_index = 0  # Default to newest
                else:
                    selected_index = int(choice) - 1
                
                if 0 <= selected_index < len(datasets):
                    selected_path = datasets[selected_index]
                    dirname = os.path.basename(selected_path)
                    print(f"\nSelected: {dirname}")
                    return os.path.join(selected_path, "rrf")
                else:
                    print("Invalid selection. Please try again.")
            except ValueError:
                print("Please enter a valid number.")
    
    def count_rxcuis_in_source_files(self, rrf_path):
        """Count unique RxCUIs in the source RxNorm files"""
        print(f"\n--- Counting RxCUIs in Source Files ---")
        
        # Check for RXNCONSO.RRF file
        rxnconso_path = os.path.join(rrf_path, "RXNCONSO.RRF")
        if not os.path.exists(rxnconso_path):
            print(f"  RXNCONSO.RRF not found at {rxnconso_path}")
            return None
        
        print(f"  Analyzing {rxnconso_path}...")
        rxcuis = set()
        line_count = 0
        
        with open(rxnconso_path, 'r', encoding='utf-8') as f:
            for line in f:
                line_count += 1
                if line_count % 1000000 == 0:
                    print(f"    Processed {line_count} lines, found {len(rxcuis)} unique RxCUIs so far...")
                
                fields = line.strip().split('|')
                if len(fields) >= 8:
                    rxcui = fields[0]
                    rxcuis.add(rxcui)
        
        print(f"  Found {len(rxcuis)} unique RxCUIs in RXNCONSO.RRF")
        return len(rxcuis)
    
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
        
        # Investigate hub nodes with extremely high degree
        if max_degree and max_degree > 1000:
            print("\n  Investigating hub nodes with extremely high degree:")
            with self.driver.session(database="neo4j") as session:
                result = session.run("""
                    MATCH (n)
                    WITH n, size((n)--()) AS degree
                    WHERE degree > 1000
                    RETURN n.name, n.tier, degree, n.rxcui
                    ORDER BY degree DESC
                    LIMIT 5
                """)
                for record in result:
                    try:
                        values = record.values()
                        name = values[0] if len(values) > 0 and values[0] else "Unknown"
                        tier = values[1] if len(values) > 1 and values[1] else "Unknown"
                        degree = values[2] if len(values) > 2 else 0
                        rxcui = values[3] if len(values) > 3 and values[3] else "Unknown"
                        print(f"    {name} ({tier}, RxCUI: {rxcui}): {degree} connections")
                    except Exception:
                        continue
    
    def analyze_completeness_metrics(self, expected_rxcuis):
        """Analyze completeness metrics from North Star goal #2"""
        print("\n--- Completeness Metrics (North Star #2) ---")
        
        # RxNorm coverage - using dynamic expected count
        rxcui_count = self.run_query("MATCH (n) RETURN count(DISTINCT n.rxcui) AS count", "Unique RxCUIs in graph")
        
        if expected_rxcuis and rxcui_count:
            coverage = (rxcui_count / expected_rxcuis * 100) if expected_rxcuis > 0 else 0
            print(f"  RxNorm coverage: {coverage:.2f}% ({rxcui_count}/{expected_rxcuis})")
            
            # Check for missing RxCUIs
            if rxcui_count < expected_rxcuis:
                missing = expected_rxcuis - rxcui_count
                print(f"  Missing RxCUIs: {missing}")
            elif rxcui_count > expected_rxcuis:
                extra = rxcui_count - expected_rxcuis
                print(f"  Extra RxCUIs: {extra}")
        else:
            print(f"  Unique RxCUIs in graph: {rxcui_count}")
        
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
            
            # Show top relationship types
            result = session.run("MATCH ()-[r]->() RETURN type(r) AS type, count(r) AS count ORDER BY count DESC LIMIT 10")
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
            
            # Check for potential small components
            result = session.run("""
                MATCH (n)
                WHERE size((n)--()) >= 1 AND size((n)--()) <= 5
                RETURN count(*) AS low_degree_nodes
            """)
            record = result.single()
            low_degree_nodes = record["low_degree_nodes"]
            print(f"    Low degree nodes (1-5 connections): {low_degree_nodes}")
            
            # Investigate isolated nodes
            if isolated_nodes > 0:
                print("\n    Investigating isolated nodes:")
                result = session.run("""
                    MATCH (n)
                    WHERE size((n)--()) = 0
                    RETURN n.tier, count(*) AS count
                    ORDER BY count DESC
                """)
                for record in result:
                    try:
                        values = record.values()
                        tier = values[0] if len(values) > 0 and values[0] else "Unknown"
                        count = values[1] if len(values) > 1 else 0
                        print(f"      {tier}: {count} isolated nodes")
                    except Exception:
                        continue
        
        # RxNorm Hierarchy Depth
        print("\n  RxNorm Hierarchy Depth:")
        with self.driver.session(database="neo4j") as session:
            result = session.run("""
                MATCH path = (n)-[:isa*]->(m)
                RETURN max(length(path)) AS max_depth
            """)
            record = result.single()
            max_depth = record["max_depth"]
            print(f"    Maximum hierarchy depth: {max_depth}")
            
            # Investigate Ingredient to Clinical Drug paths
            result = session.run("""
                MATCH (i:Ingredient), (c:ClinicalDrug)
                RETURN count(i) AS ingredient_count, count(c) AS clinical_drug_count
            """)
            record = result.single()
            print(f"    Ingredients: {record['ingredient_count']}, Clinical Drugs: {record['clinical_drug_count']}")
            
            # Check if there are any paths at all
            result = session.run("""
                MATCH path = (i:Ingredient)-[*1..5]-(c:ClinicalDrug)
                RETURN count(DISTINCT i) AS ingredients_with_paths, 
                       count(DISTINCT c) as clinical_drugs_with_paths,
                       min(length(path)) AS min_path_length,
                       max(length(path)) AS max_path_length
            """)
            record = result.single()
            try:
                values = record.values()
                ingredients_with_paths = values[0] if len(values) > 0 else 0
                clinical_drugs_with_paths = values[1] if len(values) > 1 else 0
                min_path = values[2] if len(values) > 2 else 0
                max_path = values[3] if len(values) > 3 else 0
                
                print(f"    Ingredients with paths to Clinical Drugs: {ingredients_with_paths}")
                print(f"    Clinical Drugs reachable from Ingredients: {clinical_drugs_with_paths}")
                if ingredients_with_paths > 0:
                    print(f"    Path lengths: {min_path} to {max_path}")
            except Exception:
                print("    Error analyzing paths between Ingredients and Clinical Drugs")
    
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
                try:
                    values = record.values()
                    tier = values[0] if len(values) > 0 else "Unknown"
                    count = values[1] if len(values) > 1 else 0
                    with_name = values[2] if len(values) > 2 else 0
                    with_primary_tty = values[3] if len(values) > 3 else 0
                    
                    name_pct = (with_name / count * 100) if count > 0 else 0
                    tty_pct = (with_primary_tty / count * 100) if count > 0 else 0
                    print(f"    {tier}: {name_pct:.1f}% have name, {tty_pct:.1f}% have primary_tty")
                except Exception:
                    continue
        
        # Investigate multi-word ingredient names
        print("\n  Investigating multi-word ingredient names:")
        with self.driver.session(database="neo4j") as session:
            result = session.run("""
                MATCH (i:Ingredient)
                WHERE i.name CONTAINS ' '
                RETURN count(i) AS multi_word_count, 
                       count(*) - count(i) AS single_word_count
            """)
            record = result.single()
            try:
                values = record.values()
                multi_word = values[0] if len(values) > 0 else 0
                single_word = values[1] if len(values) > 1 else 0
                total_ingredients = multi_word + single_word
                print(f"    Multi-word ingredients: {multi_word} ({multi_word/total_ingredients*100:.2f}%)")
                print(f"    Single-word ingredients: {single_word} ({single_word/total_ingredients*100:.2f}%)")
                
                # Examples of multi-word ingredients
                print("\n    Examples of multi-word ingredients:")
                result = session.run("""
                    MATCH (i:Ingredient)
                    WHERE i.name CONTAINS ' '
                    RETURN i.name
                    LIMIT 5
                """)
                for record in result:
                    try:
                        values = record.values()
                        print(f"      {values[0]}")
                    except Exception:
                        continue
            except Exception:
                print("    Error analyzing ingredient names")
    
    def analyze_graph(self):
        """Analyze the graph with dynamic metrics"""
        print("=== Dynamic Knowledge Graph Quality Analyzer ===")
        
        # Select RxNorm dataset
        rrf_path = self.select_rxnorm_dataset()
        if not rrf_path:
            print("No valid RxNorm dataset selected. Exiting.")
            return False
        
        # Count RxCUIs in source files
        expected_rxcuis = self.count_rxcuis_in_source_files(rrf_path)
        
        # Run all metric categories
        self.analyze_connectivity_metrics()
        self.analyze_completeness_metrics(expected_rxcuis)
        self.analyze_structural_quality_metrics()
        self.analyze_semantic_quality_metrics()
        
        print("\n=== Analysis Complete ===")
        return True

if __name__ == "__main__":
    try:
        analyzer = DynamicGraphAnalyzer()
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
