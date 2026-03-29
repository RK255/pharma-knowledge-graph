#!/usr/bin/env python3
"""
Pharma Knowledge Graph Schema v4.2
==================================

GRC-20 compliant schema aligned with RxNorm TTY structure.

Key Changes from v3:
- Renamed "attribute" → "property" for GRC-20 terminology alignment
- Changed ID format from Base58 → UUID (RFC 4122, non-hyphenated)
- Added predefined provenance sources with runtime date fill
- Added CSV export for ontology (human review)
- Added JSONL export for data (SDK import)
"""

import json
import csv
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
# GRC-20 Type UUIDs (from schema_cache.json)
PROVENANCE_TYPE = "4f209cfaa9065ab09544fb83a601f297"
HAS_PROVENANCE_RELATION = "40336b51fbf358408ee0cbcc808d43b6"


# =============================================================================
# GRC-20 STANDARD IDS (from spec - these are FIXED, non-hyphenated)
# =============================================================================

GRC20_STANDARD_PROPERTY_IDS = {
    "name": "a126ca530c8e48d5b88882c734c38935",
    "description": "9b1f76ff9711404c861e59dc3fa7d037",
}
# =============================================================================
# SECTION RELATION IDS (from typed_section_schema_additions.json)
# =============================================================================

SECTION_RELATION_IDS = {
    "has_active_ingredients_section": "d6b59ffc2a805784a427b85c1baf2369",
    "active_ingredients_section_of": "599de9cfba2c58ed9df893796658e380",
    "has_adverse_reactions_section": "243c46c8c18a521da8db4e6b3e76f4ec",
    "adverse_reactions_section_of": "68b70d2636835b9e8a1f5153d18bea3b",
    "has_boxed_warning_section": "de8e3141f1845f49b06e12c8367b3cb1",
    "boxed_warning_section_of": "6c32eab146f056e490a08624a5e2a865",
    "has_clinical_pharmacology_section": "6acfe22495035f02b99be8479f56965e",
    "clinical_pharmacology_section_of": "0d81e408a95059138e5b23ec09e88d3b",
    "has_clinical_studies_section": "fa740a7f28cf55ddaf01a324e7c08801",
    "clinical_studies_section_of": "89cfbdfa112c5ce4a20b9dbd5ba65ae0",
    "has_components_section": "8676c521e91b5f7aab7f75d0e93ceeab",
    "components_section_of": "5adcc7d4a3455bfd88407c4936d7a0a1",
    "has_contraindications_section": "df8f55b086765bcda3fa761729cd0e9b",
    "contraindications_section_of": "87fc3447926f5c848f210fe174d2997e",
    "has_description_section": "a4f129c1e4515ef2a80cbbb9ff22dad6",
    "description_section_of": "f26d523a3bdf5112bea1a70518a70af4",
    "has_dosage_and_administration_section": "9c7ccb0ab4825b93a84586bf467bf087",
    "dosage_and_administration_section_of": "c55a2cb6ccd955508d6e4a3c7027f1b5",
    "has_dosage_forms_and_strengths_section": "f21ada2e4b8758b6a08f6330b66589c7",
    "dosage_forms_and_strengths_section_of": "e818a1c591055ff985c8c9b328592dec",
    "has_drug_abuse_and_dependence_section": "c625228516af5bf7969adc354e9bd659",
    "drug_abuse_and_dependence_section_of": "2b1a2a91faea54a6aa5621eac85215fa",
    "has_drug_interactions_section": "32ad7d82e4315963a2af77468f926957",
    "drug_interactions_section_of": "2cff4257b1245e3c84a555bb4979c9e9",
    "has_how_supplied_section": "bf05c35764285b87a4d87b5a4bcca531",
    "how_supplied_section_of": "0242f467a92e5eaab89e96cb4de96e27",
    "has_inactive_ingredients_section": "5a8925175b395c78b275a14eb7cc93ff",
    "inactive_ingredients_section_of": "e27840649909566c8f65315177480243",
    "has_indications_and_usage_section": "280bc9899ecb5e19940ffae0c7b6f982",
    "indications_and_usage_section_of": "9c2335fca610575392387662477afb8b",
    "has_information_for_caregivers_section": "cdbd91e4ac5b59f4b595510ca1a92f52",
    "information_for_caregivers_section_of": "e4490cd8c154515abd24e7aa26c7a9c1",
    "has_information_for_patients_section": "2b0d420bc7b953fabd89e10cb3eabeec",
    "information_for_patients_section_of": "4c886f340ecb5416ab34af9decfb461b",
    "has_nonclinical_toxicology_section": "1c25429d42205d12b632b4dd2924eeb7",
    "nonclinical_toxicology_section_of": "3581277da7ad5cfdafd415f652c99822",
    "has_nonteratogenic_effects_section": "cd67fafc057b59d39540460657761394",
    "nonteratogenic_effects_section_of": "23e85e2ddbb8537e952550b29bca0d21",
    "has_otc_ask_doctor_section": "927849bc98245511a99a312b74ef7f1b",
    "otc_ask_doctor_section_of": "845c8fcf7e7c538e891208e2364cf6dc",
    "has_otc_do_not_use_section": "8dc76c9c4e975ba9a6855468610f5845",
    "otc_do_not_use_section_of": "a31ce147ccd754709c3b74bf986efc14",
    "has_otc_keep_out_of_reach_section": "40d4392ecf895dc99e704c00579bba9a",
    "otc_keep_out_of_reach_section_of": "7599e167b9b3583aa8db228c459615ff",
    "has_otc_purpose_section": "3600c193b5fe562c93fd4b4eae569fb4",
    "otc_purpose_section_of": "f81dc9cec5e9534c968761dabc6c5f88",
    "has_otc_questions_section": "425894e6839959c58ecd6b48e35af516",
    "otc_questions_section_of": "241a62937bfc5c08884995fb28e9ae60",
    "has_otc_stop_use_section": "620378ccbc195bd490ca162abe5b11a7",
    "otc_stop_use_section_of": "d4c69d7d28935d2dbcbd16084c0ddda2",
    "has_otc_when_using_section": "74aa9cfddc7e5511baa111ffdfc6267e",
    "otc_when_using_section_of": "ac3b04cd5c5b5f0f95fa9bdeca490856",
    "has_other_safety_info_section": "1e64718308e652b490d3dd93ca3a0241",
    "other_safety_info_section_of": "f505376f12715c09bf6639d07781ea24",
    "has_overdosage_section": "018dafb5ce8557299146c5748d2c688f",
    "overdosage_section_of": "13882c8ee9ec5e1cb6ee9dfd4a665b4b",
    "has_recent_major_changes_section": "e112c8f2de3953aba73c42e44bc4a096",
    "recent_major_changes_section_of": "1499657e9602564890c0386d46a09c3a",
    "has_references_section": "202f02c441b755978f16b7b5ef24a3bb",
    "references_section_of": "f6d6147a1bf150838dabbd8bbd4e9e1c",
    "has_risks_section": "30abfbdedfde5afa8b281ae04f885184",
    "risks_section_of": "9d60e3a2afd1567295dfc42f2523374b",
    "has_safe_handling_warning_section": "ca28a1e6a7ae5608802d5042c961f239",
    "safe_handling_warning_section_of": "2eee53a95f0b571ea1147f27d35afc7e",
    "has_teratogenic_effects_section": "28b2af5c5a675e6da31cd67d2e70dce2",
    "teratogenic_effects_section_of": "3af6f8717a3a545ebb218a2040aa0c71",
    "has_use_in_specific_populations_section": "aea7497ddc5755d492646db3ff1a7b14",
    "use_in_specific_populations_section_of": "75b5d000d4c654f3bc670b775887e39e",
    "has_warnings_and_precautions_section": "0b907638163c51a2ac86d093257bc16c",
    "warnings_and_precautions_section_of": "949cff126f635f22a27fa6c268cd4f18",
}

