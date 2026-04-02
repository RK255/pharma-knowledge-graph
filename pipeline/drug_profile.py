#!/usr/bin/env python3
"""
Drug Profile Extractor

Extracts comprehensive drug information from the GRC-20 knowledge graph.

Usage:
    python drug_profile.py <drug_name>
    python drug_profile.py <drug_name1> <drug_name2> ...   # Profile multiple drugs
    python drug_profile.py --list                          # List all ingredients with PubChem data
    python drug_profile.py --all                           # Profile 10 enriched ingredients
    python drug_profile.py --demo                          # Profile demo drug set
"""

import json
import sys
from pathlib import Path
from collections import defaultdict

DATA_DIR = Path(__file__).parent.parent.parent.parent / "data" / "grc20_v2"
SCHEMA_PATH = Path(__file__).parent / "00_schema"

sys.path.insert(0, str(SCHEMA_PATH))
from pharma_schema import PharmaSchema

# Demo drug set
DEMO_DRUGS = [
    'cetirizine',
    'pseudoephedrine',
    'semaglutide',
    'atorvastatin',
    'metformin',
    'levothyroxine',
    'lisinopril',
    'amlodipine',
    'gabapentin',
    'omeprazole',
]

class DrugProfiler:
    def __init__(self):
        self.schema = PharmaSchema()
        self.entities = {}
        self.entity_by_name = {}
        self.entity_by_rxcui = {}
        self.relations_from = {}
        self.relations_to = {}
        
        self.type_id_to_name = {v: k for k, v in self.schema.types.items()}
        self.rel_id_to_name = {v: k for k, v in self.schema.relations.items()}
        self.prop_id_to_name = {v: k for k, v in self.schema.properties.items()}
        
        self._load_data()
    
    def _load_data(self):
        print("Loading knowledge graph...", end=" ", flush=True)
        
        entities_file = DATA_DIR / "grc20_merged_entities.jsonl"
        with open(entities_file, 'r') as f:
            for line in f:
                entity = json.loads(line)
                eid = entity['id']
                self.entities[eid] = entity
                name = entity.get('name', '')
                if name:
                    name_lower = name.lower()
                    if name_lower not in self.entity_by_name:
                        self.entity_by_name[name_lower] = []
                    self.entity_by_name[name_lower].append(eid)
                
                for v in entity.get('values', []):
                    if v.get('property') == self.schema.properties.get('rxcui'):
                        rxcui = v.get('value')
                        if rxcui:
                            self.entity_by_rxcui[rxcui] = eid
        
        relations_file = DATA_DIR / "grc20_merged_relations.jsonl"
        with open(relations_file, 'r') as f:
            for line in f:
                rel = json.loads(line)
                from_id = rel.get('from')
                to_id = rel.get('to')
                rel_type = rel.get('type')
                if isinstance(rel_type, dict):
                    rel_type = rel_type.get('id')
                
                if from_id not in self.relations_from:
                    self.relations_from[from_id] = []
                self.relations_from[from_id].append((rel_type, to_id))
                
                if to_id not in self.relations_to:
                    self.relations_to[to_id] = []
                self.relations_to[to_id].append((rel_type, from_id))
        
        print(f"Loaded {len(self.entities):,} entities, {sum(len(v) for v in self.relations_from.values()):,} relations")
    
    def get_type_name(self, entity):
        type_ids = entity.get('types', [])
        if not type_ids:
            return 'Unknown'
        return self.type_id_to_name.get(type_ids[0], type_ids[0][:8])
    
    def get_entity_name(self, eid):
        if eid not in self.entities:
            return f"Unknown({eid[:8]})"
        return self.entities[eid].get('name', 'unnamed')
    
    def get_entity_rxcui(self, eid):
        if eid not in self.entities:
            return None
        prop_id = self.schema.properties.get('rxcui')
        for v in self.entities[eid].get('values', []):
            if v.get('property') == prop_id:
                return v.get('value')
        return None
    
    def get_entity_prop(self, eid, prop_name):
        if eid not in self.entities:
            return None
        prop_id = self.schema.properties.get(prop_name)
        for v in self.entities[eid].get('values', []):
            if v.get('property') == prop_id:
                return v.get('value')
        return None
    
    def get_entity_props(self, eid):
        if eid not in self.entities:
            return {}
        props = {}
        for v in self.entities[eid].get('values', []):
            prop_id = v.get('property')
            prop_name = self.prop_id_to_name.get(prop_id, prop_id[:8] if prop_id else 'unknown')
            val = v.get('value')
            if prop_name in props:
                if not isinstance(props[prop_name], list):
                    props[prop_name] = [props[prop_name]]
                props[prop_name].append(val)
            else:
                props[prop_name] = val
        return props
    
    def get_relations(self, eid, rel_name=None, direction='out'):
        rel_id = self.schema.relations.get(rel_name) if rel_name else None
        relations = self.relations_from.get(eid, []) if direction == 'out' else self.relations_to.get(eid, [])
        results = []
        for rt, other_id in relations:
            if rel_id and rt != rel_id:
                continue
            rel_name_found = self.rel_id_to_name.get(rt, rt[:8] if rt else 'unknown')
            results.append((rel_name_found, other_id))
        return results
    
    def get_all_related(self, eid, rel_name, direction='out'):
        relations = self.get_relations(eid, rel_name, direction)
        return [other_id for _, other_id in relations]
    
    def get_related_by_type(self, eid, rel_name, direction, target_type):
        relations = self.get_relations(eid, rel_name, direction)
        results = []
        for _, other_id in relations:
            entity = self.entities.get(other_id, {})
            if self.get_type_name(entity) == target_type:
                results.append(other_id)
        return results
    
    def get_provenance(self, eid):
        prov_ids = self.get_all_related(eid, 'has_provenance', 'out')
        sources = []
        for pid in prov_ids:
            name = self.get_entity_prop(pid, 'name')
            if name:
                sources.append(name)
        return sources
    
    def list_enriched_ingredients(self, limit=50):
        ingredient_type = self.schema.types.get('Ingredient')
        smiles_prop = self.schema.properties.get('smiles')
        
        ingredients = []
        for eid, entity in self.entities.items():
            types = entity.get('types', [])
            if ingredient_type not in types:
                continue
            
            has_smiles = False
            for v in entity.get('values', []):
                if v.get('property') == smiles_prop:
                    has_smiles = True
                    break
            
            if has_smiles:
                name = entity.get('name', 'unknown')
                rxcui = self.get_entity_prop(eid, 'rxcui')
                ingredients.append((name, rxcui, eid))
        
        ingredients.sort(key=lambda x: x[0].lower())
        return ingredients[:limit]
    
    def profile(self, drug_name):
        ingredient_ids = self.entity_by_name.get(drug_name.lower(), [])
        if not ingredient_ids:
            return None
        
        ingredient_id = ingredient_ids[0]
        ingredient = self.entities[ingredient_id]
        props = self.get_entity_props(ingredient_id)
        
        profile = {
            'name': drug_name,
            'rxcui': props.get('rxcui'),
            'tty': props.get('tty'),
            'smiles': props.get('smiles'),
            'inchikey': props.get('inchikey'),
            'molecular_weight': props.get('molecular_weight'),
            'iupac_name': props.get('iupac_name'),
            'pmid': props.get('pmid'),
            'pubchem_cid': props.get('pubchem_cid'),
            'provenance': self.get_provenance(ingredient_id),
            'brand_names': [],
            'dose_forms': [],  # SCDF level
            'dose_form_types': [],  # DF level (actual dose form types like Oral Solution)
            'precise_ingredients': [],
            'multiple_ingredients': [],
            'clinical_drug_components': [],
            'clinical_drug_forms': [],
            'clinical_drug_groups': [],
            'clinical_drugs': [],
            'semantic_branded_drugs': [],
            'ndcs': [],
            'package_inserts': [],
        }
        
        # BRAND NAMES (BN) - IN --tradename_of--> BN
        bn_ids = self.get_all_related(ingredient_id, 'tradename_of', 'out')
        for bn_id in bn_ids:
            bn_name = self.get_entity_name(bn_id)
            bn_rxcui = self.get_entity_rxcui(bn_id)
            profile['brand_names'].append((bn_name, bn_rxcui))
        
        # PRECISE INGREDIENTS (PIN) - IN --form_of--> PIN
        pin_ids = self.get_all_related(ingredient_id, 'form_of', 'out')
        for pin_id in pin_ids:
            pin_name = self.get_entity_name(pin_id)
            pin_rxcui = self.get_entity_rxcui(pin_id)
            profile['precise_ingredients'].append((pin_name, pin_rxcui))
        
        # MULTIPLE INGREDIENTS (MIN) - IN --has_part--> MIN
        min_ids = self.get_all_related(ingredient_id, 'has_part', 'out')
        for min_id in min_ids:
            min_name = self.get_entity_name(min_id)
            min_rxcui = self.get_entity_rxcui(min_id)
            profile['multiple_ingredients'].append((min_name, min_rxcui))
        
        # CLINICAL DRUG COMPONENTS (SCDC) - IN --has_ingredient--> SCDC
        scdc_ids = self.get_related_by_type(ingredient_id, 'has_ingredient', 'out', 'ClinicalDrugComponent')
        for scdc_id in scdc_ids:
            scdc_name = self.get_entity_name(scdc_id)
            scdc_rxcui = self.get_entity_rxcui(scdc_id)
            profile['clinical_drug_components'].append((scdc_name, scdc_rxcui))
        
        # CLINICAL DRUG FORMS (SCDF) - IN --has_ingredient--> SCDF
        scdf_ids = self.get_related_by_type(ingredient_id, 'has_ingredient', 'out', 'ClinicalDrugForm')
        dose_form_types_seen = set()
        for scdf_id in scdf_ids:
            scdf_name = self.get_entity_name(scdf_id)
            scdf_rxcui = self.get_entity_rxcui(scdf_id)
            profile['clinical_drug_forms'].append((scdf_name, scdf_rxcui))
            
            # Get dose form type (DF) from SCDF --dose_form_of--> DF
            df_ids = self.get_related_by_type(scdf_id, 'dose_form_of', 'out', 'DoseForm')
            for df_id in df_ids:
                df_name = self.get_entity_name(df_id)
                df_rxcui = self.get_entity_rxcui(df_id)
                if df_rxcui not in dose_form_types_seen:
                    dose_form_types_seen.add(df_rxcui)
                    profile['dose_form_types'].append((df_name, df_rxcui))
        
        # Also add SCDF names to dose_forms for backwards compatibility
        for scdf_name, scdf_rxcui in profile['clinical_drug_forms']:
            profile['dose_forms'].append((scdf_name, scdf_rxcui))
        
        # CLINICAL DRUG GROUPS (SCDG) - IN --has_ingredient--> SCDG
        scdg_ids = self.get_related_by_type(ingredient_id, 'has_ingredient', 'out', 'ClinicalDrugGroup')
        for scdg_id in scdg_ids:
            scdg_name = self.get_entity_name(scdg_id)
            scdg_rxcui = self.get_entity_rxcui(scdg_id)
            profile['clinical_drug_groups'].append((scdg_name, scdg_rxcui))
        
        # CLINICAL DRUGS (SCD) - via SCDC --consists_of--> SCD (OUTGOING!)
        scd_ids_seen = set()
        for scdc_id in scdc_ids:
            scd_ids = self.get_related_by_type(scdc_id, 'consists_of', 'out', 'ClinicalDrug')
            for scd_id in scd_ids:
                if scd_id in scd_ids_seen:
                    continue
                scd_ids_seen.add(scd_id)
                scd_name = self.get_entity_name(scd_id)
                scd_rxcui = self.get_entity_rxcui(scd_id)
                profile['clinical_drugs'].append((scd_name, scd_rxcui))
        
        # SEMANTIC BRANDED DRUGS (SBD) - via SCDC --consists_of--> SBD (OUTGOING!)
        sbd_ids_seen = set()
        for scdc_id in scdc_ids:
            sbd_ids = self.get_related_by_type(scdc_id, 'consists_of', 'out', 'BrandedDrug')
            for sbd_id in sbd_ids:
                if sbd_id in sbd_ids_seen:
                    continue
                sbd_ids_seen.add(sbd_id)
                sbd_name = self.get_entity_name(sbd_id)
                sbd_rxcui = self.get_entity_rxcui(sbd_id)
                profile['semantic_branded_drugs'].append((sbd_name, sbd_rxcui))
                
                # Get NDCs for this SBD
                ndc_ids = self.get_related_by_type(sbd_id, 'maps_to_rxcui', 'in', 'NDC')
                for ndc_id in ndc_ids:
                    ndc_name = self.get_entity_name(ndc_id)
                    if ndc_name not in profile['ndcs']:
                        profile['ndcs'].append(ndc_name)
                
                # Get Package Inserts for this SBD
                pi_ids = self.get_related_by_type(sbd_id, 'maps_to_rxcui', 'in', 'PackageInsert')
                for pi_id in pi_ids:
                    pi_name = self.get_entity_name(pi_id)
                    if pi_name not in profile['package_inserts']:
                        profile['package_inserts'].append(pi_name)
        
        return profile
    
    def print_profile(self, profile, brief=False):
        print("\n" + "=" * 80)
        print(f"DRUG PROFILE: {profile['name'].upper()}")
        print("=" * 80)
        
        # PubChem section first
        print(f"\n{'PUBCHEM DATA':<25}")
        if profile['smiles']:
            smiles = profile['smiles']
            if len(smiles) > 60:
                print(f"  SMILES:         {smiles[:60]}...")
                print(f"                  {smiles[60:]}")
            else:
                print(f"  SMILES:         {smiles}")
        if profile['inchikey']:
            key = profile['inchikey']
            if len(key) > 60:
                print(f"  InChIKey:       {key[:60]}...")
            else:
                print(f"  InChIKey:       {key}")
        if profile['iupac_name']:
            name = profile['iupac_name']
            if len(name) > 60:
                print(f"  IUPAC Name:     {name[:60]}...")
                print(f"                  {name[60:]}")
            else:
                print(f"  IUPAC Name:     {name}")
        if profile['molecular_weight']:
            print(f"  Molecular Wt:   {profile['molecular_weight']}")
        if profile['pubchem_cid']:
            print(f"  PubChem CID:    {profile['pubchem_cid']}")
        if profile['pmid']:
            print(f"  PMID:           {profile['pmid']}")
        if not any([profile['smiles'], profile['inchikey'], profile['iupac_name']]):
            print(f"  (not available)")
        
        print(f"\n{'Brand names':<25}")
        if profile['brand_names']:
            for name, rxcui in profile['brand_names'][:10]:
                print(f"  • {name:<40} RXCUI: {rxcui}")
            if len(profile['brand_names']) > 10:
                print(f"  ... and {len(profile['brand_names']) - 10} more")
        else:
            print(f"  (none found)")
        
        print(f"\n{'Dose form types':<25}")
        if profile['dose_form_types']:
            for name, rxcui in profile['dose_form_types'][:10]:
                print(f"  • {name:<40} RXCUI: {rxcui}")
            if len(profile['dose_form_types']) > 10:
                print(f"  ... and {len(profile['dose_form_types']) - 10} more")
        else:
            print(f"  (none found)")
        
        print(f"\n{'Clinical Drug Forms':<25}")
        if profile['clinical_drug_forms']:
            for name, rxcui in profile['clinical_drug_forms'][:10]:
                print(f"  • {name:<40} RXCUI: {rxcui}")
            if len(profile['clinical_drug_forms']) > 10:
                print(f"  ... and {len(profile['clinical_drug_forms']) - 10} more")
        else:
            print(f"  (none found)")
        
        print(f"\n{'Multiple ingredients':<25}")
        if profile['multiple_ingredients']:
            for name, rxcui in profile['multiple_ingredients'][:10]:
                print(f"  • {name:<40} RXCUI: {rxcui}")
        else:
            print(f"  (none)")
        
        print(f"\n{'Precise ingredient':<25}")
        if profile['precise_ingredients']:
            for name, rxcui in profile['precise_ingredients'][:10]:
                print(f"  • {name:<40} RXCUI: {rxcui}")
        else:
            print(f"  (none)")
        
        print(f"\n{'RXCUI':<25}")
        print(f"  {profile['rxcui']}")
        
        print(f"\n{'Semantic Branded Drugs':<25}")
        if profile['semantic_branded_drugs']:
            for name, rxcui in profile['semantic_branded_drugs'][:10]:
                print(f"  • {name:<55} RXCUI: {rxcui}")
            if len(profile['semantic_branded_drugs']) > 10:
                print(f"  ... and {len(profile['semantic_branded_drugs']) - 10} more")
        else:
            print(f"  (none found)")
        
        print(f"\n{'Tags':<25}")
        print(f"  {', '.join(profile['provenance'])}")
        
        # Summary
        print(f"\n{'─' * 80}")
        print(f"{'SUMMARY':<25}")
        print(f"  RXCUI:               {profile['rxcui']}")
        print(f"  Brand Names:         {len(profile['brand_names'])}")
        print(f"  Dose Form Types:     {len(profile['dose_form_types'])}")
        print(f"  Clinical Drug Forms: {len(profile['clinical_drug_forms'])}")
        print(f"  Precise Ingredients: {len(profile['precise_ingredients'])}")
        print(f"  Multiple Ingredients:{len(profile['multiple_ingredients'])}")
        print(f"  SCDC (Components):   {len(profile['clinical_drug_components'])}")
        print(f"  SCD (Clinical):      {len(profile['clinical_drugs'])}")
        print(f"  SBD (Branded):       {len(profile['semantic_branded_drugs'])}")
        print(f"  NDCs:                {len(profile['ndcs'])}")
        print(f"  Package Inserts:     {len(profile['package_inserts'])}")
        print(f"  Has PubChem:         {'Yes' if profile['smiles'] else 'No'}")
    
    def print_summary_table(self, profiles):
        print("\n" + "=" * 150)
        print("DRUG PROFILE SUMMARY")
        print("=" * 150)
        
        header = f"{'Drug':<15} {'RXCUI':<10} {'Brands':<7} {'DF Types':<9} {'SCDF':<6} {'SCDC':<5} {'SCD':<5} {'SBD':<5} {'NDCs':<6} {'PIs':<4} {'PubChem':<7}"
        print(header)
        print("-" * 150)
        
        for p in profiles:
            has_pubchem = "Yes" if p['smiles'] else "No"
            row = f"{p['name']:<15} {str(p['rxcui']):<10} {len(p['brand_names']):<7} {len(p['dose_form_types']):<9} {len(p['clinical_drug_forms']):<6} {len(p['clinical_drug_components']):<5} {len(p['clinical_drugs']):<5} {len(p['semantic_branded_drugs']):<5} {len(p['ndcs']):<6} {len(p['package_inserts']):<4} {has_pubchem:<7}"
            print(row)


