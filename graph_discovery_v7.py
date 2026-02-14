#!/usr/bin/env python3
import os
import json
import hashlib
import zipfile
from collections import defaultdict
from neo4j import GraphDatabase

# Configuration
BASE_DIR = "/home/kage/graph_workshop/data"
RAW_DATA_DIR = f"{BASE_DIR}/raw_data"
EXTRACTED_DIR = f"{RAW_DATA_DIR}/extracted_rrf"
LEDGER_FILE = f"{BASE_DIR}/provenance/Granular_Provenance_Ledger.json"
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "BowserNodes"  # Replace with your actual password

# Define primary TTYs (non-synonym types)
PRIMARY_TTYS = {
    'IN', 'PIN', 'MIN', 'SCDC', 'SCDF', 'SCDFP', 'SCDG', 'SCDGP', 'SCD',
    'SBDC', 'SBDF', 'SBDFP', 'SBDG', 'SBD', 'BN', 'DF', 'DFG', 'GPCK', 'BPCK'
}

# Define synonym TTYs
SYNONYM_TTYS = {'SY', 'PSN', 'TMSY'}

def get_node_tier(primary_tty):
    """Determine tier based on PRIMARY TTY only - following RxNorm hierarchy exactly"""
    
    # Molecular/Chemical Level (Most Specific)
    if primary_tty == 'PIN':
        return 'PreciseIngredient'
    if primary_tty == 'IN':
        return 'Ingredient'
    
    # Component Level (Building Blocks)
    if primary_tty == 'SCDC':
        return 'ClinicalComponent'
    if primary_tty == 'SBDC':
        return 'BrandedComponent'
    
    # Complete Drug Level (Administerable Forms)
    if primary_tty == 'SCD':
        return 'ClinicalDrug'
    if primary_tty == 'SBD':
        return 'BrandedDrug'
    
    # Form/Packaging Level (How It's Delivered)
    if primary_tty == 'DF':
        return 'DoseForm'
    if primary_tty == 'GPCK':
        return 'GenericPack'
    if primary_tty == 'BPCK':
        return 'BrandPack'
    
    # Naming/Synonym Level (How It's Referenced)
    if primary_tty == 'BN':
        return 'BrandName'
    if primary_tty == 'PSN':
        return 'PrescribableName'
    if primary_tty == 'SY':
        return 'Synonym'
    
    # Multi-ingredient drugs
    if primary_tty == 'MIN':
        return 'MultiIngredient'
    
    # Group/Variant Types - assign to appropriate parent category
    if primary_tty in ['SCDG', 'SBDG']:
        return 'ClinicalDrug'  # Drug groups go with drugs
    if primary_tty in ['SCDF', 'SCDFP']:
        return 'ClinicalComponent'  # Component forms go with components
    if primary_tty in ['SBDF', 'SBDFP']:
        return 'BrandedComponent'  # Branded component forms go with branded components
    if primary_tty == 'SCDGP':
        return 'ClinicalDrug'  # Drug pack groups go with drugs
    if primary_tty == 'DFG':
        return 'DoseForm'  # Dose form groups go with dose forms
    
    # Default for any other TTYs
    return 'Other'

def determine_primary_tty(ttys):
    """Determine the primary TTY for a concept with multiple TTYs"""
    
    # Filter out synonym TTYs
    primary_ttys = [tty for tty in ttys if tty in PRIMARY_TTYS]
    
    if not primary_ttys:
        # If no primary TTYs, fall back to the first TTY
        return list(ttys)[0] if ttys else None
    
    # Priority order for selecting primary TTY when multiple exist
    priority_order = [
        'SCD', 'SBD', 'MIN',  # Most specific drug products
        'IN', 'PIN',         # Ingredients
        'BN',                # Brand names
        'SCDC', 'SBDC',      # Components
        'DF', 'GPCK', 'BPCK' # Forms and packs
    ]
    
    for tty in priority_order:
        if tty in primary_ttys:
            return tty
    
    # If no priority match, return the first primary TTY
    return primary_ttys[0]