# =============================================================================
# PREDEFINED PROVENANCE SOURCES
# =============================================================================

PROVENANCE_SOURCES = {
    "RxNorm": {
        "name": "RxNorm",
        "citation_template": "RxNorm [Internet]. Bethesda (MD): National Library of Medicine (US); [cited {date}]. Available from: https://rxnorm.nlm.nih.gov/",
        "source_url": "https://rxnorm.nlm.nih.gov/",
        "provenance_type": "IMPORTED",
    },
    "PubChem": {
        "name": "PubChem",
        "citation_template": "PubChem [Internet]. Bethesda (MD): National Library of Medicine (US); [cited {date}]. Available from: https://pubchem.ncbi.nlm.nih.gov/",
        "source_url": "https://pubchem.ncbi.nlm.nih.gov/",
        "provenance_type": "IMPORTED",
    },
    "DailyMed": {
        "name": "DailyMed",
        "citation_template": "DailyMed [Internet]. Bethesda (MD): National Library of Medicine (US); [cited {date}]. Available from: https://dailymed.nlm.nih.gov/",
        "source_url": "https://dailymed.nlm.nih.gov/",
        "provenance_type": "IMPORTED",
    },
}

# =============================================================================
# RXNORM TTY TO ENTITY TYPE MAPPING
# =============================================================================

TTY_TO_ENTITY_TYPE = {
    "IN":   "Ingredient",
    "PIN":  "PreciseIngredient",
    "MIN":  "MultipleIngredient",
    "SU":   "SpecificSubstance",
    "SCDC": "ClinicalDrugComponent",
    "SCDF": "ClinicalDrugForm",
    "SCDG": "ClinicalDrugGroup",
    "SCDGP":"ClinicalDrugGroupPrecise",
    "SCD":  "ClinicalDrug",
    "SBDC": "BrandedDrugComponent",
    "SBDF": "BrandedDrugForm",
    "SBDG": "BrandedDrugGroup",
    "SBD":  "BrandedDrug",
    "BN":   "BrandName",
    "DF":   "DoseForm",
    "DFG":  "DoseFormGroup",
    "GPCK": "GenericPack",
    "BPCK": "BrandPack",
    "PSN":  "PrescribableName",
    "SY":   "Synonym",
    "TMSY": "TallManSynonym",
    "DP":   "DrugProduct",
    "MTH_RXN_DP": "MTHDrugProduct",
}

# =============================================================================
# ENTITY TYPE DEFINITIONS
# =============================================================================

ENTITY_TYPES = {
    # RxNorm TTY-based types
    "Ingredient": {"description": "Active pharmaceutical ingredient (IN)", "tty": "IN"},
    "PreciseIngredient": {"description": "Precise ingredient - salt form (PIN)", "tty": "PIN"},
    "MultipleIngredient": {"description": "Multiple ingredient combination (MIN)", "tty": "MIN"},
    "SpecificSubstance": {"description": "Specific substance (SU)", "tty": "SU"},
    "ClinicalDrugComponent": {"description": "Semantic Clinical Drug Component (SCDC)", "tty": "SCDC"},
    "ClinicalDrugForm": {"description": "Semantic Clinical Drug Form (SCDF)", "tty": "SCDF"},
    "ClinicalDrugGroup": {"description": "Semantic Clinical Drug Group (SCDG)", "tty": "SCDG"},
    "ClinicalDrugGroupPrecise": {"description": "Semantic Clinical Drug Group Precise (SCDGP)", "tty": "SCDGP"},
    "ClinicalDrug": {"description": "Semantic Clinical Drug (SCD)", "tty": "SCD"},
    "BrandedDrugComponent": {"description": "Semantic Branded Drug Component (SBDC)", "tty": "SBDC"},
    "BrandedDrugForm": {"description": "Semantic Branded Drug Form (SBDF)", "tty": "SBDF"},
    "BrandedDrugGroup": {"description": "Semantic Branded Drug Group (SBDG)", "tty": "SBDG"},
    "BrandedDrug": {"description": "Semantic Branded Drug (SBD)", "tty": "SBD"},
    "BrandName": {"description": "Brand name for a drug (BN)", "tty": "BN"},
    "DoseForm": {"description": "Dosage form (DF)", "tty": "DF"},
    "DoseFormGroup": {"description": "Dose form group (DFG)", "tty": "DFG"},
    "GenericPack": {"description": "Generic pack (GPCK)", "tty": "GPCK"},
    "BrandPack": {"description": "Brand pack (BPCK)", "tty": "BPCK"},
    "PrescribableName": {"description": "Prescribable name (PSN)", "tty": "PSN"},
    "Synonym": {"description": "Synonym (SY)", "tty": "SY"},
    "TallManSynonym": {"description": "Tall man synonym (TMSY)", "tty": "TMSY"},
    "DrugProduct": {"description": "Drug product (NDDF DP)", "tty": "DP"},
    "MTHDrugProduct": {"description": "MTH drug product", "tty": "MTH_RXN_DP"},
    
    # Non-RxNorm types
    "PackageInsert": {"description": "FDA drug label/package insert document", "tty": None},
    "Manufacturer": {"description": "Drug manufacturer or labeler company", "tty": None},
    "NDC": {"description": "National Drug Code identifier", "tty": None},
    "Provenance": {"description": "Data source provenance", "tty": None},
    "Section": {"description": "Document section (e.g., drug label section)", "tty": None},
    "DrugClass": {"description": "Drug classification or category", "tty": None},
    "Relation": {"description": "GRC-20 relation entity (edge between nodes)", "tty": None},
    "PubChemCompound": {"description": "PubChem chemical compound entry", "tty": None},
}

