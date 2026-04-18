#!/usr/bin/env python3
"""
Extract PubChem Properties for All CID-Matched Ingredients
===========================================================

This script processes all ~2,900 ingredients that have CID mappings and extracts
their PubChem properties (CID, SMILES, InChI, PMID, IUPAC name, molecular formula).
"""

import json
from pathlib import Path
from datetime import datetime

# Define file paths
DATA_DIR = Path(__file__).parent.parent.parent.parent.parent / "data" / "grc20_v2"
CID_MAPPING_FILE = DATA_DIR / "pubchem_cid_mapping.json"
ENRICHED_ENTITIES_FILE = DATA_DIR / "rxnorm_entities_enriched.jsonl"
OUTPUT_FILE = DATA_DIR / "all_pubchem_ingredients.json"


def fetch_pubchem_properties(cid, enriched_entities):
    """Fetch PubChem properties using CID
    
    This function checks if an entity with the given CID exists in the enriched entities,
    and if found, extracts the PubChem properties.
    
    Args:
        cid: PubChem Compound ID as string
        enriched_entities: Dictionary of enriched RxNorm entities
    
    Returns:
        Dictionary of PubChem properties or None if not found
    """
    # Search for entity with the given CID in enriched entities
    for entity_id, entity in enriched_entities.items():
        for prop in entity.get('values', []):
            if prop.get('property') == 'bdd863e095365bbea65deae8ebf1e81b' and prop.get('value') == cid:
                # Found entity with this CID, extract properties
                properties = {}
                
                # Property IDs for PubChem data (from pharma_schema.py)
                PROP_CID = "bdd863e095365bbea65deae8ebf1e81b"      # pubchem_cid
                PROP_SMILES = "56e99a1b93b2573689e2f6a6c662df10"   # smiles
                PROP_INCHI = "6b432fc791ad5358b1f17fdc6abcfacc"     # inchikey (actually contains InChI string)
                PROP_PMID = "c2842d1831e35b2f82fb74b532f4508b"      # pmid (PubMed ID)
                PROP_IUPAC = "5fbf742a110d508abc9af6a1cd1e49e7"     # iupac_name
                PROP_FORMULA = "20aba01a611d57e1bb02ca665dd61acd"   # molecular_formula (with MW)
                
                for prop in entity.get('values', []):
                    prop_id = prop.get('property')
                    value = prop.get('value')
                    
                    if prop_id == PROP_CID:
                        properties['pubchem_cid'] = value
                    elif prop_id == PROP_SMILES:
                        properties['smiles'] = value
                    elif prop_id == PROP_INCHI:
                        # Note: This property ID maps to "inchikey" in schema but contains InChI string
                        properties['inchi'] = value
                    elif prop_id == PROP_PMID:
                        properties['pmid'] = value
                    elif prop_id == PROP_IUPAC:
                        properties['iupac_name'] = value
                    elif prop_id == PROP_FORMULA:
                        # Clean up molecular formula (remove molecular weight)
                        if '\t' in value:
                            value = value.split('\t')[0]
                        properties['molecular_formula'] = value
                
                return properties if properties else None
    
    return None


def main():
    """Main function to process all CID-matched ingredients"""
    print("=" * 80)
    print("EXTRACTING PUBCHEM PROPERTIES FOR ALL CID-MATCHED INGREDIENTS")
    print("=" * 80)
    
    # Load CID mapping file
    print(f"\nLoading CID mapping from: {CID_MAPPING_FILE}")
    with open(CID_MAPPING_FILE, 'r') as f:
        cid_mapping_data = json.load(f)
    
    cid_mapping = cid_mapping_data.get('cid_mapping', {})
    print(f"  Loaded {len(cid_mapping):,} CID mappings")
    
    # Load enriched entities
    print(f"\nLoading enriched entities from: {ENRICHED_ENTITIES_FILE}")
    enriched_entities = {}
    with open(ENRICHED_ENTITIES_FILE, 'r') as f:
        for line in f:
            entity = json.loads(line)
            enriched_entities[entity['id']] = entity
    print(f"  Loaded {len(enriched_entities):,} enriched RxNorm entities")
    
    # Process all CID-matched ingredients
    print(f"\nProcessing {len(cid_mapping):,} CID-matched ingredients...")
    
    ingredients_data = []
    with_properties = 0
    without_properties = 0
    
    for rxcui, mapping in cid_mapping.items():
        ingredient_name = mapping.get('name', 'Unknown')
        cid = mapping.get('cid')
        
        # Extract PubChem properties for the ingredient
        pubchem_props = None
        if cid:
            pubchem_props = fetch_pubchem_properties(cid, enriched_entities)
        
        # Build the ingredient data with PubChem properties at the top level
        ingredient_data = {
            'ingredient': ingredient_name,
            'rxcui': rxcui,
            'cid': cid,
            'pubchem_properties': pubchem_props
        }
        
        ingredients_data.append(ingredient_data)
        
        if pubchem_props:
            with_properties += 1
        else:
            without_properties += 1
    
    # Save results to JSON file
    print(f"\nSaving results to: {OUTPUT_FILE}")
    output_data = {
        'metadata': {
            'generated_at': datetime.now().isoformat(),
            'total_ingredients': len(ingredients_data),
            'with_properties': with_properties,
            'without_properties': without_properties,
            'coverage_percentage': round((with_properties / len(ingredients_data)) * 100, 2)
        },
        'ingredients': ingredients_data
    }
    
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(output_data, f, indent=2)
    
    # Print summary
    print("\n" + "=" * 80)
    print("EXTRACTION COMPLETE")
    print("=" * 80)
    print(f"  Total Ingredients: {len(ingredients_data):,}")
    print(f"  With Properties: {with_properties:,} ({output_data['metadata']['coverage_percentage']:.2f}%)")
    print(f"  Without Properties: {without_properties:,} ({100 - output_data['metadata']['coverage_percentage']:.2f}%)")
    print(f"  Output file: {OUTPUT_FILE}")
    print("=" * 80)


if __name__ == "__main__":
    main()
