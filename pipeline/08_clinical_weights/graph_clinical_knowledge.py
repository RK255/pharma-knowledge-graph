"""
Graph-Native Clinical Knowledge System
Converts JSON weights to Neo4j nodes and relationships
"""

from neo4j import GraphDatabase
import json
from datetime import datetime
from typing import Dict, List, Optional

NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "Nani*48301"

class ClinicalKnowledgeGraph:
    """Manage clinical knowledge as graph nodes and relationships."""
    
    def __init__(self):
        self.driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    
    def close(self):
        self.driver.close()
    
    def create_schema(self):
        """Create indexes for clinical knowledge nodes."""
        with self.driver.session() as session:
            # Expert indexes
            session.run("CREATE INDEX IF NOT EXISTS FOR (e:Expert) ON (e.provenance_hash)")
            session.run("CREATE INDEX IF NOT EXISTS FOR (e:Expert) ON (e.name)")
            
            # Evidence indexes
            session.run("CREATE INDEX IF NOT EXISTS FOR (e:Evidence) ON (e.evidence_id)")
            
            # Indication indexes
            session.run("CREATE INDEX IF NOT EXISTS FOR (i:Indication) ON (i.name)")
            
            # ClinicalWeight indexes
            session.run("CREATE INDEX IF NOT EXISTS FOR (w:ClinicalWeight) ON (w.weight_id)")
            session.run("CREATE INDEX IF NOT EXISTS FOR (w:ClinicalWeight) ON (w.weight)")
            
            print("✅ Schema created")
    
    def create_expert(self, name: str, credentials: str, license_info: str, 
                      experience: str = None, specialization: str = None) -> str:
        """Create or update an Expert node. Returns the provenance hash."""
        provenance_hash = self._compute_hash(f"{name}:{credentials}:{license_info}")
        
        with self.driver.session() as session:
            session.run("""
                MERGE (e:Expert {provenance_hash: $hash})
                SET e.name = $name,
                    e.credentials = $credentials,
                    e.license = $license,
                    e.experience = $experience,
                    e.specialization = $specialization,
                    e.last_updated = datetime()
            """, hash=provenance_hash, name=name, credentials=credentials, 
                 license=license_info, experience=experience, specialization=specialization)
            
            return provenance_hash
    
    def create_evidence(self, evidence_id: str, name: str, evidence_type: str, 
                        year: int = None, url: str = None) -> Dict:
        """Create or update an Evidence node (clinical trial, guideline, etc.)."""
        with self.driver.session() as session:
            result = session.run("""
                MERGE (e:Evidence {evidence_id: $evidence_id})
                SET e.name = $name,
                    e.type = $evidence_type,
                    e.year = $year,
                    e.url = $url,
                    e.last_updated = datetime()
                RETURN e
            """, evidence_id=evidence_id, name=name, evidence_type=evidence_type, 
                 year=year, url=url)
            
            record = result.single()
            return dict(record["e"]) if record else None
    
    def create_indication(self, name: str, display_name: str, description: str = None,
                          first_line: str = None, guidelines: str = None) -> Dict:
        """Create or update an Indication node."""
        with self.driver.session() as session:
            result = session.run("""
                MERGE (i:Indication {name: $name})
                SET i.display_name = $display_name,
                    i.description = $description,
                    i.first_line = $first_line,
                    i.guidelines = $guidelines,
                    i.last_updated = datetime()
                RETURN i
            """, name=name, display_name=display_name, description=description,
                 first_line=first_line, guidelines=guidelines)
            
            record = result.single()
            return dict(record["i"]) if record else None
    
    def create_clinical_weight(self, drug_ingredient: str, expert_hash: str,
                                indication: str, weight: int, rationale: str,
                                evidence_id: str = None, clinical_note: str = None) -> str:
        """Create a ClinicalWeight node with relationships. Returns weight_id."""
        
        weight_id = self._compute_hash(f"{drug_ingredient}:{indication}:{expert_hash}")
        
        with self.driver.session() as session:
            # Check if ingredient exists using toLower
            check = session.run("""
                MATCH (d:Ingredient)
                WHERE toLower(d.name) = toLower($drug)
                RETURN d.name as name
            """, drug=drug_ingredient)
            
            if not check.single():
                print(f"   ⚠️  Ingredient '{drug_ingredient}' not found in graph, skipping...")
                return None
            
            # Create the weight node and connect everything
            session.run("""
                // Find or create the weight node
                MERGE (w:ClinicalWeight {weight_id: $weight_id})
                SET w.weight = $weight,
                    w.rationale = $rationale,
                    w.clinical_note = $clinical_note,
                    w.indication = $indication,
                    w.last_updated = datetime()
                
                // Connect to Expert
                WITH w
                MATCH (e:Expert {provenance_hash: $expert_hash})
                MERGE (e)-[r1:CURATED]->(w)
                SET r1.date = date()
                
                // Connect to Drug Ingredient (using toLower for matching)
                WITH w
                MATCH (d:Ingredient)
                WHERE toLower(d.name) = toLower($drug_ingredient)
                MERGE (w)-[r3:WEIGHTS]->(d)
                SET r3.weight = $weight
                
                // Optionally connect to Evidence
                WITH w
                OPTIONAL MATCH (ev:Evidence {evidence_id: $evidence_id})
                WITH w, ev
                WHERE ev IS NOT NULL
                MERGE (w)-[r4:BASED_ON]->(ev)
            """, weight_id=weight_id, weight=weight, rationale=rationale,
                 clinical_note=clinical_note, expert_hash=expert_hash,
                 indication=indication, drug_ingredient=drug_ingredient,
                 evidence_id=evidence_id)
            
            return weight_id
    
    def get_drug_recommendations(self, drug_name: str, indication: str = None) -> List[Dict]:
        """Get clinically weighted recommendations for a drug from the graph."""
        with self.driver.session() as session:
            if indication:
                result = session.run("""
                    MATCH (drug:Ingredient)
                    WHERE toLower(drug.name) = toLower($drug_name)
                    MATCH (drug)-[:BELONGS_TO]->(class:PharmacologicalClass)<-[:BELONGS_TO]-(other:Ingredient)
                    WHERE other <> drug
                    OPTIONAL MATCH (weight:ClinicalWeight)-[:WEIGHTS]->(other)
                    WHERE weight.indication = $indication
                    OPTIONAL MATCH (expert:Expert)-[:CURATED]->(weight)
                    OPTIONAL MATCH (weight)-[:BASED_ON]->(evidence:Evidence)
                    WITH other, class, weight, expert, evidence
                    WHERE weight IS NOT NULL
                    RETURN 
                        other.name as ingredient_name,
                        class.name as shared_class,
                        weight.weight as clinical_weight,
                        weight.rationale as rationale,
                        weight.clinical_note as clinical_note,
                        $indication as indication,
                        expert.name as curator_name,
                        expert.credentials as curator_credentials,
                        evidence.name as evidence_name,
                        'expert' as weight_source
                    ORDER BY weight.weight DESC
                """, drug_name=drug_name, indication=indication)
            else:
                result = session.run("""
                    MATCH (drug:Ingredient)
                    WHERE toLower(drug.name) = toLower($drug_name)
                    MATCH (drug)-[:BELONGS_TO]->(class:PharmacologicalClass)<-[:BELONGS_TO]-(other:Ingredient)
                    WHERE other <> drug
                    OPTIONAL MATCH (weight:ClinicalWeight)-[:WEIGHTS]->(other)
                    WHERE weight.indication = 'default'
                    OPTIONAL MATCH (expert:Expert)-[:CURATED]->(weight)
                    WITH other, class, weight, expert
                    WHERE weight IS NOT NULL
                    RETURN 
                        other.name as ingredient_name,
                        class.name as shared_class,
                        weight.weight as clinical_weight,
                        weight.rationale as rationale,
                        weight.clinical_note as clinical_note,
                        null as indication,
                        expert.name as curator_name,
                        expert.credentials as curator_credentials,
                        null as evidence_name,
                        'expert' as weight_source
                    ORDER BY weight.weight DESC
                """, drug_name=drug_name)
            
            return [dict(record) for record in result]
    
    def migrate_from_json(self, json_path: str):
        """Migrate clinical weights from JSON file to graph."""
        with open(json_path, 'r') as f:
            data = json.load(f)
        
        # Create expert - handle nested curator object
        curator_data = data.get('curator', {})
        if isinstance(curator_data, dict):
            curator_name = curator_data.get('name', 'Unknown')
            credentials = curator_data.get('credentials', '')
            license_info = curator_data.get('license', '')
            experience = curator_data.get('experience')
            specialization = curator_data.get('specialization')
        else:
            curator_name = curator_data
            credentials = data.get('credentials', '')
            license_info = data.get('license', '')
            experience = None
            specialization = None
        
        expert_hash = self.create_expert(
            name=curator_name,
            credentials=credentials,
            license_info=license_info,
            experience=experience,
            specialization=specialization
        )
        print(f"✅ Created Expert: {curator_name}, {credentials}")
        
        # Create indications from disease_states
        disease_states = data.get('disease_states', {})
        for ind_name, ind_data in disease_states.items():
            self.create_indication(
                name=ind_name,
                display_name=ind_data.get('name', ind_name),
                description=ind_data.get('description'),
                first_line=ind_data.get('first_line'),
                guidelines=ind_data.get('guidelines')
            )
        print(f"✅ Created {len(disease_states)} Indications")
        
        # Create common evidence sources
        evidence_sources = {
            'ACC_AHA_2018': ('ACC/AHA 2018 Cholesterol Guidelines', 'guideline', 2018),
            'IMPROVE_IT': ('IMPROVE-IT Trial', 'clinical_trial', 2015),
            'AIM_HIGH': ('AIM-HIGH Trial', 'clinical_trial', 2011),
            'HPS2_THRIVE': ('HPS2-THRIVE Trial', 'clinical_trial', 2014),
        }
        
        for ev_id, (name, ev_type, year) in evidence_sources.items():
            self.create_evidence(ev_id, name, ev_type, year)
        print(f"✅ Created {len(evidence_sources)} Evidence sources")
        
        # Create clinical weights for each drug
        drugs = data.get('drugs', {})
        count = 0
        skipped = 0
        
        for drug_name, drug_data in drugs.items():
            # Default weight (no indication)
            default = drug_data.get('default', {})
            if default:
                weight_id = self.create_clinical_weight(
                    drug_ingredient=drug_name,
                    expert_hash=expert_hash,
                    indication='default',
                    weight=default.get('weight', 50),
                    rationale=default.get('rationale'),
                    evidence_id=self._parse_evidence(default.get('evidence')),
                    clinical_note=drug_data.get('clinical_note')
                )
                if weight_id:
                    count += 1
                else:
                    skipped += 1
            
            # Indication-specific weights
            for ind_name, ind_weight in drug_data.get('indications', {}).items():
                weight_id = self.create_clinical_weight(
                    drug_ingredient=drug_name,
                    expert_hash=expert_hash,
                    indication=ind_name,
                    weight=ind_weight.get('weight', 50),
                    rationale=ind_weight.get('rationale'),
                    evidence_id=self._parse_evidence(ind_weight.get('evidence')),
                    clinical_note=drug_data.get('clinical_note')
                )
                if weight_id:
                    count += 1
                else:
                    skipped += 1
        
        print(f"✅ Created {count} ClinicalWeight nodes")
        if skipped > 0:
            print(f"   ⚠️  Skipped {skipped} weights (ingredients not found in graph)")
    
    def verify_graph(self):
        """Verify the graph structure."""
        with self.driver.session() as session:
            print("\n=== Graph Verification ===")
            
            # Count nodes
            experts = session.run("MATCH (e:Expert) RETURN count(e) as count").single()['count']
            indications = session.run("MATCH (i:Indication) RETURN count(i) as count").single()['count']
            weights = session.run("MATCH (w:ClinicalWeight) RETURN count(w) as count").single()['count']
            evidence = session.run("MATCH (e:Evidence) RETURN count(e) as count").single()['count']
            
            print(f"Experts: {experts}")
            print(f"Indications: {indications}")
            print(f"Evidence: {evidence}")
            print(f"ClinicalWeights: {weights}")
            
            # Show sample relationships
            print("\nSample ClinicalWeight relationships:")
            result = session.run("""
                MATCH (e:Expert)-[:CURATED]->(w:ClinicalWeight)-[:WEIGHTS]->(i:Ingredient)
                OPTIONAL MATCH (w)-[:BASED_ON]->(ev:Evidence)
                RETURN e.name as expert, w.weight as weight, w.indication as indication,
                       i.name as ingredient, ev.name as evidence
                LIMIT 5
            """)
            
            for r in result:
                print(f"  {r['expert']} -> {r['ingredient']}: {r['weight']} ({r['indication']})")
                if r['evidence']:
                    print(f"    Evidence: {r['evidence']}")
    
    def _compute_hash(self, input_str: str) -> str:
        """Compute a short hash for provenance."""
        import hashlib
        return hashlib.sha256(input_str.encode()).hexdigest()[:16]
    
    def _parse_evidence(self, evidence_str: str) -> Optional[str]:
        """Parse evidence string to evidence_id."""
        if not evidence_str:
            return None
        
        evidence_str = evidence_str.upper()
        if 'ACC' in evidence_str or 'AHA' in evidence_str:
            return 'ACC_AHA_2018'
        elif 'IMPROVE' in evidence_str:
            return 'IMPROVE_IT'
        elif 'AIM' in evidence_str:
            return 'AIM_HIGH'
        elif 'THRIVE' in evidence_str:
            return 'HPS2_THRIVE'
        return None


def main():
    """Run migration."""
    kg = ClinicalKnowledgeGraph()
    
    print("=" * 60)
    print("Clinical Knowledge Graph Migration")
    print("=" * 60)
    
    # Create schema
    print("\n1. Creating schema...")
    kg.create_schema()
    
    # Migrate from JSON
    print("\n2. Migrating clinical weights...")
    kg.migrate_from_json('/mnt/fast_raid/server_projects/Geo/graph_workshop/pharma-backend/clinical_weights.json')
    
    # Verify
    kg.verify_graph()
    
    kg.close()
    print("\n✅ Migration complete!")


if __name__ == "__main__":
    main()