# =============================================================================
# PROPERTY DEFINITIONS (renamed from ATTRIBUTES)
# =============================================================================

PROPERTIES = {
    # Core properties
    "name": {"value_type": "TEXT", "description": "Primary name or label"},
    "description": {"value_type": "TEXT", "description": "Description or summary text"},
    "rxcui": {"value_type": "TEXT", "description": "RxNorm Concept Unique Identifier"},
    "tty": {"value_type": "TEXT", "description": "RxNorm Term Type"},
    
    # Relation properties
    "rela_code": {"value_type": "TEXT", "description": "Raw RxNorm relationship code (RO/RN/RB)"},
    "source_tty": {"value_type": "TEXT", "description": "Source term type for relationship"},
    "target_tty": {"value_type": "TEXT", "description": "Target term type for relationship"},
    
    # Chemical properties
    "pubchem_cid": {"value_type": "NUMBER", "description": "PubChem Compound ID"},
    "mesh_classes": {"value_type": "TEXT", "description": "MeSH classification codes"},
    "smiles": {"value_type": "TEXT", "description": "SMILES molecular structure"},
    "inchikey": {"value_type": "TEXT", "description": "InChIKey identifier"},
    "iupac_name": {"value_type": "TEXT", "description": "IUPAC systematic name"},
    "iupac_name": {"value_type": "TEXT", "description": "IUPAC systematic name"},
    "molecular_formula": {"value_type": "TEXT", "description": "Molecular formula"},
    "molecular_weight": {"value_type": "NUMBER", "description": "Molecular weight in Daltons"},
    
    # DailyMed / Package Insert properties
    "ndc_code": {"value_type": "TEXT", "description": "National Drug Code"},
    "fda_set_id": {"value_type": "TEXT", "description": "FDA SET ID for package insert"},
    "effective_time": {"value_type": "TIME", "description": "Effective date/time of drug label"},
    "content": {"value_type": "TEXT", "description": "Text content of a document section"},
    "set_id": {"value_type": "TEXT", "description": "Unique identifier for document set"},
    
    # PubChem properties
    "pubchem_date": {"value_type": "TIME", "description": "PubChem data retrieval date"},
    "pmid": {"value_type": "TEXT", "description": "PubMed ID reference"},
    "sid": {"value_type": "TEXT", "description": "PubChem Substance ID"},
    "mesh_classes": {"value_type": "TEXT", "description": "MeSH classification codes"},
    
    # Provenance properties
    "source": {"value_type": "TEXT", "description": "Data source name"},
    "citation": {"value_type": "TEXT", "description": "Citation for data source"},
    "date_accessed": {"value_type": "TIME", "description": "Date data was accessed"},
    "source_url": {"value_type": "URL", "description": "URL to data source"},
    "provenance_type": {"value_type": "TEXT", "description": "Type of provenance: AUTOMATED, EXPERT, INFERRED, IMPORTED"},
    
    # Section properties
    "section_type": {"value_type": "TEXT", "description": "Type of document section"},
    "sequence": {"value_type": "NUMBER", "description": "Order sequence"},
    
    # Drug classification
    "class_name": {"value_type": "TEXT", "description": "Drug class name"},
    "class_type": {"value_type": "TEXT", "description": "Classification system (ATC, MeSH, etc.)"},
    "class_code": {"value_type": "TEXT", "description": "Classification code"},
    
    # Clinical properties
    "clinical_weight": {"value_type": "NUMBER", "description": "Weighted clinical relationship"},
    "evidence": {"value_type": "TEXT", "description": "Evidence supporting a clinical relationship"},
}

# =============================================================================
# RELATION TYPE DEFINITIONS
# =============================================================================

