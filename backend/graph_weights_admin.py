"""
Graph-Based Clinical Weights Admin System
==========================================
Provides atomic updates to Neo4j graph with JSON backup for audit trail.
Admin UI can push updates that immediately update the graph.
"""

from neo4j import GraphDatabase
from datetime import datetime
from typing import Dict, Optional, List
import json
import hashlib
import os

NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "Nani*48301"
WEIGHTS_FILE = "/mnt/fast_raid/server_projects/Geo/graph_workshop/pharma-backend/clinical_weights.json"

DEFAULT_CURATOR = {
    "name": "Kevin G",
    "credentials": "PharmD",
    "license": "WA DOH RPH License #PH61629288",
    "experience": "20+ years clinical pharmacy practice",
    "specialization": "Ambulatory care, chronic disease management"
}


class GraphWeightsAdmin:
    """
    Admin interface for clinical weights stored in Neo4j.
    
    Architecture:
    ┌─────────────────────────────────────────────────────────────┐
    │                    ADMIN UPDATE FLOW                        │
    ├─────────────────────────────────────────────────────────────┤
    │                                                             │
    │  Admin UI ──► API Endpoint ──► update_weight()             │
    │                                    │                        │
    │                                    ├──► 1. Update Neo4j     │
    │                                    │    (live queries)      │
    │                                    │                        │
    │                                    └──► 2. Update JSON      │
    │                                         (backup/audit)      │
    │                                                             │
    │  Query Flow:                                                │
    │  LLM ──► get_weight() ──► Neo4j (direct, no JSON)          │
    │                                                             │
    └─────────────────────────────────────────────────────────────┘
    """
    
    def __init__(self):
        self.driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    
    def close(self):
        self.driver.close()
    
    # ==================== READ OPERATIONS ====================
    
    def get_weight(self, ingredient: str, indication: str = None) -> Optional[Dict]:
        """Get clinical weight for an ingredient from the graph."""
        with self.driver.session() as session:
            if indication:
                result = session.run("""
                    MATCH (w:ClinicalWeight)-[:WEIGHTS]->(i:Ingredient)
                    WHERE toLower(i.name) = toLower($ingredient)
                      AND w.indication = $indication
                    OPTIONAL MATCH (e:Expert)-[:CURATED]->(w)
                    OPTIONAL MATCH (w)-[:BASED_ON]->(ev:Evidence)
                    RETURN w.weight as weight, w.rationale as rationale,
                           w.clinical_note as clinical_note, w.updated_at as updated_at,
                           e.name as curator, e.credentials as curator_credentials,
                           e.license as curator_license, e.provenance_hash as curator_hash,
                           ev.name as evidence, ev.evidence_id as evidence_id
                """, ingredient=ingredient, indication=indication)
            else:
                result = session.run("""
                    MATCH (w:ClinicalWeight)-[:WEIGHTS]->(i:Ingredient)
                    WHERE toLower(i.name) = toLower($ingredient)
                      AND w.indication = 'default'
                    OPTIONAL MATCH (e:Expert)-[:CURATED]->(w)
                    OPTIONAL MATCH (w)-[:BASED_ON]->(ev:Evidence)
                    RETURN w.weight as weight, w.rationale as rationale,
                           w.clinical_note as clinical_note, w.updated_at as updated_at,
                           e.name as curator, e.credentials as curator_credentials,
                           e.license as curator_license, e.provenance_hash as curator_hash,
                           ev.name as evidence, ev.evidence_id as evidence_id
                """, ingredient=ingredient)
            
            record = result.single()
            if record and record['weight'] is not None:
                return {
                    'weight': record['weight'],
                    'rationale': record['rationale'],
                    'clinical_note': record['clinical_note'],
                    'updated_at': record['updated_at'],
                    'curator': record['curator'],
                    'curator_credentials': record['curator_credentials'],
                    'curator_license': record['curator_license'],
                    'curator_hash': record['curator_hash'],
                    'evidence': record['evidence'],
                    'evidence_id': record['evidence_id'],
                    'source': f'expert:graph:{indication}' if indication else 'expert:graph:default'
                }
            return None
    
    def get_all_weights_for_ingredient(self, ingredient: str) -> List[Dict]:
        """Get all weights for an ingredient across all indications."""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (w:ClinicalWeight)-[:WEIGHTS]->(i:Ingredient)
                WHERE toLower(i.name) = toLower($ingredient)
                OPTIONAL MATCH (e:Expert)-[:CURATED]->(w)
                OPTIONAL MATCH (w)-[:BASED_ON]->(ev:Evidence)
                RETURN w.indication as indication, w.weight as weight,
                       w.rationale as rationale, w.clinical_note as clinical_note,
                       w.updated_at as updated_at, w.weight_id as weight_id,
                       e.name as curator, e.credentials as curator_credentials,
                       e.license as curator_license, ev.name as evidence
                ORDER BY w.weight DESC
            """, ingredient=ingredient)
            
            return [dict(record) for record in result]
    
    def list_all_weighted_ingredients(self) -> List[Dict]:
        """List all ingredients with clinical weights."""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (i:Ingredient)<-[:WEIGHTS]-(w:ClinicalWeight)
                WITH i, count(w) as weight_count, collect(DISTINCT w.indication) as indications
                RETURN i.name as ingredient, weight_count, indications
                ORDER BY i.name
            """)
            
            return [dict(record) for record in result]
    
    # ==================== WRITE OPERATIONS (ATOMIC) ====================
    
    def update_weight(self, ingredient: str, indication: str, weight: int,
                      rationale: str = None, evidence_id: str = None,
                      clinical_note: str = None, curator: Dict = None) -> Dict:
        """
        Atomically update a clinical weight in the graph.
        
        This is the main admin update function:
        1. Validates the ingredient exists
        2. Creates/updates the weight node
        3. Links to expert (creates if needed)
        4. Links to evidence (if provided)
        5. Updates JSON backup for audit trail
        6. Returns the updated weight with full provenance
        """
        # Use default curator if not provided
        if curator is None:
            curator = DEFAULT_CURATOR
        
        curator_hash = self._compute_hash(f"{curator['name']}:{curator['credentials']}:{curator['license']}")
        weight_id = self._compute_hash(f"{ingredient}:{indication}:{curator_hash}")
        
        with self.driver.session() as session:
            # Start transaction - all or nothing
            tx = session.begin_transaction()
            
            try:
                # 1. Verify ingredient exists
                check = tx.run("""
                    MATCH (i:Ingredient)
                    WHERE toLower(i.name) = toLower($ingredient)
                    RETURN i.name as name
                """, ingredient=ingredient)
                
                if not check.single():
                    tx.rollback()
                    return {"success": False, "error": f"Ingredient '{ingredient}' not found in graph"}
                
                # 2. Create or update Expert
                tx.run("""
                    MERGE (e:Expert {provenance_hash: $hash})
                    SET e.name = $name,
                        e.credentials = $credentials,
                        e.license = $license,
                        e.experience = $experience,
                        e.specialization = $specialization,
                        e.updated_at = datetime()
                """, hash=curator_hash, 
                     name=curator.get('name'),
                     credentials=curator.get('credentials'),
                     license=curator.get('license'),
                     experience=curator.get('experience'),
                     specialization=curator.get('specialization'))
                
                # 3. Create or update ClinicalWeight
                tx.run("""
                    MATCH (i:Ingredient)
                    WHERE toLower(i.name) = toLower($ingredient)
                    MERGE (w:ClinicalWeight {weight_id: $weight_id})
                    SET w.weight = $weight,
                        w.rationale = $rationale,
                        w.clinical_note = $clinical_note,
                        w.indication = $indication,
                        w.updated_at = datetime()
                    WITH w, i
                    MERGE (w)-[:WEIGHTS]->(i)
                """, weight_id=weight_id, ingredient=ingredient, indication=indication,
                     weight=weight, rationale=rationale, clinical_note=clinical_note)
                
                # 4. Link Expert to Weight
                tx.run("""
                    MATCH (e:Expert {provenance_hash: $hash})
                    MATCH (w:ClinicalWeight {weight_id: $weight_id})
                    MERGE (e)-[r:CURATED]->(w)
                    SET r.date = date()
                """, hash=curator_hash, weight_id=weight_id)
                
                # 5. Link Evidence if provided
                if evidence_id:
                    tx.run("""
                        MATCH (w:ClinicalWeight {weight_id: $weight_id})
                        MATCH (ev:Evidence {evidence_id: $evidence_id})
                        MERGE (w)-[:BASED_ON]->(ev)
                    """, weight_id=weight_id, evidence_id=evidence_id)
                
                # Commit transaction
                tx.commit()
                
                # 6. Update JSON backup (for audit trail)
                self._update_json_backup(ingredient, indication, weight, rationale, evidence_id, clinical_note, curator)
                
                return {
                    "success": True,
                    "weight_id": weight_id,
                    "ingredient": ingredient,
                    "indication": indication,
                    "weight": weight,
                    "rationale": rationale,
                    "curator": curator['name'],
                    "updated_at": datetime.now().isoformat()
                }
                
            except Exception as e:
                tx.rollback()
                return {"success": False, "error": str(e)}
    
    def delete_weight(self, ingredient: str, indication: str) -> Dict:
        """Delete a clinical weight from the graph."""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (w:ClinicalWeight)-[:WEIGHTS]->(i:Ingredient)
                WHERE toLower(i.name) = toLower($ingredient)
                  AND w.indication = $indication
                DETACH DELETE w
                RETURN count(w) as deleted
            """, ingredient=ingredient, indication=indication)
            
            deleted = result.single()['deleted']
            
            if deleted > 0:
                # Also update JSON backup
                self._delete_from_json_backup(ingredient, indication)
                return {"success": True, "deleted": deleted}
            
            return {"success": False, "error": "Weight not found"}
    
    # ==================== EVIDENCE MANAGEMENT ====================
    
    def add_evidence(self, evidence_id: str, name: str, evidence_type: str,
                     year: int = None, url: str = None) -> Dict:
        """Add a new evidence source."""
        with self.driver.session() as session:
            result = session.run("""
                MERGE (e:Evidence {evidence_id: $evidence_id})
                SET e.name = $name,
                    e.type = $evidence_type,
                    e.year = $year,
                    e.url = $url,
                    e.updated_at = datetime()
                RETURN e
            """, evidence_id=evidence_id, name=name, evidence_type=evidence_type,
                 year=year, url=url)
            
            if result.single():
                return {"success": True, "evidence_id": evidence_id}
            return {"success": False, "error": "Failed to create evidence"}
    
    def list_evidence(self) -> List[Dict]:
        """List all evidence sources."""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (e:Evidence)
                OPTIONAL MATCH (e)<-[:BASED_ON]-(w:ClinicalWeight)
                RETURN e.evidence_id as id, e.name as name, e.type as type,
                       e.year as year, e.url as url,
                       count(w) as weight_count
                ORDER BY e.year DESC
            """)
            
            return [dict(record) for record in result]
    
    # ==================== INDICATION MANAGEMENT ====================
    
    def list_indications(self) -> List[Dict]:
        """List all disease state indications."""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (i:Indication)
                OPTIONAL MATCH (i)<-[:APPLIES_TO]-(w:ClinicalWeight)
                RETURN i.name as name, i.display_name as display_name,
                       i.description as description, i.first_line as first_line,
                       i.guidelines as guidelines,
                       count(w) as weight_count
                ORDER BY i.name
            """)
            
            return [dict(record) for record in result]
    
    def update_indication(self, name: str, display_name: str = None,
                          description: str = None, first_line: str = None,
                          guidelines: str = None) -> Dict:
        """Update an indication's metadata."""
        with self.driver.session() as session:
            result = session.run("""
                MERGE (i:Indication {name: $name})
                SET i.display_name = COALESCE($display_name, i.display_name),
                    i.description = COALESCE($description, i.description),
                    i.first_line = COALESCE($first_line, i.first_line),
                    i.guidelines = COALESCE($guidelines, i.guidelines),
                    i.updated_at = datetime()
                RETURN i
            """, name=name, display_name=display_name, description=description,
                 first_line=first_line, guidelines=guidelines)
            
            if result.single():
                return {"success": True, "name": name}
            return {"success": False, "error": "Failed to update indication"}
    
    # ==================== EXPERT MANAGEMENT ====================
    
    def get_expert(self, curator_hash: str = None, name: str = None) -> Optional[Dict]:
        """Get expert information."""
        with self.driver.session() as session:
            if curator_hash:
                result = session.run("""
                    MATCH (e:Expert {provenance_hash: $hash})
                    RETURN e.name as name, e.credentials as credentials,
                           e.license as license, e.experience as experience,
                           e.specialization as specialization, e.provenance_hash as hash
                """, hash=curator_hash)
            else:
                result = session.run("""
                    MATCH (e:Expert)
                    WHERE toLower(e.name) CONTAINS toLower($name)
                    RETURN e.name as name, e.credentials as credentials,
                           e.license as license, e.experience as experience,
                           e.specialization as specialization, e.provenance_hash as hash
                """, name=name)
            
            record = result.single()
            return dict(record) if record else None
    
    def list_experts(self) -> List[Dict]:
        """List all clinical experts."""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (e:Expert)
                OPTIONAL MATCH (e)-[:CURATED]->(w:ClinicalWeight)
                RETURN e.name as name, e.credentials as credentials,
                       e.license as license, e.provenance_hash as hash,
                       count(w) as weight_count
                ORDER BY e.name
            """)
            
            return [dict(record) for record in result]
    
    # ==================== PROVENANCE & AUDIT ====================
    
    def get_weight_history(self, ingredient: str, indication: str = None) -> List[Dict]:
        """Get full provenance history for a weight (from JSON audit trail)."""
        # For now, we only have current state in graph
        # In production, you'd want to add a WeightHistory node for each change
        weight = self.get_weight(ingredient, indication)
        if weight:
            return [{
                "current": weight,
                "note": "Full history requires WeightHistory nodes (not yet implemented)"
            }]
        return []
    
    def get_recommendations_for_indication(self, drug_name: str, indication: str) -> List[Dict]:
        """Get all clinically weighted recommendations for a drug given an indication.
        
        Returns ingredients in the same pharmacological class with their clinical weights.
        Deduplicates by ingredient, keeping the first (highest weight) match.
        """
        with self.driver.session() as session:
            result = session.run("""
                // Find the drug ingredient
                MATCH (drug:Ingredient)
                WHERE toLower(drug.name) = toLower($drug_name)
                
                // Find drugs in same pharmacological class
                MATCH (drug)-[:BELONGS_TO]->(class:PharmacologicalClass)<-[:BELONGS_TO]-(other:Ingredient)
                WHERE other <> drug
                
                // Get clinical weights for this indication
                OPTIONAL MATCH (weight:ClinicalWeight)-[:WEIGHTS]->(other)
                WHERE weight.indication = $indication
                
                // Get expert provenance
                OPTIONAL MATCH (expert:Expert)-[:CURATED]->(weight)
                
                // Get evidence
                OPTIONAL MATCH (weight)-[:BASED_ON]->(evidence:Evidence)
                
                WITH other, class, weight, expert, evidence
                WHERE weight IS NOT NULL
                
                // Deduplicate by ingredient, keeping highest weight
                WITH other.name as ingredient_name,
                     collect(DISTINCT class.name)[0] as shared_class,
                     max(weight.weight) as clinical_weight,
                     head(collect(DISTINCT weight.rationale)) as rationale,
                     head(collect(DISTINCT weight.clinical_note)) as clinical_note,
                     head(collect(DISTINCT expert.name)) as curator_name,
                     head(collect(DISTINCT expert.credentials)) as curator_credentials,
                     head(collect(DISTINCT expert.license)) as curator_license,
                     head(collect(DISTINCT evidence.name)) as evidence_name,
                     'expert:graph' as weight_source
                
                RETURN 
                    ingredient_name,
                    shared_class,
                    clinical_weight,
                    rationale,
                    clinical_note,
                    curator_name,
                    curator_credentials,
                    curator_license,
                    evidence_name,
                    weight_source
                ORDER BY clinical_weight DESC
            """, drug_name=drug_name, indication=indication)
            
            return [dict(record) for record in result]

    def export_to_json(self, filepath: str = None) -> Dict:
        """Export all graph weights to JSON format (for backup/migration)."""
        if filepath is None:
            filepath = WEIGHTS_FILE
        
        with self.driver.session() as session:
            # Get all weights grouped by ingredient
            result = session.run("""
                MATCH (w:ClinicalWeight)-[:WEIGHTS]->(i:Ingredient)
                OPTIONAL MATCH (e:Expert)-[:CURATED]->(w)
                OPTIONAL MATCH (w)-[:BASED_ON]->(ev:Evidence)
                RETURN i.name as ingredient, w.indication as indication,
                       w.weight as weight, w.rationale as rationale,
                       w.clinical_note as clinical_note,
                       e.name as curator, e.credentials as credentials,
                       e.license as license, ev.name as evidence
                ORDER BY i.name, w.indication
            """)
            
            drugs = {}
            curator_info = DEFAULT_CURATOR
            
            for record in result:
                ing = record['ingredient'].lower()
                if ing not in drugs:
                    drugs[ing] = {"default": {}, "indications": {}, "clinical_note": record['clinical_note']}
                
                if record['indication'] == 'default':
                    drugs[ing]['default'] = {
                        "weight": record['weight'],
                        "rationale": record['rationale'],
                        "evidence": record['evidence']
                    }
                else:
                    drugs[ing]['indications'][record['indication']] = {
                        "weight": record['weight'],
                        "rationale": record['rationale']
                    }
                
                # Update curator if found
                if record['curator']:
                    curator_info = {
                        "name": record['curator'],
                        "credentials": record['credentials'],
                        "license": record['license']
                    }
            
            # Get indications
            indications_result = session.run("""
                MATCH (i:Indication)
                RETURN i.name as name, i.display_name as display_name,
                       i.description as description, i.first_line as first_line,
                       i.guidelines as guidelines
            """)
            
            disease_states = {}
            for record in indications_result:
                disease_states[record['name']] = {
                    "name": record['display_name'],
                    "description": record['description'],
                    "first_line": record['first_line'],
                    "guidelines": record['guidelines']
                }
            
            export = {
                "version": "2.0",
                "exported_at": datetime.now().isoformat(),
                "source": "neo4j_graph",
                "curator": curator_info,
                "disease_states": disease_states,
                "drugs": drugs
            }
            
            with open(filepath, 'w') as f:
                json.dump(export, f, indent=2)
            
            return export
    
    # ==================== HELPER METHODS ====================
    
    def _compute_hash(self, input_str: str) -> str:
        import hashlib
        return hashlib.sha256(input_str.encode()).hexdigest()[:16]
    
    def _update_json_backup(self, ingredient: str, indication: str, weight: int,
                            rationale: str, evidence_id: str, clinical_note: str,
                            curator: Dict):
        """Update JSON backup for audit trail."""
        try:
            if os.path.exists(WEIGHTS_FILE):
                with open(WEIGHTS_FILE, 'r') as f:
                    data = json.load(f)
            else:
                data = {"version": "2.0", "drugs": {}, "curator": curator}
            
            ing_key = ingredient.lower()
            if ing_key not in data.get('drugs', {}):
                data['drugs'][ing_key] = {"default": {}, "indications": {}, "clinical_note": clinical_note}
            
            weight_data = {"weight": weight, "rationale": rationale}
            
            if indication == 'default':
                data['drugs'][ing_key]['default'] = weight_data
            else:
                data['drugs'][ing_key]['indications'][indication] = weight_data
            
            data['last_updated'] = datetime.now().isoformat()
            
            with open(WEIGHTS_FILE, 'w') as f:
                json.dump(data, f, indent=2)
                
        except Exception as e:
            print(f"Warning: Failed to update JSON backup: {e}")
    
    def _delete_from_json_backup(self, ingredient: str, indication: str):
        """Delete weight from JSON backup."""
        try:
            if os.path.exists(WEIGHTS_FILE):
                with open(WEIGHTS_FILE, 'r') as f:
                    data = json.load(f)
                
                ing_key = ingredient.lower()
                if ing_key in data.get('drugs', {}):
                    if indication == 'default':
                        data['drugs'][ing_key]['default'] = {}
                    else:
                        data['drugs'][ing_key]['indications'].pop(indication, None)
                
                with open(WEIGHTS_FILE, 'w') as f:
                    json.dump(data, f, indent=2)
                    
        except Exception as e:
            print(f"Warning: Failed to update JSON backup: {e}")


# ==================== API HELPER FUNCTIONS ====================

_admin = None

def get_admin() -> GraphWeightsAdmin:
    """Get singleton admin instance."""
    global _admin
    if _admin is None:
        _admin = GraphWeightsAdmin()
    return _admin


def update_clinical_weight(ingredient: str, indication: str, weight: int,
                           rationale: str = None, evidence_id: str = None,
                           clinical_note: str = None) -> Dict:
    """Convenience function for updating weights."""
    return get_admin().update_weight(ingredient, indication, weight, rationale,
                                      evidence_id, clinical_note)


def get_clinical_weight(ingredient: str, indication: str = None) -> Optional[Dict]:
    """Convenience function for getting weights."""
    return get_admin().get_weight(ingredient, indication)


if __name__ == "__main__":
    # Test the admin system
    print("=== Testing Graph Weights Admin ===\n")
    
    admin = GraphWeightsAdmin()
    
    # Test update
    print("1. Updating ezetimibe weight for statin_intolerance...")
    result = admin.update_weight(
        ingredient="ezetimibe",
        indication="statin_intolerance",
        weight=92,  # Updated from 90
        rationale="First-line non-statin alternative - UPDATED via admin"
    )
    print(f"   Result: {result}")
    
    # Verify update
    print("\n2. Verifying update...")
    weight = admin.get_weight("ezetimibe", "statin_intolerance")
    print(f"   Weight: {weight['weight']}/100")
    print(f"   Rationale: {weight['rationale']}")
    print(f"   Curator: {weight['curator']} ({weight['curator_credentials']})")
    
    # List all weighted ingredients
    print("\n3. All weighted ingredients:")
    ingredients = admin.list_all_weighted_ingredients()
    for ing in ingredients[:5]:
        print(f"   {ing['ingredient']}: {ing['weight_count']} weights ({', '.join(ing['indications'])})")
    
    admin.close()
    print("\n✅ Admin system working!")
