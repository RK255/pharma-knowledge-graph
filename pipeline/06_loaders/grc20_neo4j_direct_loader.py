#!/usr/bin/env python3
"""
GRC-20 Neo4j Direct Loader v1
=============================

This script loads GRC-20 data directly into Neo4j without CSV conversion.
It uses batch Cypher queries for efficient loading.

Features:
- Direct JSON to Neo4j loading
- Batch processing for performance
- Progress tracking
- Error handling
- Index creation
"""

import json
import sys
import time
from pathlib import Path
from typing import List, Dict, Any

try:
    from neo4j import GraphDatabase
except ImportError:
    print("Error: neo4j Python driver not installed")
    print("Install with: pip install neo4j")
    sys.exit(1)

class GRC20Neo4jLoader:
    def __init__(
        self,
        uri: str = "bolt://localhost:7687",
        user: str = "neo4j",
        password: str = "BowserNodes",
        database: str = "neo4j",
        batch_size: int = 1000
    ):
        self.uri = uri
        self.user = user
        self.password = password
        self.database = database
        self.batch_size = batch_size
        self.driver = None
        
        # Statistics
        self.stats = {
            'entities_loaded': 0,
            'triples_loaded': 0,
            'relation_entities_loaded': 0,
            'provenance_entities_loaded': 0,
            'errors': 0,
            'start_time': None,
            'end_time': None,
        }
    
    def connect(self):
        """Connect to Neo4j"""
        print(f"Connecting to Neo4j at {self.uri}...")
        self.driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
        
        # Verify connection
        with self.driver.session(database=self.database) as session:
            result = session.run("RETURN 1 as test")
            result.single()
        
        print("Connected successfully!")
    
    def disconnect(self):
        """Disconnect from Neo4j"""
        if self.driver:
            self.driver.close()
            print("Disconnected from Neo4j")
    
    def create_indexes(self):
        """Create indexes for better performance"""
        print("\nCreating indexes...")
        
        indexes = [
            "CREATE INDEX entity_id_index IF NOT EXISTS FOR (e:Entity) REQUIRE (e.id) IS NODE KEY",
            "CREATE INDEX entity_name_index IF NOT EXISTS FOR (e:Entity) REQUIRE (e.name) IS NODE KEY",
            "CREATE INDEX relation_from_index IF NOT EXISTS FOR (r:Relation) REQUIRE (r.from_entity) IS NODE KEY",
            "CREATE INDEX relation_to_index IF NOT EXISTS FOR (r:Relation) REQUIRE (r.to_entity) IS NODE KEY",
        ]
        
        with self.driver.session(database=self.database) as session:
            for index in indexes:
                try:
                    session.run(index)
                    print(f"  Created: {index.split()[2]}")
                except Exception as e:
                    print(f"  Error creating index: {e}")
        
        print("Indexes created!")
    
    def clear_database(self):
        """Clear all data from the database"""
        print("\nClearing database...")
        
        with self.driver.session(database=self.database) as session:
            # Delete all nodes and relationships
            session.run("MATCH (n) DETACH DELETE n")
            print("Database cleared!")
    
    def load_entities(self, entities: List[Dict[str, Any]]):
        """Load entities into Neo4j"""
        print("\n" + "=" * 80)
        print("LOADING ENTITIES")
        print("=" * 80)
        
        self.stats['start_time'] = time.time()
        
        total_entities = len(entities)
        batch_count = 0
        
        # Process in batches
        for i in range(0, total_entities, self.batch_size):
            batch = entities[i:i + self.batch_size]
            batch_count += 1
            
            try:
                self._load_entity_batch(batch)
                self.stats['entities_loaded'] += len(batch)
                
                # Progress update
                if batch_count % 10 == 0:
                    progress = (i + len(batch)) / total_entities * 100
                    elapsed = time.time() - self.stats['start_time']
                    rate = self.stats['entities_loaded'] / elapsed if elapsed > 0 else 0
                    eta = (total_entities - self.stats['entities_loaded']) / rate if rate > 0 else 0
                    
                    print(f"  Progress: {progress:.1f}% | "
                          f"Loaded: {self.stats['entities_loaded']:,}/{total_entities:,} | "
                          f"Rate: {rate:.0f} entities/sec | "
                          f"ETA: {eta/60:.1f} min")
            
            except Exception as e:
                print(f"  Error loading batch {batch_count}: {e}")
                self.stats['errors'] += 1
        
        self.stats['end_time'] = time.time()
        total_time = self.stats['end_time'] - self.stats['start_time']
        
        print("\n" + "=" * 80)
        print("ENTITY LOADING COMPLETE")
        print("=" * 80)
        print(f"  Total entities loaded: {self.stats['entities_loaded']:,}")
        print(f"  Total triples loaded: {self.stats['triples_loaded']:,}")
        print(f"  Total relation entities: {self.stats['relation_entities_loaded']:,}")
        print(f"  Total provenance entities: {self.stats['provenance_entities_loaded']:,}")
        print(f"  Errors: {self.stats['errors']:,}")
        print(f"  Total time: {total_time:.2f} seconds ({total_time/60:.2f} minutes)")
        print(f"  Average rate: {self.stats['entities_loaded']/total_time:.0f} entities/sec")
        print("=" * 80)
    
    def _load_entity_batch(self, batch: List[Dict[str, Any]]):
        """Load a batch of entities"""
        
        # Prepare batch data
        entity_data = []
        triple_data = []
        relation_data = []
        
        for entity in batch:
            entity_id = entity.get('entity', '')
            triples = entity.get('triples', [])
            
            # Determine entity type
            entity_types = []
            for triple in triples:
                attr = triple.get('attribute', '')
                value = triple.get('value', {})
                
                if isinstance(value, dict):
                    val = value.get('value', '')
                else:
                    val = value
                
                if attr == "Jfmby78N4BCseZinBmdVov":  # Type attribute
                    entity_types.append(str(val))
            
            # Collect entity properties
            props = {"id": entity_id}
            for triple in triples:
                attr = triple.get('attribute', '')
                value = triple.get('value', {})
                
                if isinstance(value, dict):
                    val = value.get('value', '')
                    val_type = value.get('type', 1)
                else:
                    val = value
                    val_type = 1
                
                # Store as property
                props[f"attr_{attr}"] = str(val)
                
                # Also track for triples
                triple_data.append({
                    'entity': entity_id,
                    'attribute': attr,
                    'value': str(val),
                    'value_type': val_type,
                })
            
            # Check if this is a relation entity
            is_relation = False
            for t in entity_types:
                if t == "QtC4Ay8HNLwSd1kSARgcDE":  # Relation type
                    is_relation = True
                    break
            
            if is_relation:
                self.stats['relation_entities_loaded'] += 1
                
                # Extract relation properties
                from_entity = props.get('attr_RERshk4JoYoMC17r1qAo9J')  # from_entity
                to_entity = props.get('attr_Qx8dASiTNsxxP3rJbd4Lzd')  # to_entity
                
                if from_entity and to_entity:
                    relation_data.append({
                        'id': entity_id,
                        'from': from_entity,
                        'to': to_entity,
                        'types': entity_types,
                    })
            
            # Check if this is a provenance entity
            is_provenance = False
            for t in entity_types:
                if "Provenance" in str(t):  # Provenance type
                    is_provenance = True
                    break
            
            if is_provenance:
                self.stats['provenance_entities_loaded'] += 1
            
            entity_data.append({
                'id': entity_id,
                'types': entity_types,
                'properties': props,
            })
            
            self.stats['triples_loaded'] += len(triples)
        
        # Execute Cypher queries
        with self.driver.session(database=self.database) as session:
            # Create entity nodes
            if entity_data:
                session.run("""
                    UNWIND $batch AS data
                    MERGE (e:Entity {id: data.id})
                    SET e += data.properties
                    WITH e, data
                    UNWIND data.types AS type
                    CALL apoc.create.addLabels(e, [type]) YIELD node
                    RETURN count(*)
                """, batch=entity_data)
            
            # Create relationships
            if relation_data:
                session.run("""
                    UNWIND $batch AS data
                    MATCH (from:Entity {id: data.from})
                    MATCH (to:Entity {id: data.to})
                    MERGE (r:Relation {id: data.id})
                    SET r.from_entity = data.from
                    SET r.to_entity = data.to
                    MERGE (from)-[rel:RELATED_TO]->(r)
                    MERGE (r)-[rel2:RELATED_TO]->(to)
                    RETURN count(*)
                """, batch=relation_data)
    
    def verify_load(self):
        """Verify the load"""
        print("\n" + "=" * 80)
        print("VERIFYING LOAD")
        print("=" * 80)
        
        with self.driver.session(database=self.database) as session:
            # Count nodes
            result = session.run("MATCH (n) RETURN count(n) as count")
            node_count = result.single()['count']
            print(f"Total nodes: {node_count:,}")
            
            # Count relationships
            result = session.run("MATCH ()-[r]->() RETURN count(r) as count")
            rel_count = result.single()['count']
            print(f"Total relationships: {rel_count:,}")
            
            # Count entity nodes
            result = session.run("MATCH (e:Entity) RETURN count(e) as count")
            entity_count = result.single()['count']
            print(f"Entity nodes: {entity_count:,}")
            
            # Count relation nodes
            result = session.run("MATCH (r:Relation) RETURN count(r) as count")
            relation_count = result.single()['count']
            print(f"Relation nodes: {relation_count:,}")
            
            # Sample queries
            print("\nSample queries:")
            
            # Find nodes with most connections
            result = session.run("""
                MATCH (n)-[r]-()
                RETURN n.id as id, labels(n) as labels, count(r) as connections
                ORDER BY connections DESC
                LIMIT 5
            """)
            
            print("\nTop 5 most connected nodes:")
            for record in result:
                print(f"  {record['id'][:20]}... | {record['labels']} | {record['connections']} connections")
        
        print("=" * 80)
    
    def load_data(self, data_file: str, clear: bool = False):
        """Load data from file"""
        
        # Connect
        self.connect()
        
        try:
            # Clear database if requested
            if clear:
                self.clear_database()
            
            # Create indexes
            self.create_indexes()
            
            # Load data
            print(f"\nLoading data from {data_file}...")
            with open(data_file, 'r') as f:
                data = json.load(f)
            
            entities = data.get('entities', [])
            print(f"Found {len(entities):,} entities in file")
            
            # Load entities
            self.load_entities(entities)
            
            # Verify
            self.verify_load()
            
        finally:
            # Disconnect
            self.disconnect()

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Load GRC-20 data into Neo4j")
    parser.add_argument("data_file", help="Path to GRC-20 JSON file")
    parser.add_argument("--uri", default="bolt://localhost:7687", help="Neo4j URI")
    parser.add_argument("--user", default="neo4j", help="Neo4j user")
    parser.add_argument("--password", default="BowserNodes", help="Neo4j password")
    parser.add_argument("--database", default="neo4j", help="Neo4j database name")
    parser.add_argument("--batch-size", type=int, default=1000, help="Batch size")
    parser.add_argument("--clear", action="store_true", help="Clear database before loading")
    
    args = parser.parse_args()
    
    loader = GRC20Neo4jLoader(
        uri=args.uri,
        user=args.user,
        password=args.password,
        database=args.database,
        batch_size=args.batch_size
    )
    
    loader.load_data(args.data_file, clear=args.clear)

if __name__ == "__main__":
    main()