RELATION_TYPES = {
    # Document structure
    "has_section": {"description": "Package insert has this section", "inverse": "section_of"},
    "section_of": {"description": "Section belongs to this package insert", "inverse": "has_section"},
    "manufactured_by": {"description": "Package insert manufactured by this company", "inverse": "manufactures"},
    "manufactures": {"description": "Manufacturer produces this drug product", "inverse": "manufactured_by"},
    
    # Ingredient relationships
    "has_ingredient": {"description": "Drug has this ingredient", "inverse": "ingredient_of"},
    "ingredient_of": {"description": "Ingredient is in this drug", "inverse": "has_ingredient"},
    "has_precise_ingredient": {"description": "Drug has this precise ingredient (salt form)", "inverse": "precise_ingredient_of"},
    "precise_ingredient_of": {"description": "Precise ingredient is in this drug", "inverse": "has_precise_ingredient"},
    "has_ingredients": {"description": "Multiple ingredients drug has", "inverse": "ingredients_of"},
    "ingredients_of": {"description": "Ingredients are in this multiple ingredient drug", "inverse": "has_ingredients"},
    
    # Dose form relationships
    "has_dose_form": {"description": "Drug has this dose form", "inverse": "dose_form_of"},
    "dose_form_of": {"description": "Dose form is used by this drug", "inverse": "has_dose_form"},
    "has_doseformgroup": {"description": "Drug belongs to this dose form group", "inverse": "doseformgroup_of"},
    "doseformgroup_of": {"description": "Dose form group contains this drug", "inverse": "has_doseformgroup"},
    
    # Brand relationships
    "has_tradename": {"description": "Drug has this brand/trade name", "inverse": "tradename_of"},
    "tradename_of": {"description": "Brand name is for this drug", "inverse": "has_tradename"},
    
    # Taxonomy relationships
    "is_a": {"description": "Entity is a subtype of", "inverse": "inverse_isa"},
    "inverse_isa": {"description": "Entity is a supertype of", "inverse": "is_a"},
    
    # Component relationships
    "consists_of": {"description": "Drug consists of these components", "inverse": "constitutes"},
    "constitutes": {"description": "Component constitutes this drug", "inverse": "consists_of"},
    "contains": {"description": "Pack contains this drug", "inverse": "contained_in"},
    "contained_in": {"description": "Drug is contained in this pack", "inverse": "contains"},
    "has_part": {"description": "Entity has this part", "inverse": "part_of"},
    "part_of": {"description": "Entity is part of this", "inverse": "has_part"},
    
    # Form relationships
    "has_form": {"description": "Drug has this form (salt form)", "inverse": "form_of"},
    "form_of": {"description": "Form is of this drug", "inverse": "has_form"},
    "reformulated_to": {"description": "Drug was reformulated to this", "inverse": "reformulation_of"},
    "reformulation_of": {"description": "Drug is a reformulation of this", "inverse": "reformulated_to"},
    "has_quantified_form": {"description": "Drug has this quantified form", "inverse": "quantified_form_of"},
    "quantified_form_of": {"description": "Quantified form is of this drug", "inverse": "has_quantified_form"},
    
    # Boss relationships
    "has_boss": {"description": "Drug has this boss (active moiety)", "inverse": "boss_of"},
    "boss_of": {"description": "Boss (active moiety) of this drug", "inverse": "has_boss"},
    
    # Equivalence
    "equivalent_to": {"description": "Entity is equivalent to", "inverse": "equivalent_to"},
    

    # Section relations (DailyMed typed sections)
    # Auto-generated from typed_section_schema_additions.json
    "has_active_ingredients_section": {"description": "Package insert has Active Ingredients section", "inverse": "active_ingredients_section_of"},
    "active_ingredients_section_of": {"description": "Active Ingredients section of package insert", "inverse": "has_active_ingredients_section"},
    "has_adverse_reactions_section": {"description": "Package insert has Adverse Reactions section", "inverse": "adverse_reactions_section_of"},
    "adverse_reactions_section_of": {"description": "Adverse Reactions section of package insert", "inverse": "has_adverse_reactions_section"},
    "has_boxed_warning_section": {"description": "Package insert has Boxed Warning section", "inverse": "boxed_warning_section_of"},
    "boxed_warning_section_of": {"description": "Boxed Warning section of package insert", "inverse": "has_boxed_warning_section"},
    "has_clinical_pharmacology_section": {"description": "Package insert has Clinical Pharmacology section", "inverse": "clinical_pharmacology_section_of"},
    "clinical_pharmacology_section_of": {"description": "Clinical Pharmacology section of package insert", "inverse": "has_clinical_pharmacology_section"},
    "has_clinical_studies_section": {"description": "Package insert has Clinical Studies section", "inverse": "clinical_studies_section_of"},
    "clinical_studies_section_of": {"description": "Clinical Studies section of package insert", "inverse": "has_clinical_studies_section"},
    "has_components_section": {"description": "Package insert has Components section", "inverse": "components_section_of"},
    "components_section_of": {"description": "Components section of package insert", "inverse": "has_components_section"},
    "has_contraindications_section": {"description": "Package insert has Contraindications section", "inverse": "contraindications_section_of"},
    "contraindications_section_of": {"description": "Contraindications section of package insert", "inverse": "has_contraindications_section"},
    "has_description_section": {"description": "Package insert has Description section", "inverse": "description_section_of"},
    "description_section_of": {"description": "Description section of package insert", "inverse": "has_description_section"},
    "has_dosage_and_administration_section": {"description": "Package insert has Dosage And Administration section", "inverse": "dosage_and_administration_section_of"},
    "dosage_and_administration_section_of": {"description": "Dosage And Administration section of package insert", "inverse": "has_dosage_and_administration_section"},
    "has_dosage_forms_and_strengths_section": {"description": "Package insert has Dosage Forms And Strengths section", "inverse": "dosage_forms_and_strengths_section_of"},
    "dosage_forms_and_strengths_section_of": {"description": "Dosage Forms And Strengths section of package insert", "inverse": "has_dosage_forms_and_strengths_section"},
    "has_drug_abuse_and_dependence_section": {"description": "Package insert has Drug Abuse And Dependence section", "inverse": "drug_abuse_and_dependence_section_of"},
    "drug_abuse_and_dependence_section_of": {"description": "Drug Abuse And Dependence section of package insert", "inverse": "has_drug_abuse_and_dependence_section"},
    "has_drug_interactions_section": {"description": "Package insert has Drug Interactions section", "inverse": "drug_interactions_section_of"},
    "drug_interactions_section_of": {"description": "Drug Interactions section of package insert", "inverse": "has_drug_interactions_section"},
    "has_how_supplied_section": {"description": "Package insert has How Supplied section", "inverse": "how_supplied_section_of"},
    "how_supplied_section_of": {"description": "How Supplied section of package insert", "inverse": "has_how_supplied_section"},
    "has_inactive_ingredients_section": {"description": "Package insert has Inactive Ingredients section", "inverse": "inactive_ingredients_section_of"},
    "inactive_ingredients_section_of": {"description": "Inactive Ingredients section of package insert", "inverse": "has_inactive_ingredients_section"},
    "has_indications_and_usage_section": {"description": "Package insert has Indications And Usage section", "inverse": "indications_and_usage_section_of"},
    "indications_and_usage_section_of": {"description": "Indications And Usage section of package insert", "inverse": "has_indications_and_usage_section"},
    "has_information_for_caregivers_section": {"description": "Package insert has Information For Caregivers section", "inverse": "information_for_caregivers_section_of"},
    "information_for_caregivers_section_of": {"description": "Information For Caregivers section of package insert", "inverse": "has_information_for_caregivers_section"},
    "has_information_for_patients_section": {"description": "Package insert has Information For Patients section", "inverse": "information_for_patients_section_of"},
    "information_for_patients_section_of": {"description": "Information For Patients section of package insert", "inverse": "has_information_for_patients_section"},
    "has_nonclinical_toxicology_section": {"description": "Package insert has Nonclinical Toxicology section", "inverse": "nonclinical_toxicology_section_of"},
    "nonclinical_toxicology_section_of": {"description": "Nonclinical Toxicology section of package insert", "inverse": "has_nonclinical_toxicology_section"},
    "has_nonteratogenic_effects_section": {"description": "Package insert has Nonteratogenic Effects section", "inverse": "nonteratogenic_effects_section_of"},
    "nonteratogenic_effects_section_of": {"description": "Nonteratogenic Effects section of package insert", "inverse": "has_nonteratogenic_effects_section"},
    "has_otc_ask_doctor_section": {"description": "Package insert has Otc Ask Doctor section", "inverse": "otc_ask_doctor_section_of"},
    "otc_ask_doctor_section_of": {"description": "Otc Ask Doctor section of package insert", "inverse": "has_otc_ask_doctor_section"},
    "has_otc_do_not_use_section": {"description": "Package insert has Otc Do Not Use section", "inverse": "otc_do_not_use_section_of"},
    "otc_do_not_use_section_of": {"description": "Otc Do Not Use section of package insert", "inverse": "has_otc_do_not_use_section"},
    "has_otc_keep_out_of_reach_section": {"description": "Package insert has Otc Keep Out Of Reach section", "inverse": "otc_keep_out_of_reach_section_of"},
    "otc_keep_out_of_reach_section_of": {"description": "Otc Keep Out Of Reach section of package insert", "inverse": "has_otc_keep_out_of_reach_section"},
    "has_otc_purpose_section": {"description": "Package insert has Otc Purpose section", "inverse": "otc_purpose_section_of"},
    "otc_purpose_section_of": {"description": "Otc Purpose section of package insert", "inverse": "has_otc_purpose_section"},
    "has_otc_questions_section": {"description": "Package insert has Otc Questions section", "inverse": "otc_questions_section_of"},
    "otc_questions_section_of": {"description": "Otc Questions section of package insert", "inverse": "has_otc_questions_section"},
    "has_otc_stop_use_section": {"description": "Package insert has Otc Stop Use section", "inverse": "otc_stop_use_section_of"},
    "otc_stop_use_section_of": {"description": "Otc Stop Use section of package insert", "inverse": "has_otc_stop_use_section"},
    "has_otc_when_using_section": {"description": "Package insert has Otc When Using section", "inverse": "otc_when_using_section_of"},
    "otc_when_using_section_of": {"description": "Otc When Using section of package insert", "inverse": "has_otc_when_using_section"},
    "has_other_safety_info_section": {"description": "Package insert has Other Safety Info section", "inverse": "other_safety_info_section_of"},
    "other_safety_info_section_of": {"description": "Other Safety Info section of package insert", "inverse": "has_other_safety_info_section"},
    "has_overdosage_section": {"description": "Package insert has Overdosage section", "inverse": "overdosage_section_of"},
    "overdosage_section_of": {"description": "Overdosage section of package insert", "inverse": "has_overdosage_section"},
    "has_recent_major_changes_section": {"description": "Package insert has Recent Major Changes section", "inverse": "recent_major_changes_section_of"},
    "recent_major_changes_section_of": {"description": "Recent Major Changes section of package insert", "inverse": "has_recent_major_changes_section"},
    "has_references_section": {"description": "Package insert has References section", "inverse": "references_section_of"},
    "references_section_of": {"description": "References section of package insert", "inverse": "has_references_section"},
    "has_risks_section": {"description": "Package insert has Risks section", "inverse": "risks_section_of"},
    "risks_section_of": {"description": "Risks section of package insert", "inverse": "has_risks_section"},
    "has_safe_handling_warning_section": {"description": "Package insert has Safe Handling Warning section", "inverse": "safe_handling_warning_section_of"},
    "safe_handling_warning_section_of": {"description": "Safe Handling Warning section of package insert", "inverse": "has_safe_handling_warning_section"},
    "has_teratogenic_effects_section": {"description": "Package insert has Teratogenic Effects section", "inverse": "teratogenic_effects_section_of"},
    "teratogenic_effects_section_of": {"description": "Teratogenic Effects section of package insert", "inverse": "has_teratogenic_effects_section"},
    "has_use_in_specific_populations_section": {"description": "Package insert has Use In Specific Populations section", "inverse": "use_in_specific_populations_section_of"},
    "use_in_specific_populations_section_of": {"description": "Use In Specific Populations section of package insert", "inverse": "has_use_in_specific_populations_section"},
    "has_warnings_and_precautions_section": {"description": "Package insert has Warnings And Precautions section", "inverse": "warnings_and_precautions_section_of"},
    "warnings_and_precautions_section_of": {"description": "Warnings And Precautions section of package insert", "inverse": "has_warnings_and_precautions_section"},

    # NDC mapping
    "maps_to_rxcui": {"description": "NDC maps to this RxCUI", "inverse": "mapped_from_ndc"},
    "mapped_from_ndc": {"description": "RxCUI is mapped from this NDC", "inverse": "maps_to_rxcui"},
    
    # Provenance
    "has_provenance": {"description": "Entity has provenance information", "inverse": None},
    
    # PubChem
    "has_pubchem": {"description": "Entity links to PubChem compound", "inverse": None},
    
    # TTY-based relationships
    "has_component": {"description": "Ingredient has clinical drug component", "inverse": "ingredient_of"},
    "has_group": {"description": "Ingredient has clinical drug group", "inverse": "group_of"},
    "group_of": {"description": "Clinical drug group of this ingredient", "inverse": "has_group"},
    "has_clinical_drug": {"description": "Component/form/group has clinical drug", "inverse": "clinical_drug_of"},
    "clinical_drug_of": {"description": "Clinical drug of this component", "inverse": "has_clinical_drug"},
    "has_branded_drug": {"description": "Clinical drug has branded drug", "inverse": "branded_drug_of"},
    "branded_drug_of": {"description": "Branded drug of this clinical drug", "inverse": "has_branded_drug"},
    "has_branded_component": {"description": "Clinical component has branded component", "inverse": "branded_component_of"},
    "branded_component_of": {"description": "Branded component of this clinical component", "inverse": "has_branded_component"},
    "has_branded_form": {"description": "Clinical form has branded form", "inverse": "branded_form_of"},
    "branded_form_of": {"description": "Branded form of this clinical form", "inverse": "has_branded_form"},
    "has_branded_group": {"description": "Clinical group has branded group", "inverse": "branded_group_of"},
    "branded_group_of": {"description": "Branded group of this clinical group", "inverse": "has_branded_group"},
    "has_brand_name": {"description": "Entity has brand name", "inverse": "brand_name_of"},
    "brand_name_of": {"description": "Brand name of this entity", "inverse": "has_brand_name"},
    "has_brand": {"description": "Branded drug has brand", "inverse": "brand_of"},
    "brand_of": {"description": "Brand of this branded drug", "inverse": "has_brand"},
    # Section relations (DailyMed typed sections)
}