def main():
    profiler = DrugProfiler()
    
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python drug_profile.py <drug_name>                    # Profile a specific drug")
        print("  python drug_profile.py <drug1> <drug2> ...             # Profile multiple drugs")
        print("  python drug_profile.py --list                          # List enriched ingredients")
        print("  python drug_profile.py --all                           # Profile 10 enriched ingredients")
        print("  python drug_profile.py --demo                          # Profile demo drug set")
        sys.exit(1)
    
    arg = sys.argv[1]
    
    if arg == '--list':
        print("\nEnriched Ingredients (with PubChem data):")
        print("-" * 60)
        ingredients = profiler.list_enriched_ingredients(limit=50)
        for name, rxcui, eid in ingredients:
            print(f"  {name:<30} RXCUI: {rxcui}")
        print(f"\nTotal: {len(ingredients)} ingredients with PubChem enrichment")
    
    elif arg == '--all':
        ingredients = profiler.list_enriched_ingredients(limit=10)
        profiles = []
        for name, rxcui, eid in ingredients:
            profile = profiler.profile(name)
            if profile:
                profiles.append(profile)
                profiler.print_profile(profile)
        
        profiler.print_summary_table(profiles)
    
    elif arg == '--demo':
        print(f"\nProfiling {len(DEMO_DRUGS)} demo drugs...")
        profiles = []
        for drug_name in DEMO_DRUGS:
            profile = profiler.profile(drug_name)
            if profile:
                profiles.append(profile)
                print(f"  ✓ {drug_name}")
            else:
                print(f"  ✗ {drug_name} (not found)")
        
        profiler.print_summary_table(profiles)
    
    else:
        drug_names = sys.argv[1:]
        profiles = []
        not_found = []
        
        for drug_name in drug_names:
            profile = profiler.profile(drug_name)
            if profile:
                profiles.append(profile)
            else:
                not_found.append(drug_name)
        
        if profiles:
            for profile in profiles:
                profiler.print_profile(profile)
            profiler.print_summary_table(profiles)
        
        if not_found:
            print(f"\nDrugs not found: {', '.join(not_found)}")
            print("\nTry one of these enriched ingredients:")
            ingredients = profiler.list_enriched_ingredients(limit=10)
            for name, rxcui, eid in ingredients:
                print(f"  {name}")


if __name__ == '__main__':
    main()
