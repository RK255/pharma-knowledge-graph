"""
Graph-Based Clinical Weight Lookup
Replaces JSON-based weights with Neo4j graph queries
"""

from neo4j import GraphDatabase
from typing import Dict, List, Optional

NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "Nani*48301"

class GraphClinicalWeights:
    """Query clinical weights from Neo4j graph."""
    
    def __init__(self):
        self.driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    
    def close(self):
        self.driver.close()
    
    def get_weight(self, ingredient_name: str, indication: str = None) -> Optional[Dict]:
        """Get clinical weight for an ingredient, optionally filtered by indication.
        
        Returns dict with:
            - weight: int (0-100)
            - rationale: str
            - clinical_note: str
            - curator: str
            - curator_credentials: str
            - curator_license: str
            - evidence: str
            - source: str ('expert:graph')
        """
        with self.driver.session() as session:
            if indication:
                # Get indication-specific weight
                result = session.run("""
                    MATCH (w:ClinicalWeight)-[:WEIGHTS]->(i:Ingredient)
                    WHERE toLower(i.name) = toLower($ingredient)
                      AND w.indication = $indication
                    OPTIONAL MATCH (e:Expert)-[:CURATED]->(w)
                    OPTIONAL MATCH (w)-[:BASED_ON]->(ev:Evidence)
                    RETURN w.weight as weight, w.rationale as rationale,
                           w.clinical_note as clinical_note,
                           e.name as curator, e.credentials as curator_credentials,
                           e.license as curator_license,
                           ev.name as evidence
                """, ingredient=ingredient_name, indication=indication)
            else:
                # Get default weight
                result = session.run("""
                    MATCH (w:ClinicalWeight)-[:WEIGHTS]->(i:Ingredient)
                    WHERE toLower(i.name) = toLower($ingredient)
                      AND w.indication = 'default'
                    OPTIONAL MATCH (e:Expert)-[:CURATED]->(w)
                    OPTIONAL MATCH (w)-[:BASED_ON]->(ev:Evidence)
                    RETURN w.weight as weight, w.rationale as rationale,
                           w.clinical_note as clinical_note,
                           e.name as curator, e.credentials as curator_credentials,
                           e.license as curator_license,
                           ev.name as evidence
                """, ingredient=ingredient_name)
            
            record = result.single()
            if record and record['weight'] is not None:
                return {
                    'weight': record['weight'],
                    'rationale': record['rationale'],
                    'clinical_note': record['clinical_note'],
                    'curator': record['curator'],
                    'curator_credentials': record['curator_credentials'],
                    'curator_license': record['curator_license'],
                    'evidence': record['evidence'],
                    'source': f'expert:graph:{indication}' if indication else 'expert:graph:default'
                }
            
            return None
    
    def get_all_weights_for_ingredient(self, ingredient_name: str) -> List[Dict]:
        """Get all clinical weights for an ingredient across all indications."""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (w:ClinicalWeight)-[:WEIGHTS]->(i:Ingredient)
                WHERE toLower(i.name) = toLower($ingredient)
                OPTIONAL MATCH (e:Expert)-[:CURATED]->(w)
                OPTIONAL MATCH (w)-[:BASED_ON]->(ev:Evidence)
                RETURN w.indication as indication, w.weight as weight,
                       w.rationale as rationale, w.clinical_note as clinical_note,
                       e.name as curator, e.credentials as curator_credentials,
                       e.license as curator_license, ev.name as evidence
                ORDER BY w.weight DESC
            """, ingredient=ingredient_name)
            
            weights = []
            for record in result:
                weights.append({
                    'indication': record['indication'],
                    'weight': record['weight'],
                    'rationale': record['rationale'],
                    'clinical_note': record['clinical_note'],
                    'curator': record['curator'],
                    'curator_credentials': record['curator_credentials'],
                    'curator_license': record['curator_license'],
                    'evidence': record['evidence']
                })
            
            return weights
    
    def get_recommendations_for_indication(self, drug_name: str, indication: str) -> List[Dict]:
        """Get all clinically weighted recommendations for a drug given an indication.
        
        Returns ingredients in the same pharmacological class with their clinical weights.
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
                
                RETURN 
                    other.name as ingredient_name,
                    class.name as shared_class,
                    weight.weight as clinical_weight,
                    weight.rationale as rationale,
                    weight.clinical_note as clinical_note,
                    expert.name as curator_name,
                    expert.credentials as curator_credentials,
                    expert.license as curator_license,
                    evidence.name as evidence_name,
                    'expert:graph' as weight_source
                ORDER BY weight.weight DESC
            """, drug_name=drug_name, indication=indication)
            
            return [dict(record) for record in result]
    
    def get_expert_info(self, expert_name: str = None) -> Dict:
        """Get information about clinical experts."""
        with self.driver.session() as session:
            if expert_name:
                result = session.run("""
                    MATCH (e:Expert)
                    WHERE toLower(e.name) CONTAINS toLower($name)
                    RETURN e.name as name, e.credentials as credentials,
                           e.license as license, e.experience as experience,
                           e.specialization as specialization
                """, name=expert_name)
            else:
                result = session.run("""
                    MATCH (e:Expert)
                    RETURN e.name as name, e.credentials as credentials,
                           e.license as license, e.experience as experience,
                           e.specialization as specialization
                """)
            
            experts = [dict(record) for record in result]
            return experts[0] if len(experts) == 1 else experts


# Singleton instance
_graph_weights = None

def get_graph_weights() -> GraphClinicalWeights:
    """Get singleton instance of graph clinical weights."""
    global _graph_weights
    if _graph_weights is None:
        _graph_weights = GraphClinicalWeights()
    return _graph_weights


# Convenience functions
def get_clinical_weight(ingredient: str, indication: str = None) -> Optional[Dict]:
    """Get clinical weight for an ingredient."""
    return get_graph_weights().get_weight(ingredient, indication)

def get_recommendations(drug: str, indication: str) -> List[Dict]:
    """Get clinical recommendations for a drug given an indication."""
    return get_graph_weights().get_recommendations_for_indication(drug, indication)


if __name__ == "__main__":
    # Test the graph weights
    print("=== Testing Graph Clinical Weights ===\n")
    
    gw = GraphClinicalWeights()
    
    # Test single weight lookup
    print("1. Get weight for ezetimibe (statin_intolerance):")
    weight = gw.get_weight("ezetimibe", "statin_intolerance")
    if weight:
        print(f"   Weight: {weight['weight']}/100")
        print(f"   Rationale: {weight['rationale']}")
        print(f"   Curator: {weight['curator']} ({weight['curator_credentials']})")
        print(f"   Evidence: {weight['evidence']}")
    
    # Test all weights for an ingredient
    print("\n2. All weights for ezetimibe:")
    weights = gw.get_all_weights_for_ingredient("ezetimibe")
    for w in weights:
        print(f"   {w['indication']}: {w['weight']}/100")
    
    # Test recommendations
    print("\n3. Recommendations for simvastatin (statin_intolerance):")
    recs = gw.get_recommendations_for_indication("simvastatin", "statin_intolerance")
    for r in recs:
        print(f"   {r['ingredient_name']}: {r['clinical_weight']}/100 - {r['rationale']}")
    
    gw.close()
    print("\n✅ Graph clinical weights working!")