def generate_uuid(seed: str = None) -> str:
    """Generate a valid RFC 4122 UUID without hyphens (GRC-20 recommended format).
    
    Args:
        seed: Optional seed string for deterministic UUID generation.
              Same seed always produces same UUID.
    
    Returns:
        UUID string in format: xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx (32 hex chars)
    """
    if seed:
        # Use UUID5 for deterministic generation from seed
        namespace = uuid.UUID('6ba7b810-9dad-11d1-80b4-00c04fd430c8')
        return str(uuid.uuid5(namespace, seed)).replace('-', '')
    else:
        return str(uuid.uuid4()).replace('-', '')


class PharmaSchema:
    """Pharma Knowledge Graph Schema v4 - GRC-20 Aligned with RxNorm TTY."""
    
    CACHE_FILE = Path(__file__).parent / "schema_cache.json"
    
    def __init__(self):
        self.types: Dict[str, str] = {}
        self.properties: Dict[str, str] = {}  # Renamed from attributes
        self.relations: Dict[str, str] = {}
        self.metadata: Dict[str, Any] = {}
        self.provenance_entities: Dict[str, str] = {}  # source_name -> entity_id
        
        if not self._load_cache():
            self._generate_ids()
            self._create_provenance_entities()
            self._save_cache()
    
    def _load_cache(self) -> bool:
        """Load schema from cache if available."""
        if not self.CACHE_FILE.exists():
            print("[INFO] No cache found. Generating new schema...")
            return False
        try:
            with open(self.CACHE_FILE, 'r') as f:
                data = json.load(f)
            self.metadata = data.get("metadata", {})
            
            # Load types from full dictionary structure
            self.types = {}
            for type_dict in data.get("types", []):
                self.types[type_dict["name"]] = type_dict["id"]
            
            # Load properties from full dictionary structure
            self.properties = {}
            for prop_dict in data.get("properties", []):
                self.properties[prop_dict["name"]] = prop_dict["id"]
            
            # Load relations from full dictionary structure
            self.relations = {}
            for rel_dict in data.get("relations", []):
                self.relations[rel_dict["name"]] = rel_dict["id"]
            
            # Load provenance entities
            self.provenance_entities = data.get("provenance_entities", {})
            
            print(f"[INFO] Loaded schema from cache: {len(self.types)} types, {len(self.properties)} properties, {len(self.relations)} relations")
            return True
        except Exception as e:
            print(f"[WARN] Cache load failed: {e}. Regenerating...")
            return False
    
    def _generate_ids(self):
        """Generate UUIDs for all schema elements."""
        self.metadata = {
            "version": "4.2.0",
            "created": datetime.now().isoformat(),
            "description": "Pharma Knowledge Graph Schema v4 - UUID-based, Property terminology",
        }
        
        # Generate type IDs
        for type_name in ENTITY_TYPES:
            self.types[type_name] = generate_uuid(seed=f"pharma_v4_type_{type_name}")
        
        # Generate property IDs (use fixed IDs for standard properties)
        for prop_name in PROPERTIES:
            if prop_name in GRC20_STANDARD_PROPERTY_IDS:
                self.properties[prop_name] = GRC20_STANDARD_PROPERTY_IDS[prop_name]
            else:
                self.properties[prop_name] = generate_uuid(seed=f"pharma_v4_prop_{prop_name}")
        
        # Generate relation type IDs
        # Use SECTION_RELATION_IDS for section relations, generate for others
        for rel_name in RELATION_TYPES:
            if rel_name in SECTION_RELATION_IDS:
                self.relations[rel_name] = SECTION_RELATION_IDS[rel_name]
            else:
                self.relations[rel_name] = generate_uuid(seed=f"pharma_v4_rel_{rel_name}")
        
        print(f"[INFO] Generated {len(self.types)} types, {len(self.properties)} properties, {len(self.relations)} relations")
    
    def _create_provenance_entities(self):
        """Create provenance entity IDs for each source."""
        for source_name in PROVENANCE_SOURCES:
            self.provenance_entities[source_name] = generate_uuid(seed=f"pharma_v4_prov_{source_name}")
    
    def _save_cache(self):
        """Save schema to cache."""
        # Build types list
        types_list = []
        for name, type_id in self.types.items():
            info = ENTITY_TYPES.get(name, {})
            types_list.append({
                "id": type_id,
                "name": name,
                "description": info.get("description", ""),
                "tty": info.get("tty"),
            })
        
        # Build properties list
        properties_list = []
        for name, prop_id in self.properties.items():
            info = PROPERTIES.get(name, {})
            properties_list.append({
                "id": prop_id,
                "name": name,
                "value_type": info.get("value_type", "TEXT"),
                "description": info.get("description", ""),
            })
        
        # Build relations list
        relations_list = []
        for name, rel_id in self.relations.items():
            info = RELATION_TYPES.get(name, {})
            relations_list.append({
                "id": rel_id,
                "name": name,
                "description": info.get("description", ""),
                "inverse": info.get("inverse"),
            })
        
        # Build provenance list
        provenance_list = []
        for source_name, source_id in self.provenance_entities.items():
            info = PROVENANCE_SOURCES[source_name]
            provenance_list.append({
                "id": source_id,
                "name": source_name,
                "citation_template": info["citation_template"],
                "source_url": info["source_url"],
                "provenance_type": info["provenance_type"],
            })
        
        data = {
            "metadata": self.metadata,
            "types": types_list,
            "properties": properties_list,
            "relations": relations_list,
            "provenance_entities": self.provenance_entities,
            "provenance_sources": provenance_list,
        }
        with open(self.CACHE_FILE, 'w') as f:
            json.dump(data, f, indent=2)
        print(f"[INFO] Schema cached to {self.CACHE_FILE}")
    
    # =========================================================================
    # HELPER METHODS
    # =========================================================================
    
    def tty_to_entity_type(self, tty: str) -> str:
        """Convert RxNorm TTY to entity type name."""
        return TTY_TO_ENTITY_TYPE.get(tty, "DrugProduct")
    
    def prop(self, name: str) -> str:
        """Get property ID by name."""
        if name in GRC20_STANDARD_PROPERTY_IDS:
            return GRC20_STANDARD_PROPERTY_IDS[name]
        if name not in self.properties:
            raise KeyError(f"Unknown property: {name}")
        return self.properties[name]
    
    def rel(self, name: str) -> str:
        """Get relation type ID by name."""
        if name not in self.relations:
            raise KeyError(f"Unknown relation: {name}")
        return self.relations[name]
    
    def type_id(self, name: str) -> str:
        """Get entity type ID by name."""
        if name not in self.types:
            raise KeyError(f"Unknown type: {name}")
        return self.types[name]
    
    # =========================================================================
    # ENTITY CREATION METHODS
    # =========================================================================
    
    def create_entity(self, entity_type: str, name: str, entity_id: Optional[str] = None,
                      rxcui: Optional[str] = None, tty: Optional[str] = None) -> dict:
        """Create an entity with GRC-20 structure.
        
        Returns:
            dict with 'id', 'name', 'types', 'values' for Geo SDK import
        """
        if entity_id is None:
            entity_id = generate_uuid()
        
        entity = {
            "id": entity_id,
            "name": name,  # Keep at top level for convenience
            "types": [self.type_id(entity_type)],
            "values": [
                {"property": self.prop("name"), "value": name}  # GRC-20 compliant
            ]
        }
        
        # Add RxNorm-specific properties if provided
        if rxcui:
            entity["values"].append({
                "property": self.prop("rxcui"),
                "value": rxcui
            })
        
        if tty:
            entity["values"].append({
                "property": self.prop("tty"),
                "value": tty
            })
        
        return entity
    
    def add_property(self, entity: dict, property_name: str, value: Any) -> dict:
        """Add a property value to an entity.
        
        Returns:
            Modified entity dict
        """
        entity["values"].append({
            "property": self.prop(property_name),
            "value": value
        })
        return entity
    
    # =========================================================================
    # RELATION CREATION METHODS
    # =========================================================================
    
    def create_relation(self, from_entity_id: str, relation_type: str, to_entity_id: str,
                        relation_id: Optional[str] = None,
                        rela_code: Optional[str] = None,
                        source_tty: Optional[str] = None,
                        target_tty: Optional[str] = None) -> dict:
        """Create a relation with GRC-20 structure.
        
        Returns:
            dict with 'id', 'type', 'from', 'to', 'values' for Geo SDK import
        """
        if relation_id is None:
            relation_id = generate_uuid()
        
        relation = {
            "id": relation_id,
            "type": self.rel(relation_type),
            "from": from_entity_id,
            "to": to_entity_id,
            "values": []
        }
        
        # Add relation attributes
        if rela_code:
            relation["values"].append({
                "property": self.prop("rela_code"),
                "value": rela_code
            })
        
        if source_tty:
            relation["values"].append({
                "property": self.prop("source_tty"),
                "value": source_tty
            })
        
        if target_tty:
            relation["values"].append({
                "property": self.prop("target_tty"),
                "value": target_tty
            })
        
        return relation
    
    # =========================================================================
    # PROVENANCE METHODS
    # =========================================================================
    
    def create_provenance_entity(
        self,
        source_name: str,
        date_accessed: str = None,
    ) -> Dict[str, Any]:
        """Create a provenance entity for a data source.
        
        Args:
            source_name: Name of the source (RxNorm, PubChem, DailyMed)
            date_accessed: Date data was accessed (defaults to today)
        
        Returns:
            Entity dict with provenance information
        """
        source_def = PROVENANCE_SOURCES.get(source_name)
        if not source_def:
            raise ValueError(f"Unknown provenance source: {source_name}")
        
        if date_accessed is None:
            date_accessed = datetime.utcnow().strftime("%Y-%m-%d")
        
        citation = source_def["citation_template"].format(date=date_accessed)
        
        return {
            "id": generate_uuid(seed=f"provenance:{source_name}:{date_accessed}"),
            "types": [self.type_id("Provenance")],
            "values": [
                {
                    "property": self.prop("name"),
                    "value": source_def["name"],
                },
                {
                    "property": self.prop("citation"),
                    "value": citation,
                },
                {
                    "property": self.prop("source_url"),
                    "value": source_def["source_url"],
                },
                {
                    "property": self.prop("date_accessed"),
                    "value": date_accessed,
                },
                {
                    "property": self.prop("provenance_type"),
                    "value": source_def["provenance_type"],
                },
            ],
        }

    def add_provenance_relation(
        self,
        from_entity_id: str,
        source_name: str,
        relation_id: Optional[str] = None,
    ) -> dict:
        """Add a provenance relation from an entity to its provenance source.
        
        Args:
            from_entity_id: The entity ID that has provenance
            source_name: Name of the provenance source (RxNorm, PubChem, DailyMed)
            relation_id: Optional relation ID (will be generated if not provided)
        
        Returns:
            dict with 'id', 'type', 'from', 'to', 'values' for Geo SDK import
        """
        # Get or create the provenance entity
        if source_name not in self.provenance_entities:
            provenance = self.create_provenance_entity(source_name)
            self.provenance_entities[source_name] = provenance["id"]
        
        to_entity_id = self.provenance_entities[source_name]
        
        if relation_id is None:
            relation_id = generate_uuid()
        
        return {
            "id": relation_id,
            "type": HAS_PROVENANCE_RELATION,
            "from": from_entity_id,
            "to": to_entity_id,
            "values": []
        }

    def export_ontology_csv(self, output_dir: Path):
        """Export ontology as CSV files for human review (Geo devs).
        
        Creates:
            - types.csv
            - properties.csv  
            - relation_types.csv
            - provenance_sources.csv
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Export types
        with open(output_dir / "types.csv", 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['id', 'name', 'description', 'tty'])
            for name, type_id in self.types.items():
                info = ENTITY_TYPES.get(name, {})
                writer.writerow([
                    type_id,
                    name,
                    info.get('description', ''),
                    info.get('tty', '')
                ])
        
        # Export properties
        with open(output_dir / "properties.csv", 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['id', 'name', 'value_type', 'description'])
            for name, prop_id in self.properties.items():
                info = PROPERTIES.get(name, {})
                writer.writerow([
                    prop_id,
                    name,
                    info.get('value_type', 'TEXT'),
                    info.get('description', '')
                ])
        
        # Export relation types
        with open(output_dir / "relation_types.csv", 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['id', 'name', 'description', 'inverse'])
            for name, rel_id in self.relations.items():
                info = RELATION_TYPES.get(name, {})
                writer.writerow([
                    rel_id,
                    name,
                    info.get('description', ''),
                    info.get('inverse', '')
                ])
        
        # Export provenance sources
        with open(output_dir / "provenance_sources.csv", 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['id', 'name', 'citation_template', 'source_url', 'provenance_type'])
            for source_name, source_id in self.provenance_entities.items():
                info = PROVENANCE_SOURCES[source_name]
                writer.writerow([
                    source_id,
                    source_name,
                    info['citation_template'],
                    info['source_url'],
                    info['provenance_type']
                ])
        
        print(f"[INFO] Ontology exported to {output_dir}/")
        print(f"  - types.csv: {len(self.types)} types")
        print(f"  - properties.csv: {len(self.properties)} properties")
        print(f"  - relation_types.csv: {len(self.relations)} relation types")
        print(f"  - provenance_sources.csv: {len(PROVENANCE_SOURCES)} sources")
    
    def export_data_jsonl(self, entities: List[dict], relations: List[dict], 
                          output_dir: Path, include_provenance: bool = True):
        """Export entities and relations to JSONL files for Geo SDK import.
        
        Args:
            entities: List of entity dicts
            relations: List of relation dicts
            output_dir: Output directory
            include_provenance: Whether to include provenance entities
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Export provenance entities
        if include_provenance:
            with open(output_dir / "provenance.jsonl", 'w', encoding='utf-8') as f:
                for source_name in PROVENANCE_SOURCES:
                    prov = self.create_provenance_entity(source_name)
                    f.write(json.dumps(prov) + '\n')
        
        # Export entities
        with open(output_dir / "entities.jsonl", 'w', encoding='utf-8') as f:
            for entity in entities:
                f.write(json.dumps(entity) + '\n')
        
        # Export relations
        with open(output_dir / 'relations.jsonl', 'w', encoding='utf-8') as f:
            for relation in relations:
                f.write(json.dumps(relation) + '\n')
        
        print(f"[INFO] Data exported to {output_dir}/")
        print(f"  - provenance.jsonl: {len(PROVENANCE_SOURCES) if include_provenance else 0} sources")
        print(f"  - entities.jsonl: {len(entities)} entities")
        print(f"  - relations.jsonl: {len(relations)} relations")
    
    def export_schema_json(self, output_path: Path):
        """Export complete schema as a single JSON file.
        
        Args:
            output_path: Output file path
        """
        # Build types list
        types_list = []
        for name, type_id in self.types.items():
            info = ENTITY_TYPES.get(name, {})
            types_list.append({
                "id": type_id,
                "name": name,
                "description": info.get("description", ""),
                "tty": info.get("tty"),
            })
        
        # Build properties list
        properties_list = []
        for name, prop_id in self.properties.items():
            info = PROPERTIES.get(name, {})
            properties_list.append({
                "id": prop_id,
                "name": name,
                "value_type": info.get("value_type", "TEXT"),
                "description": info.get("description", ""),
            })
        
        # Build relations list
        relations_list = []
        for name, rel_id in self.relations.items():
            info = RELATION_TYPES.get(name, {})
            relations_list.append({
                "id": rel_id,
                "name": name,
                "description": info.get("description", ""),
                "inverse": info.get("inverse"),
            })
        
        # Build provenance list
        provenance_list = []
        for source_name, source_id in self.provenance_entities.items():
            info = PROVENANCE_SOURCES[source_name]
            provenance_list.append({
                "id": source_id,
                "name": source_name,
                "citation_template": info["citation_template"],
                "source_url": info["source_url"],
                "provenance_type": info["provenance_type"],
            })
        
        schema = {
            "metadata": self.metadata,
            "types": types_list,
            "properties": properties_list,
            "relations": relations_list,
            "provenance_sources": provenance_list,
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(schema, f, indent=2)
        
        print(f"[INFO] Schema exported to {output_path}")


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Pharma Knowledge Graph Schema v4")
    parser.add_argument("--export-ontology", type=str, help="Export ontology CSVs to directory")
    parser.add_argument("--export-schema", type=str, help="Export schema JSON to file")
    parser.add_argument("--clear-cache", action="store_true", help="Clear schema cache and regenerate")
    args = parser.parse_args()
    
    # Clear cache if requested
    if args.clear_cache:
        cache_file = Path(__file__).parent / "schema_cache.json"
        if cache_file.exists():
            cache_file.unlink()
            print(f"[INFO] Cache cleared: {cache_file}")
    
    # Initialize schema
    schema = PharmaSchema()
    
    print(f"\n{'='*60}")
    print(f"Pharma Schema v{schema.metadata.get('version', '?.?.?')}")
    print(f"{'='*60}")
    print(f"Types: {len(schema.types)}")
    print(f"Properties: {len(schema.properties)}")
    print(f"Relations: {len(schema.relations)}")
    print(f"Provenance Sources: {len(schema.provenance_entities)}")
    
    # Show provenance entities
    print("\nProvenance Entities:")
    for source_name, entity_id in schema.provenance_entities.items():
        print(f"  {source_name}: {entity_id}")
    
    # Export ontology if requested
    if args.export_ontology:
        schema.export_ontology_csv(Path(args.export_ontology))
    
    # Export schema if requested
    if args.export_schema:
        schema.export_schema_json(Path(args.export_schema))
    
    # Test entity creation
    print("\nTest entity creation:")
    entity = schema.create_entity("Ingredient", "Acetaminophen", rxcui="161", tty="IN")
    entity = schema.add_property(entity, "smiles", "CC(=O)NC1=CC=C(C=C1)O")
    entity = schema.add_property(entity, "inchikey", "RZVAJINKPMORJF-UHFFFAOYSA-N")
    print(f"  Entity ID: {entity['id']}")
    print(f"  Name: {entity['name']}")
    print(f"  Types: {entity['types']}")
    print(f"  Values: {len(entity['values'])}")
    
    # Test relation creation
    print("\nTest relation creation:")
    relation = schema.create_relation(
        from_entity_id="test-drug-id",
        relation_type="has_ingredient",
        to_entity_id=entity['id'],
        rela_code="RO",
        source_tty="SCD",
        target_tty="IN"
    )
    print(f"  Relation ID: {relation['id']}")
    print(f"  Type: {relation['type']}")
    print(f"  From → To: {relation['from'][:8]}... → {relation['to'][:8]}...")
    
    # Test provenance
    print("\nTest provenance:")
    prov = schema.create_provenance_entity("RxNorm")
    print(f"  RxNorm provenance: {prov['id']}")
    citation = [v for v in prov['values'] if v['property'] == schema.prop('citation')][0]
    print(f"  Citation: {citation['value'][:60]}...")