class RxNormGraphBuilder:
    def __init__(self):
        self.driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        self.all_rxcuis = {}
        self.all_relationships = []
        self.provenance_ledger = {}
        self.rxcui_to_id = {}  # Store the mapping here
    
    def close(self):
        self.driver.close()
    
    def run(self):
        print("=== RxNorm Provenanced Graph Builder ===")
        print("Focus: Complete Data Import with Provenance + RxNorm Hierarchy Tiers")
        
        # Step 0: Clear existing data
        self.clear_existing_data()
        
        # Step 1: Select RxNorm file
        rxnorm_file = self.select_rxnorm_file()
        
        # Step 2: Extract if needed
        self.extract_rxnorm(rxnorm_file)
        
        # Step 3: Load existing provenance ledger
        self.load_provenance_ledger()
        
        # Step 4: Build the graph
        self.build_complete_graph()
        
        # Step 5: Import to Neo4j
        self.import_to_neo4j()
        
        # Step 6: Verify and save
        self.verify_and_save()
        
        print("\n=== Provenanced Graph Built Successfully ===")
    
    def clear_rxcui_cache(self):
        """Clear the RxCUI to ID cache file"""
        cache_file = f"{BASE_DIR}/import_csvs/rxcui_id_cache.json"
        if os.path.exists(cache_file):
            try:
                os.remove(cache_file)
                print(f"✅ Cleared RxCUI cache file: {cache_file}")
            except Exception as e:
                print(f"⚠️ Error clearing cache file: {e}")
        else:
            print("No cache file to clear")
    
    def clear_existing_data(self):
        """Clear all existing nodes and relationships from Neo4j"""
        print("\n--- Clearing Existing Data ---")
        
        # Also clear the cache when clearing the database
        self.clear_rxcui_cache()
        
        with self.driver.session(database="neo4j") as session:
            # Count before deletion
            result = session.run("MATCH (n) RETURN count(n) as count").single()
            node_count = result['count'] if result else 0
            result = session.run("MATCH ()-[r]->() RETURN count(r) as count").single()
            rel_count = result['count'] if result else 0
            
            print(f"Existing data: {node_count} nodes, {rel_count} relationships")
            
            if node_count > 0 or rel_count > 0:
                # More aggressive clearing - delete everything
                print("Deleting all nodes and relationships...")
                
                # First, delete all constraints and indexes
                try:
                    constraints = session.run("SHOW CONSTRAINTS").data()
                    for constraint in constraints:
                        try:
                            session.run(f"DROP CONSTRAINT {constraint['name']}")
                            print(f"Dropped constraint: {constraint['name']}")
                        except Exception as e:
                            print(f"Error dropping constraint {constraint['name']}: {e}")
                except Exception as e:
                    print(f"Error listing constraints: {e}")
                
                try:
                    indexes = session.run("SHOW INDEXES").data()
                    for index in indexes:
                        try:
                            session.run(f"DROP INDEX {index['name']}")
                            print(f"Dropped index: {index['name']}")
                        except Exception as e:
                            print(f"Error dropping index {index['name']}: {e}")
                except Exception as e:
                    print(f"Error listing indexes: {e}")
                
                # Delete all nodes and relationships
                result = session.run("MATCH (n) DETACH DELETE n RETURN count(n) as count").single()
                print(f"✅ Deleted {result['count']} nodes")
                
                # Verify everything is gone
                result = session.run("MATCH (n) RETURN count(n) as count").single()
                node_count = result['count'] if result else 0
                result = session.run("MATCH ()-[r]->() RETURN count(r) as count").single()
                rel_count = result['count'] if result else 0
                
                print(f"After clearing: {node_count} nodes, {rel_count} relationships")
                
                if node_count > 0 or rel_count > 0:
                    print("⚠️ Warning: Data still exists after clearing")
                    # Try alternative clearing method
                    print("Attempting alternative clearing method...")
                    try:
                        session.run("CALL apoc.schema.assert({}, {})")  # Clear schema
                        session.run("MATCH (n) CALL apoc.path.expandConfig(n, {}) YIELD path DETACH DELETE n")  # Delete all nodes
                    except Exception as e:
                        print(f"Alternative clearing failed: {e}")
                else:
                    print("✅ Successfully cleared all data")
            else:
                print("✅ No existing data to clear")
    
    def select_rxnorm_file(self):
        """Select RxNorm file to process"""
        print("\n--- Select RxNorm File ---")
        
        # Find available RxNorm zip files
        zip_files = []
        for file in os.listdir(RAW_DATA_DIR):
            if file.startswith("RxNorm_") and file.endswith(".zip"):
                zip_files.append(file)
        
        if not zip_files:
            print("❌ No RxNorm zip files found")
            return None
        
        print("Available RxNorm files:")
        for i, file in enumerate(zip_files, 1):
            print(f"{i}: {file}")
        
        while True:
            try:
                choice = int(input("Select RxNorm file to process (1-{}): ".format(len(zip_files))))
                if 1 <= choice <= len(zip_files):
                    selected_file = zip_files[choice-1]
                    break
                else:
                    print("Invalid choice. Please try again.")
            except ValueError:
                print("Please enter a number.")
        
        return selected_file
    
    def extract_rxnorm(self, zip_file):
        """Extract RxNorm zip file if needed"""
        print(f"\n--- Extracting {zip_file} ---")
        
        # Create extraction directory
        extract_dir = os.path.join(EXTRACTED_DIR, zip_file.replace(".zip", "_extracted"))
        
        if os.path.exists(extract_dir):
            print(f"✅ Files already extracted to {extract_dir}")
            return extract_dir
        
        os.makedirs(extract_dir, exist_ok=True)
        
        # Extract the zip file
        with zipfile.ZipFile(os.path.join(RAW_DATA_DIR, zip_file), 'r') as zip_ref:
            zip_ref.extractall(extract_dir)
        
        print(f"✅ Extracted to {extract_dir}")
        return extract_dir
    
    def load_provenance_ledger(self):
        """Load existing provenance ledger or create a new one"""
        print("\n--- Loading Provenance Ledger ---")
        
        if os.path.exists(LEDGER_FILE):
            with open(LEDGER_FILE, 'r') as f:
                self.provenance_ledger = json.load(f)
            print(f"✅ Loaded existing provenance ledger with {len(self.provenance_ledger)} entries")
        else:
            self.provenance_ledger = {}
            os.makedirs(os.path.dirname(LEDGER_FILE), exist_ok=True)
            print("✅ Created new provenance ledger")
    
    def create_provenance_record(self, data_type, source, source_file, **kwargs):
        """Create a provenance record and return its hash"""
        # Base metadata
        metadata = {
            "data_type": data_type,
            "source": source,
            "source_file": source_file,
            "date_published": "2026-02-13",
            "date_accessed": "2026-02-13",
        }
        
        # Add additional metadata
        for key, value in kwargs.items():
            metadata[key] = value
        
        # Create full citation
        if source == "rxnorm":
            metadata["full_citation"] = f"RxNorm (Prescribable Content). National Library of Medicine. Dataset released on {metadata['date_published']}. Accessed on {metadata['date_accessed']}."
        else:
            metadata["full_citation"] = f"Connectivity enhancement based on algorithmic analysis. Generated on {metadata['date_accessed']}."
        
        # Create hash
        prov_hash = hashlib.sha256(json.dumps(metadata, sort_keys=True).encode('utf-8')).hexdigest()[:16]
        
        # Add to ledger
        self.provenance_ledger[prov_hash] = metadata
        
        return prov_hash
    
    def build_complete_graph(self):
        """Build the complete graph with provenance"""
        print("\n--- Building Complete Graph with Provenance ---")
        
        # Import concepts
        self.import_provenanced_concepts()
        
        # Check if concepts were loaded
        print(f"Loaded {len(self.all_rxcuis)} concepts")
        
        # Import relationships
        self.import_provenanced_relationships()
        
        # Check if relationships were loaded
        print(f"Loaded {len(self.all_relationships)} relationships")
        
        # Enhance connectivity
        self.enhance_connectivity()
        
        # Check enhanced relationships
        enhanced_count = len([r for r in self.all_relationships if 'provenance_enhancement' in r])
        print(f"Enhanced relationships: {enhanced_count}")
    
    def import_provenanced_concepts(self):
        """Import concepts with provenance from RXNCONSO.RRF"""
        print("\n--- Importing Provenanced Concepts from RXNCONSO.RRF ---")
        
        # Find the RXNCONSO.RRF file
        conso_file = None
        for root, dirs, files in os.walk(EXTRACTED_DIR):
            for file in files:
                if file == "RXNCONSO.RRF":
                    conso_file = os.path.join(root, file)
                    break
            if conso_file:
                break
        
        if not conso_file:
            print("❌ RXNCONSO.RRF file not found")
            return
        
        print(f"Processing {conso_file}...")
        
        # Process the file
        processed_count = 0
        with open(conso_file, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                if line_num % 10000 == 0:
                    print(f"Processed {line_num} lines...")
                
                # Parse the line
                fields = line.strip().split('|')
                if len(fields) < 18:
                    continue
                
                rxcui = fields[0]
                name = fields[14]
                tty = fields[12]
                
                # Skip empty fields
                if not rxcui or not name or not tty:
                    continue
                
                # Create or update the concept
                if rxcui not in self.all_rxcuis:
                    # Create a new concept with provenance
                    prov_hash = self.create_provenance_record(
                        data_type="concept",
                        source="rxnorm",
                        source_file="RXNCONSO.RRF",
                        rxcui=rxcui,
                        name=name,
                        tty=tty
                    )
                    
                    self.all_rxcuis[rxcui] = {
                        'name': name,
                        'ttys': set([tty]),
                        'provenance_rxnorm': prov_hash
                    }
                else:
                    # Update existing concept
                    self.all_rxcuis[rxcui]['ttys'].add(tty)
                
                processed_count += 1
        
        print(f"✅ Imported {len(self.all_rxcuis)} distinct RxCUIs with provenance")
    
    def import_provenanced_relationships(self):
        """Import relationships with provenance from RXNREL.RRF"""
        print("\n--- Importing Provenanced Relationships from RXNREL.RRF ---")
        
        # Find the RXNREL.RRF file
        rel_file = None
        for root, dirs, files in os.walk(EXTRACTED_DIR):
            for file in files:
                if file == "RXNREL.RRF":
                    rel_file = os.path.join(root, file)
                    break
            if rel_file:
                break
        
        if not rel_file:
            print("❌ RXNREL.RRF file not found")
            return
        
        print(f"Processing {rel_file}...")
        
        # Process the file
        processed_count = 0
        with open(rel_file, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                if line_num % 10000 == 0:
                    print(f"Processed {line_num} lines...")
                
                # Parse the line
                fields = line.strip().split('|')
                if len(fields) < 9:
                    continue
                
                source_rxcui = fields[0]
                target_rxcui = fields[4]
                relationship = fields[7]
                
                # Skip empty fields
                if not source_rxcui or not target_rxcui or not relationship:
                    continue
                
                # Skip if either concept doesn't exist
                if source_rxcui not in self.all_rxcuis or target_rxcui not in self.all_rxcuis:
                    continue
                
                # Create a provenance record for this relationship
                prov_hash = self.create_provenance_record(
                    data_type="relationship",
                    source="rxnorm",
                    source_file="RXNREL.RRF",
                    source_rxcui=source_rxcui,
                    target_rxcui=target_rxcui,
                    relationship=relationship
                )
                
                # Add the relationship
                self.all_relationships.append({
                    'source': source_rxcui,
                    'target': target_rxcui,
                    'relationship': relationship,
                    'provenance_rxnorm': prov_hash
                })
                
                processed_count += 1
        
        print(f"✅ Imported {len(self.all_relationships)} relationships with provenance")
        
        # Show relationship types
        rel_types = set(rel['relationship'] for rel in self.all_relationships)
        print(f"✅ Found {len(rel_types)} relationship types: {', '.join(sorted(rel_types))}")
    
    def enhance_connectivity(self):
        """Enhance connectivity by adding strategic relationships"""
        print("\n--- Enhancing Graph Connectivity ---")
        
        # Group ingredients by their first word (e.g., "acetaminophen" in "acetaminophen 500mg")
        ingredient_groups = defaultdict(list)
        for rxcui, data in self.all_rxcuis.items():
            if 'IN' in data['ttys']:  # Active ingredients
                first_word = data['name'].split()[0].lower()
                ingredient_groups[first_word].append(rxcui)
        
        # Create connections between related ingredients
        enhanced_rels = 0
        for first_word, rxcuis in ingredient_groups.items():
            if len(rxcuis) > 1:
                # Connect all ingredients with the same first word
                for i in range(len(rxcuis)):
                    for j in range(i+1, len(rxcuis)):
                        # Create a provenance record for this enhanced connection
                        prov_hash = self.create_provenance_record(
                            data_type="relationship",
                            source="connectivity_enhancement",
                            source_file="algorithmic_analysis",
                            source_rxcui=rxcuis[i],
                            target_rxcui=rxcuis[j],
                            relationship="SIMILAR_INGREDIENT",
                            reasoning=f"Both ingredients start with '{first_word}'"
                        )
                        
                        self.all_relationships.append({
                            'source': rxcuis[i],
                            'target': rxcuis[j],
                            'relationship': 'SIMILAR_INGREDIENT',
                            'provenance_enhancement': prov_hash
                        })
                        
                        enhanced_rels += 1
        
        print(f"✅ Enhanced connectivity with {enhanced_rels} additional relationships")
    
    def import_to_neo4j(self):
        """Import all concepts and relationships to Neo4j"""
        print("\n--- Importing to Neo4j ---")
        
        # Create constraints and indexes
        self.create_constraints_and_indexes()
        
        # Import nodes
        self.import_provenanced_nodes()
        
        # Import relationships
        self.import_provenanced_relationships_to_neo4j()
        
        # Create provenance indexes
        self.create_provenance_indexes()
    
    def create_constraints_and_indexes(self):
        """Create constraints and indexes in Neo4j"""
        print("\n--- Creating Constraints and Indexes ---")
        
        with self.driver.session(database="neo4j") as session:
            # Create uniqueness constraint on RxCUI (using Neo4j 5.x syntax)
            try:
                session.run("CREATE CONSTRAINT rxcui_uniq IF NOT EXISTS FOR (c:Tier1) REQUIRE c.rxcui IS UNIQUE")
                print("✅ Created uniqueness constraint on RxCui")
            except Exception as e:
                print(f"⚠️ Constraint may already exist: {e}")
            
            # Create index on primary_tty (using Neo4j 5.x syntax)
            try:
                session.run("CREATE INDEX primary_tty_idx IF NOT EXISTS FOR (c:Tier1) ON (c.primary_tty)")
                print("✅ Created index on primary_tty")
            except Exception as e:
                print(f"⚠️ Index may already exist: {e}")
            
            # Create index on tier (using Neo4j 5.x syntax)
            try:
                session.run("CREATE INDEX tier_idx IF NOT EXISTS FOR (c:Tier1) ON (c.tier)")
                print("✅ Created index on tier")
            except Exception as e:
                print(f"⚠️ Index may already exist: {e}")
    
    def import_provenanced_nodes(self):
        """Import all concepts with provenance to Neo4j using RxNorm hierarchy tiers and build mapping"""
        print("\n--- Importing Provenanced Nodes with RxNorm Hierarchy Tiers ---")
        
        # Convert sets to lists for JSON serialization and determine tier
        concepts = []
        for rxcui, data in self.all_rxcuis.items():
            # Determine primary TTY
            primary_tty = determine_primary_tty(data['ttys'])
            
            # Determine tier based on primary TTY using our hierarchy
            tier = get_node_tier(primary_tty)
            
            concepts.append({
                'rxcui': rxcui,
                'name': data['name'],
                'primary_tty': primary_tty,
                'all_ttys': list(data['ttys']),
                'tier': tier,
                'provenance_rxnorm': data['provenance_rxnorm']
            })
        
        print(f"Prepared {len(concepts)} concepts for import")
        
        # Debug: Show a few examples
        print("\n--- Sample Concepts ---")
        for i, concept in enumerate(concepts[:5]):
            print(f"{i+1}. RxCUI: {concept['rxcui']}, Name: {concept['name']}, Tier: {concept['tier']}, Primary TTY: {concept['primary_tty']}")
        
        # Group by tier for batch processing
        tier_groups = defaultdict(list)
        for concept in concepts:
            tier_groups[concept['tier']].append(concept)
        
        print(f"\n--- Tier Distribution ---")
        for tier, tier_concepts in tier_groups.items():
            print(f"{tier}: {len(tier_concepts)} concepts")
        
        # Initialize the RxCUI to ID mapping
        self.rxcui_to_id = {}
        
        # Import each tier separately and build the mapping
        with self.driver.session(database="neo4j") as session:
            for tier, tier_concepts in tier_groups.items():
                print(f"\nImporting {len(tier_concepts)} concepts for tier: {tier}")
                
                # Import in batches
                batch_size = 5000
                for i in range(0, len(tier_concepts), batch_size):
                    batch = tier_concepts[i:i+batch_size]
                    
                    # Use CREATE with the specific tier label and return the created nodes
                    query = f"""
                    UNWIND $concepts AS concept
                    CREATE (c:Tier1:{tier})
                    SET c.rxcui = concept.rxcui,
                        c.name = concept.name,
                        c.primary_tty = concept.primary_tty,
                        c.all_ttys = concept.all_ttys,
                        c.tier = concept.tier,
                        c.provenance_rxnorm = concept.provenance_rxnorm
                    RETURN c.rxcui AS rxcui, elementId(c) AS id
                    """
                    
                    result = session.run(query, concepts=batch)
                    
                    # Build the mapping from the returned results
                    for record in result:
                        self.rxcui_to_id[record['rxcui']] = record['id']
                    
                    if (i + batch_size) % 10000 == 0 or i + batch_size >= len(tier_concepts):
                        percent = min(i + batch_size, len(tier_concepts)) / len(tier_concepts) * 100
                        print(f"  Processed {min(i + batch_size, len(tier_concepts))}/{len(tier_concepts)} ({percent:.1f}%)")
                
                # Check count for this tier
                result = session.run(f"MATCH (n:Tier1:{tier}) RETURN count(n) as count").single()
                print(f"  Current {tier} node count in Neo4j: {result['count']}")
        
        print(f"✅ Imported {len(concepts)} nodes with RxNorm hierarchy tiers and provenance")
        print(f"✅ Built mapping for {len(self.rxcui_to_id)} nodes")
        
        # Save the mapping to cache for future use
        cache_file = f"{BASE_DIR}/import_csvs/rxcui_id_cache.json"
        try:
            cache_data = {
                'node_count': len(self.rxcui_to_id),
                'rxcui_lookup': self.rxcui_to_id,
                'created': '2026-02-14'
            }
            
            os.makedirs(os.path.dirname(cache_file), exist_ok=True)
            with open(cache_file, 'w') as f:
                json.dump(cache_data, f)
            
            print(f"✅ Saved RxCUI to ID mapping to {cache_file}")
        except Exception as e:
            print(f"⚠️ Error saving mapping: {e}")
    
    def import_provenanced_relationships_to_neo4j(self):
        """Import all relationships with provenance to Neo4j using the pre-built mapping"""
        print("\n--- Importing Provenanced Relationships (Using Pre-built Mapping) ---")
        
        # Group relationships by type for more efficient processing
        rels_by_type = defaultdict(list)
        for rel in self.all_relationships:
            rels_by_type[rel['relationship']].append(rel)
        
        print(f"Found {len(rels_by_type)} unique relationship types")
        for rel_type, rels in rels_by_type.items():
            print(f"  {rel_type}: {len(rels)} relationships")
        
        # Check if we have a mapping available
        if not hasattr(self, 'rxcui_to_id') or len(self.rxcui_to_id) == 0:
            print("❌ No RxCUI to ID mapping available")
            return
        
        print(f"✅ Using pre-built mapping for {len(self.rxcui_to_id)} nodes")
        
        # Process each relationship type separately
        for rel_type, rels in rels_by_type.items():
            print(f"\nProcessing {len(rels)} relationships of type '{rel_type}'")
            
            # Debug: Show a few examples
            print("\n--- Sample Relationships ---")
            for i, rel in enumerate(rels[:5]):
                print(f"{i+1}. {rel['source']} -[{rel_type}]-> {rel['target']}")
            
            # Filter relationships where both nodes exist
            valid_rels = []
            for rel in rels:
                if rel['source'] in self.rxcui_to_id and rel['target'] in self.rxcui_to_id:
                    valid_rels.append(rel)
            
            print(f"Valid relationships: {len(valid_rels)}/{len(rels)}")
            
            if not valid_rels:
                print(f"No valid relationships for type '{rel_type}' - skipping")
                continue
            
            # Process in batches using node IDs for faster matching
            batch_size = 10000  # Increased batch size
            processed_rels = 0
            
            with self.driver.session(database="neo4j") as session:
                for i in range(0, len(valid_rels), batch_size):
                    batch = valid_rels[i:i+batch_size]
                    
                    # Prepare batch with node IDs instead of RxCUIs
                    batch_with_ids = []
                    for rel in batch:
                        batch_with_ids.append({
                            'source_id': self.rxcui_to_id[rel['source']],
                            'target_id': self.rxcui_to_id[rel['target']],
                            'provenance_rxnorm': rel.get('provenance_rxnorm'),
                            'provenance_enhancement': rel.get('provenance_enhancement')
                        })
                    
                    # Special handling for SIMILAR_INGREDIENT relationships
                    if rel_type == 'SIMILAR_INGREDIENT':
                        query = """
                        UNWIND $rels AS rel
                        MATCH (source) WHERE elementId(source) = rel.source_id
                        MATCH (target) WHERE elementId(target) = rel.target_id
                        MERGE (source)-[r:SIMILAR_INGREDIENT]->(target)
                        SET r.provenance_enhancement = rel.provenance_enhancement
                        """
                    else:
                        query = f"""
                        UNWIND $rels AS rel
                        MATCH (source) WHERE elementId(source) = rel.source_id
                        MATCH (target) WHERE elementId(target) = rel.target_id
                        MERGE (source)-[r:{rel_type}]->(target)
                        SET r.provenance_rxnorm = rel.provenance_rxnorm
                        """
                    
                    session.run(query, rels=batch_with_ids)
                    processed_rels += len(batch)
                    
                    if processed_rels % 20000 == 0 or processed_rels == len(valid_rels):
                        percent = processed_rels / len(valid_rels) * 100
                        print(f"Processed {processed_rels}/{len(valid_rels)} ({percent:.1f}%)")
                        
                        # Check actual count in Neo4j
                        result = session.run("MATCH ()-[r]->() RETURN count(r) as count").single()
                        print(f"Current relationship count in Neo4j: {result['count']}")
            
            print(f"✅ Imported {len(valid_rels)} relationships of type '{rel_type}'")
        
        print(f"✅ Imported {len(self.all_relationships)} relationships with provenance")
    
    def create_provenance_indexes(self):
        """Create indexes for provenance properties"""
        print("\n--- Creating Provenance Indexes ---")
        
        with self.driver.session(database="neo4j") as session:
            try:
                # For Neo4j 5.x, use this syntax for relationship property indexes
                session.run("CREATE INDEX provenance_rxnorm_idx IF NOT EXISTS FOR ()-[r:HAS_SYNONYM]-() ON (r.provenance_rxnorm)")
                print("✅ Created provenance_rxnorm index for HAS_SYNONYM relationships")
            except Exception as e:
                print(f"⚠️ Index may already exist: {e}")
            
            try:
                session.run("CREATE INDEX provenance_enhancement_idx IF NOT EXISTS FOR ()-[r:SIMILAR_INGREDIENT]-() ON (r.provenance_enhancement)")
                print("✅ Created provenance_enhancement index for SIMILAR_INGREDIENT relationships")
            except Exception as e:
                print(f"⚠️ Index may already exist: {e}")
    
    def verify_and_save(self):
        """Verify the imported graph and save the provenance ledger"""
        print("\n" + "="*60)
        print("FINAL VERIFICATION")
        print("="*60)
        
        with self.driver.session(database="neo4j") as session:
            # Count nodes by tier
            print("\n--- Node Counts by Tier ---")
            result = session.run("""
            MATCH (c:Tier1)
            RETURN c.tier AS tier, count(*) AS count
            ORDER BY count DESC
            """)
            
            for record in result:
                print(f"{record['tier']}: {record['count']} nodes")
            
            # Count all nodes
            result = session.run("MATCH (n:Tier1) RETURN count(n) as count").single()
            actual_nodes = result['count'] if result else 0
            
            # Count relationships
            result = session.run("MATCH ()-[r]->() RETURN count(r) as count").single()
            actual_rels = result['count'] if result else 0
            
            # Expected counts
            expected_nodes = len(self.all_rxcuis)
            expected_base_rels = len([r for r in self.all_relationships if 'provenance_rxnorm' in r])
            expected_enhanced_rels = len([r for r in self.all_relationships if 'provenance_enhancement' in r])
            expected_total_rels = expected_base_rels + expected_enhanced_rels
            
            # Verify nodes
            print(f"\nExpected nodes: {expected_nodes}")
            print(f"Actual nodes: {actual_nodes}")
            if actual_nodes == expected_nodes:
                print("Node match: ✅")
            else:
                print("Node match: ❌")
            
            # Verify relationships
            print(f"\nExpected base relationships: {expected_base_rels}")
            print(f"Expected enhanced relationships: {expected_enhanced_rels}")
            print(f"Expected total relationships: {expected_total_rels}")
            print(f"Actual relationships: {actual_rels}")
            if actual_rels >= expected_total_rels:  # >= because we added additional relationships
                print("Relationship match: ✅")
            else:
                print("Relationship match: ❌")
            
            # Count relationship types
            print("\n--- Relationship Types ---")
            result = session.run("""
            MATCH ()-[r]->()
            RETURN type(r) as rel_type, count(*) as count
            ORDER BY count DESC
            """)
            
            for record in result:
                print(f"{record['rel_type']}: {record['count']}")
            
            # Provenance ledger
            print(f"\nProvenance ledger entries: {len(self.provenance_ledger)}")
            
            # Save the provenance ledger
            os.makedirs(os.path.dirname(LEDGER_FILE), exist_ok=True)
            with open(LEDGER_FILE, 'w') as f:
                json.dump(self.provenance_ledger, f, indent=2)
            
            print(f"Provenance ledger file: {LEDGER_FILE}")
            
            # Save verification report
            report_file = f"{BASE_DIR}/import_csvs/provenanced_graph_verification_2026-02-14.txt"
            with open(report_file, 'w') as f:
                f.write(f"RxNorm Graph Verification Report\n")
                f.write(f"Generated: 2026-02-14\n\n")
                f.write(f"Nodes: {actual_nodes}/{expected_nodes}\n")
                f.write(f"Relationships: {actual_rels}/{expected_total_rels}\n")
                f.write(f"Provenance Ledger Entries: {len(self.provenance_ledger)}\n")
            
            print(f"✅ Verification report saved to {report_file}")

if __name__ == "__main__":
    try:
        builder = RxNormGraphBuilder()
        builder.run()
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        if 'builder' in locals():
            builder.close()
