#!/usr/bin/env python3
"""
Drug Profile Exporter

Exports comprehensive drug profiles to JSON format.

Usage:
    python drug_profile_export.py --output profiles.json
    python drug_profile_export.py --drugs "cetirizine,ibuprofen,acetaminophen" --output profiles.json
"""

import json
import sys
from pathlib import Path
from collections import defaultdict
from datetime import datetime

DATA_DIR = Path(__file__).parent.parent.parent.parent / "data" / "grc20_v2"
SCHEMA_PATH = Path(__file__).parent / "00_schema"
OUTPUT_DIR = Path(__file__).parent.parent.parent.parent / "data" / "profiles"

sys.path.insert(0, str(SCHEMA_PATH))
from pharma_schema import PharmaSchema

# Default drug set for comprehensive export
DEFAULT_DRUGS = [
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

class DrugProfileExporter:
    def __init__(self):
        self.schema = PharmaSchema()
        self.entities = {}
        self.entity_by_name = {}
        self.entity_by_rxcui = {}
        self.relations_from = {}
        self.relations_to = {}
        self.cid_mapping = {}  # RxCUI -> CID mapping
        
        self.type_id_to_name = {v: k for k, v in self.schema.types.items()}
        self.rel_id_to_name = {v: k for k, v in self.schema.relations.items()}
        self.prop_id_to_name = {v: k for k, v in self.schema.properties.items()}
        
        self._load_cid_mapping()
        self._load_data()
    
    def _load_cid_mapping(self):
        """Load PubChem CID mapping from cache file"""
        cid_file = DATA_DIR / "pubchem_cid_mapping.json"
        if cid_file.exists():
            with open(cid_file, 'r') as f:
                data = json.load(f)
            self.cid_mapping = data.get('cid_mapping', {})
            print(f"Loaded CID mapping: {len(self.cid_mapping)} entries")
        else:
            print(f"Warning: CID mapping file not found at {cid_file}")
    
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
    
    def get_cid_for_rxcui(self, rxcui):
        """Look up PubChem CID by RxCUI"""
        if not rxcui:
            return None
        rxcui_str = str(rxcui)
        if rxcui_str in self.cid_mapping:
            return self.cid_mapping[rxcui_str].get('cid')
        return None
    
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
            name = self.get_entity_props(pid).get('name')
            if name:
                sources.append(name)
        return sources
    
    def profile_comprehensive(self, drug_name):
        """Build a comprehensive drug profile with all connected entities"""
        ingredient_ids = self.entity_by_name.get(drug_name.lower(), [])
        if not ingredient_ids:
            return None
        
        ingredient_id = ingredient_ids[0]
        ingredient = self.entities[ingredient_id]
        props = self.get_entity_props(ingredient_id)
        rxcui = props.get('rxcui')
        
        # Get CID from mapping
        pubchem_cid = self.get_cid_for_rxcui(rxcui)
        
        profile = {
            # Core ingredient info
            'ingredient': {
                'id': ingredient_id,
                'name': drug_name,
                'rxcui': rxcui,
                'tty': props.get('tty'),
                'provenance': self.get_provenance(ingredient_id),
            },
            
            # PubChem data
            'pubchem': {
                'cid': pubchem_cid,
                'smiles': props.get('smiles'),
                'inchikey': props.get('inchikey'),
                'inchi': props.get('inchi'),
                'molecular_weight': props.get('molecular_weight'),
                'iupac_name': props.get('iupac_name'),
                'pmid': props.get('pmid'),
            },
            
            # Brand names
            'brand_names': [],
            
            # Dose forms
            'dose_form_types': [],  # DF level
            'clinical_drug_forms': [],  # SCDF level
            
            # Ingredients
            'precise_ingredients': [],
            'multiple_ingredients': [],
            
            # Clinical drugs
            'clinical_drug_components': [],  # SCDC
            'clinical_drug_groups': [],  # SCDG
            'clinical_drugs': [],  # SCD
            
            # Branded drugs
            'semantic_branded_drugs': [],  # SBD
            'branded_drug_forms': [],  # SBDF
            
            # NDCs and Package Inserts
            'ndcs': [],
            'package_inserts': [],
            
            # Statistics
            'stats': {}
        }
        
        # === BRAND NAMES (BN) ===
        bn_ids = self.get_all_related(ingredient_id, 'tradename_of', 'out')
        for bn_id in bn_ids:
            bn_props = self.get_entity_props(bn_id)
            profile['brand_names'].append({
                'id': bn_id,
                'name': self.get_entity_name(bn_id),
                'rxcui': bn_props.get('rxcui'),
            })
        
        # === PRECISE INGREDIENTS (PIN) ===
        pin_ids = self.get_all_related(ingredient_id, 'form_of', 'out')
        for pin_id in pin_ids:
            pin_props = self.get_entity_props(pin_id)
            pin_rxcui = pin_props.get('rxcui')
            profile['precise_ingredients'].append({
                'id': pin_id,
                'name': self.get_entity_name(pin_id),
                'rxcui': pin_rxcui,
                'pubchem_cid': self.get_cid_for_rxcui(pin_rxcui),
            })
        
        # === MULTIPLE INGREDIENTS (MIN) ===
        min_ids = self.get_all_related(ingredient_id, 'has_part', 'out')
        for min_id in min_ids:
            min_props = self.get_entity_props(min_id)
            # Get all ingredients in this MIN
            min_parts = self.get_all_related(min_id, 'has_part', 'in')
            ingredients = []
            for part_id in min_parts:
                part_props = self.get_entity_props(part_id)
                part_rxcui = part_props.get('rxcui')
                ingredients.append({
                    'name': self.get_entity_name(part_id),
                    'rxcui': part_rxcui,
                    'pubchem_cid': self.get_cid_for_rxcui(part_rxcui),
                })
            profile['multiple_ingredients'].append({
                'id': min_id,
                'name': self.get_entity_name(min_id),
                'rxcui': min_props.get('rxcui'),
                'ingredients': ingredients,
            })
        
        # === CLINICAL DRUG COMPONENTS (SCDC) ===
        scdc_ids = self.get_related_by_type(ingredient_id, 'has_ingredient', 'out', 'ClinicalDrugComponent')
        for scdc_id in scdc_ids:
            scdc_props = self.get_entity_props(scdc_id)
            profile['clinical_drug_components'].append({
                'id': scdc_id,
                'name': self.get_entity_name(scdc_id),
                'rxcui': scdc_props.get('rxcui'),
            })
        
        # === CLINICAL DRUG FORMS (SCDF) and DOSE FORM TYPES (DF) ===
        scdf_ids = self.get_related_by_type(ingredient_id, 'has_ingredient', 'out', 'ClinicalDrugForm')
        dose_form_types_seen = set()
        
        for scdf_id in scdf_ids:
            scdf_props = self.get_entity_props(scdf_id)
            
            scdf_record = {
                'id': scdf_id,
                'name': self.get_entity_name(scdf_id),
                'rxcui': scdf_props.get('rxcui'),
                'dose_form_type': None,
            }
            
            # Get dose form type (DF)
            df_ids = self.get_related_by_type(scdf_id, 'dose_form_of', 'out', 'DoseForm')
            if df_ids:
                df_id = df_ids[0]
                df_props = self.get_entity_props(df_id)
                df_rxcui = df_props.get('rxcui')
                scdf_record['dose_form_type'] = {
                    'id': df_id,
                    'name': self.get_entity_name(df_id),
                    'rxcui': df_rxcui,
                }
                if df_rxcui not in dose_form_types_seen:
                    dose_form_types_seen.add(df_rxcui)
                    profile['dose_form_types'].append({
                        'id': df_id,
                        'name': self.get_entity_name(df_id),
                        'rxcui': df_rxcui,
                    })
            
            profile['clinical_drug_forms'].append(scdf_record)
        
        # === CLINICAL DRUG GROUPS (SCDG) ===
        scdg_ids = self.get_related_by_type(ingredient_id, 'has_ingredient', 'out', 'ClinicalDrugGroup')
        for scdg_id in scdg_ids:
            scdg_props = self.get_entity_props(scdg_id)
            profile['clinical_drug_groups'].append({
                'id': scdg_id,
                'name': self.get_entity_name(scdg_id),
                'rxcui': scdg_props.get('rxcui'),
            })
        
        # === CLINICAL DRUGS (SCD) ===
        scd_ids_seen = set()
        for scdc_id in scdc_ids:
            scd_ids = self.get_related_by_type(scdc_id, 'consists_of', 'out', 'ClinicalDrug')
            for scd_id in scd_ids:
                if scd_id in scd_ids_seen:
                    continue
                scd_ids_seen.add(scd_id)
                scd_props = self.get_entity_props(scd_id)
                profile['clinical_drugs'].append({
                    'id': scd_id,
                    'name': self.get_entity_name(scd_id),
                    'rxcui': scd_props.get('rxcui'),
                })
        
        # === SEMANTIC BRANDED DRUGS (SBD) ===
        sbd_ids_seen = set()
        sbd_to_ndcs = {}
        sbd_to_pis = {}
        
        for scdc_id in scdc_ids:
            sbd_ids = self.get_related_by_type(scdc_id, 'consists_of', 'out', 'BrandedDrug')
            for sbd_id in sbd_ids:
                if sbd_id in sbd_ids_seen:
                    continue
                sbd_ids_seen.add(sbd_id)
                sbd_props = self.get_entity_props(sbd_id)
                
                sbd_record = {
                    'id': sbd_id,
                    'name': self.get_entity_name(sbd_id),
                    'rxcui': sbd_props.get('rxcui'),
                    'ndcs': [],
                    'package_inserts': [],
                }
                
                # Get NDCs
                ndc_ids = self.get_related_by_type(sbd_id, 'maps_to_rxcui', 'in', 'NDC')
                for ndc_id in ndc_ids:
                    ndc_name = self.get_entity_name(ndc_id)
                    sbd_record['ndcs'].append(ndc_name)
                    if ndc_name not in profile['ndcs']:
                        profile['ndcs'].append(ndc_name)
                
                # Get Package Inserts
                pi_ids = self.get_related_by_type(sbd_id, 'maps_to_rxcui', 'in', 'PackageInsert')
                for pi_id in pi_ids:
                    pi_props = self.get_entity_props(pi_id)
                    pi_record = {
                        'id': pi_id,
                        'name': self.get_entity_name(pi_id),
                        'set_id': pi_props.get('set_id'),
                    }
                    sbd_record['package_inserts'].append(pi_record)
                    if pi_record['name'] not in [p['name'] for p in profile['package_inserts']]:
                        profile['package_inserts'].append(pi_record)
                
                profile['semantic_branded_drugs'].append(sbd_record)
        
        # === BRANDED DRUG FORMS (SBDF) ===
        sbdf_ids = self.get_related_by_type(ingredient_id, 'has_tradename', 'in', 'BrandedDrugForm')
        for sbdf_id in sbdf_ids:
            sbdf_props = self.get_entity_props(sbdf_id)
            profile['branded_drug_forms'].append({
                'id': sbdf_id,
                'name': self.get_entity_name(sbdf_id),
                'rxcui': sbdf_props.get('rxcui'),
            })
        
        # === STATISTICS ===
        profile['stats'] = {
            'brand_names': len(profile['brand_names']),
            'dose_form_types': len(profile['dose_form_types']),
            'clinical_drug_forms': len(profile['clinical_drug_forms']),
            'precise_ingredients': len(profile['precise_ingredients']),
            'multiple_ingredients': len(profile['multiple_ingredients']),
            'clinical_drug_components': len(profile['clinical_drug_components']),
            'clinical_drug_groups': len(profile['clinical_drug_groups']),
            'clinical_drugs': len(profile['clinical_drugs']),
            'semantic_branded_drugs': len(profile['semantic_branded_drugs']),
            'branded_drug_forms': len(profile['branded_drug_forms']),
            'ndcs': len(profile['ndcs']),
            'package_inserts': len(profile['package_inserts']),
            'has_pubchem': bool(profile['pubchem'].get('smiles') or profile['pubchem'].get('cid')),
        }
        
        return profile
    
    def export_profiles(self, drug_names, output_path):
        """Export profiles for multiple drugs to JSON"""
        profiles = []
        not_found = []
        
        print(f"\nExporting {len(drug_names)} drug profiles...")
        print("-" * 80)
        
        for drug_name in drug_names:
            profile = self.profile_comprehensive(drug_name)
            if profile:
                profiles.append(profile)
                stats = profile['stats']
                cid = profile['pubchem'].get('cid', 'N/A')
                print(f"  ✓ {drug_name:<20} RXCUI: {profile['ingredient']['rxcui']:<10} "
                      f"CID: {cid:<8} "
                      f"Brands: {stats['brand_names']:<3} "
                      f"DF: {stats['dose_form_types']:<2} "
                      f"SCD: {stats['clinical_drugs']:<3} "
                      f"SBD: {stats['semantic_branded_drugs']:<3} "
                      f"NDCs: {stats['ndcs']:<4}")
            else:
                not_found.append(drug_name)
                print(f"  ✗ {drug_name:<20} (not found)")
        
        # Build output structure
        output = {
            'generated_at': datetime.now().isoformat(),
            'profile_version': '1.0',
            'total_drugs': len(profiles),
            'drugs_not_found': not_found,
            'profiles': profiles,
            'summary': {
                'total_brand_names': sum(p['stats']['brand_names'] for p in profiles),
                'total_dose_form_types': sum(p['stats']['dose_form_types'] for p in profiles),
                'total_clinical_drug_forms': sum(p['stats']['clinical_drug_forms'] for p in profiles),
                'total_clinical_drugs': sum(p['stats']['clinical_drugs'] for p in profiles),
                'total_semantic_branded_drugs': sum(p['stats']['semantic_branded_drugs'] for p in profiles),
                'total_ndcs': sum(p['stats']['ndcs'] for p in profiles),
                'total_package_inserts': sum(p['stats']['package_inserts'] for p in profiles),
                'drugs_with_pubchem': sum(1 for p in profiles if p['stats']['has_pubchem']),
            }
        }
        
        # Write to JSON
        with open(output_path, 'w') as f:
            json.dump(output, f, indent=2)
        
        print("-" * 80)
        print(f"\nExported {len(profiles)} profiles to: {output_path}")
        
        # Print summary
        print("\n" + "=" * 100)
        print("EXPORT SUMMARY")
        print("=" * 100)
        print(f"  Total Drugs:           {output['summary']['total_drugs']}")
        print(f"  Total Brand Names:     {output['summary']['total_brand_names']}")
        print(f"  Total Dose Forms:      {output['summary']['total_dose_form_types']}")
        print(f"  Total Clinical Drugs:  {output['summary']['total_clinical_drugs']}")
        print(f"  Total Branded Drugs:   {output['summary']['total_semantic_branded_drugs']}")
        print(f"  Total NDCs:            {output['summary']['total_ndcs']}")
        print(f"  Total Package Inserts: {output['summary']['total_package_inserts']}")
        print(f"  Drugs with PubChem:    {output['summary']['drugs_with_pubchem']}")
        
        if not_found:
            print(f"\nDrugs not found: {', '.join(not_found)}")
        
        return output


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Export drug profiles to JSON')
    parser.add_argument('--output', '-o', default='demo_drug_profiles.json', help='Output JSON file')
    parser.add_argument('--drugs', '-d', help='Comma-separated list of drugs (default: 10 demo drugs)')
    parser.add_argument('--all-enriched', action='store_true', help='Export all enriched ingredients')
    args = parser.parse_args()
    
    exporter = DrugProfileExporter()
    
    if args.all_enriched:
        # Get all enriched ingredients
        ingredient_type = exporter.schema.types.get('Ingredient')
        smiles_prop = exporter.schema.properties.get('smiles')
        drug_names = []
        
        for eid, entity in exporter.entities.items():
            if ingredient_type in entity.get('types', []):
                for v in entity.get('values', []):
                    if v.get('property') == smiles_prop:
                        drug_names.append(entity.get('name', ''))
                        break
        
        drug_names = sorted(set(drug_names))
        print(f"Found {len(drug_names)} enriched ingredients")
    elif args.drugs:
        drug_names = [d.strip() for d in args.drugs.split(',')]
    else:
        drug_names = DEFAULT_DRUGS
    
    # Ensure output directory exists
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / args.output
    
    exporter.export_profiles(drug_names, output_path)


if __name__ == '__main__':
    main()
