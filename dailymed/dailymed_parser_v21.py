#!/usr/bin/env python3
"""
Enhanced Drug Knowledge Graph Builder with AMA Citations, ANDA/NDA Info, and SPL Completeness Score.
Builds a comprehensive drug knowledge graph from DailyMed XML files with 
section-specific relationship types, proper AMA citations, ANDA/NDA information,
and a verifiable accuracy score based on FDA source data.

VERSION 21: Fixed document duplication issue by tracking processed set IDs
VERSION 21.1: Fixed corrupted provenance ledger handling
"""

import os
import json
import logging
import argparse
import hashlib
import re
import sys
import time  # NEW: Import time module for progress tracking
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Set
import xml.etree.ElementTree as ET
from datetime import datetime
from collections import defaultdict

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Define namespace for SPL XML
SPL_NS = {'ns0': 'urn:hl7-org:v3'}

# --- DEFINITIVE FDA LOINC CODE MAPPING ---
LOINC_CODE_MAP = {
    # Core Sections
    '34066-1': 'BOXED_WARNING',
    '34067-9': 'INDICATIONS_AND_USAGE',
    '34068-7': 'DOSAGE_AND_ADMINISTRATION',
    '43678-2': 'DOSAGE_FORMS_AND_STRENGTHS',
    '34070-3': 'CONTRAINDICATIONS',
    '34071-1': 'WARNINGS_AND_PRECAUTIONS',
    '43685-7': 'WARNINGS_AND_PRECAUTIONS',
    '42232-9': 'WARNINGS_AND_PRECAUTIONS',
    '34084-4': 'ADVERSE_REACTIONS',
    '90374-0': 'ADVERSE_REACTIONS',
    '90375-7': 'ADVERSE_REACTIONS',
    '34073-7': 'DRUG_INTERACTIONS',
    '34074-5': 'DRUG_INTERACTIONS',  # Added mapping for Drug-Laboratory Test Interactions
    '43684-0': 'USE_IN_SPECIFIC_POPULATIONS',
    '42228-7': 'USE_IN_SPECIFIC_POPULATIONS',
    '34080-2': 'USE_IN_SPECIFIC_POPULATIONS',
    '34081-0': 'USE_IN_SPECIFIC_POPULATIONS',
    '34082-8': 'USE_IN_SPECIFIC_POPULATIONS',
    '34079-4': 'USE_IN_SPECIFIC_POPULATIONS',
    '77290-5': 'USE_IN_SPECIFIC_POPULATIONS',
    '77291-3': 'USE_IN_SPECIFIC_POPULATIONS',
    '88829-7': 'USE_IN_SPECIFIC_POPULATIONS',
    '88830-5': 'USE_IN_SPECIFIC_POPULATIONS',
    '88828-9': 'USE_IN_SPECIFIC_POPULATIONS',
    '42227-9': 'DRUG_ABUSE_AND_DEPENDENCE',
    '34085-1': 'DRUG_ABUSE_AND_DEPENDENCE',
    '34087-7': 'DRUG_ABUSE_AND_DEPENDENCE',
    '34086-9': 'DRUG_ABUSE_AND_DEPENDENCE',
    '34088-5': 'OVERDOSAGE',
    '34089-3': 'DESCRIPTION',
    '34090-1': 'CLINICAL_PHARMACOLOGY',
    '43679-0': 'CLINICAL_PHARMACOLOGY',
    '43681-6': 'CLINICAL_PHARMACOLOGY',
    '43682-4': 'CLINICAL_PHARMACOLOGY',
    '49489-8': 'CLINICAL_PHARMACOLOGY',
    '66106-6': 'CLINICAL_PHARMACOLOGY',
    '43680-8': 'NONCLINICAL_TOXICOLOGY',
    '34083-6': 'NONCLINICAL_TOXICOLOGY',
    '34091-9': 'NONCLINICAL_TOXICOLOGY',
    '34069-5': 'HOW_SUPPLIED',
    '44425-7': 'HOW_SUPPLIED',
    '34076-0': 'INFORMATION_FOR_PATIENTS',
    '88436-1': 'INFORMATION_FOR_PATIENTS',
    '59845-8': 'INFORMATION_FOR_PATIENTS',
    '50744-2': 'INFORMATION_FOR_PATIENTS',  # Information for owners or caregivers section
    '68498-5': 'INFORMATION_FOR_PATIENTS',  # Patient medication information section
    '42230-3': 'INFORMATION_FOR_PATIENTS',
    '42231-1': 'INFORMATION_FOR_PATIENTS',
    '34092-7': 'CLINICAL_STUDIES',
    '34093-5': 'REFERENCES',
    '42229-5': 'OTHER',  # Structured patient labelling unclassified section
    '48780-1': 'OTHER',  # Structured product labelling listing data elements section
    '48779-3': 'OTHER',  # Structured product labelling indexing data elements section
    '51945-4': 'OTHER',  # Principal Display Panel
    
    # NEW: Missing Codes from Your Analysis
    '43683-2': 'RECENT_MAJOR_CHANGES',  # Recent major changes section
    '34077-8': 'TERATOGENIC_EFFECTS',   # Teratogenic effects section
    '34078-6': 'NONTERATOGENIC_EFFECTS', # Nonteratogenic effects section
    '51727-6': 'INACTIVE_INGREDIENTS',   # Inactive ingredient section
    '69759-9': 'RISKS',                  # Risks
    '60559-2': 'COMPONENTS',             # Components
    '55106-9': 'ACTIVE_INGREDIENTS',     # Active ingredient section
    '50565-1': 'OTC_KEEP_OUT_OF_REACH',  # OTC - Keep out of reach of children section
    '55105-1': 'OTC_PURPOSE',            # OTC - Purpose section
    '60561-8': 'OTHER_SAFETY_INFO',      # Other safety information
    '50741-8': 'SAFE_HANDLING_WARNING',  # Safe handling warning section
    '50566-9': 'OTC_STOP_USE',           # OTC - Stop use section
    '50570-1': 'OTC_DO_NOT_USE',         # OTC - Do not use section
    '50567-7': 'OTC_WHEN_USING',         # OTC - When using section
    '53413-1': 'OTC_QUESTIONS',          # OTC - Questions section
    '71744-7': 'HEALTHCARE_PROVIDER_LETTER', # Health care provider letter
    
    # NEW: Additional Missing Codes from Latest Analysis
    '50569-3': 'OTC_ASK_DOCTOR',         # OTC - Ask doctor section
    '50744-2': 'INFORMATION_FOR_CAREGIVERS', # Information for owners or caregivers section
    '38056-8': 'SUPPLEMENTAL_PATIENT_MATERIAL', # Structured product labelling supplemental patient material
    '69763-1': 'DISPOSAL_INSTRUCTIONS',  # Disposal and waste handling
    '69718-5': 'STATEMENT_OF_IDENTITY',  # Statement of identity section
    '50742-6': 'ENVIRONMENTAL_WARNING',  # Environmental warning section
    '53414-9': 'OTC_PREGNANCY_BREASTFEEDING', # OTC - Pregnancy or breast feeding section
    '60560-0': 'INTENDED_USE',           # Intended use of the device
    '54433-8': 'USER_SAFETY_WARNINGS',   # User safety warnings section
    '50745-9': 'VETERINARY_INDICATIONS', # Veterinary indications section
    '82598-4': 'REMS_MEDICATION_GUIDE',  # REMS medication guide
    '69719-3': 'HEALTH_CLAIM',           # Health claim section
    '50568-5': 'OTC_ASK_DOCTOR_PHARMACIST', # OTC - Ask doctor or pharmacist section
    '60558-4': 'CLEANING_INSTRUCTIONS',  # Cleaning, disinfecting, and sterilization instructions
    '69761-5': 'ALARMS',                 # Alarms
    '82347-6': 'REMS_SUMMARY',           # REMS summary
    '60562-6': 'ADMINISTRATION_METHODS', # Route, method and frequency of administration
    '60563-4': 'SAFETY_EFFECTIVENESS_SUMMARY', # Summary of safety and effectiveness
    '87523-7': 'REMS_ADMIN_INFO',        # REMS administrative information
    '60555-0': 'ACCESSORIES',            # Accessories
    
    # FINAL: Last 7 Missing Codes
    '69760-7': 'COMPATIBLE_ACCESSORIES', # Compatible accessories
    '60556-8': 'ASSEMBLY_INSTRUCTIONS',  # Assembly or installation instructions
    '69758-1': 'DEVICE_DIAGRAM',         # Diagram of device
    '82350-0': 'REMS_IMPLEMENTATION_SYSTEM', # REMS implementation system
    '82344-3': 'REMS_COMMUNICATION_PLAN', # REMS communication plan
    '60557-6': 'CALIBRATION_INSTRUCTIONS', # Calibration instructions
    '69762-3': 'TROUBLESHOOTING',        # Troubleshooting,
}
# --- END LOINC MAPPING ---

# --- NEW: Core Clinical Sections for Enhanced Metrics ---
CORE_CLINICAL_LOINC_CODES = {
    '34066-1': 'BOXED_WARNING',
    '34067-9': 'INDICATIONS_AND_USAGE',
    '34068-7': 'DOSAGE_AND_ADMINISTRATION',
    '43678-2': 'DOSAGE_FORMS_AND_STRENGTHS',
    '34070-3': 'CONTRAINDICATIONS',
    '43685-7': 'WARNINGS_AND_PRECAUTIONS',
    '34084-4': 'ADVERSE_REACTIONS',
    '90374-0': 'ADVERSE_REACTIONS',
    '90375-7': 'ADVERSE_REACTIONS',
    '34073-7': 'DRUG_INTERACTIONS',
    '43684-0': 'USE_IN_SPECIFIC_POPULATIONS',
    '34088-5': 'OVERDOSAGE',
    '34089-3': 'DESCRIPTION',
    '34090-1': 'CLINICAL_PHARMACOLOGY',
    '43680-8': 'NONCLINICAL_TOXICOLOGY',
    '34091-9': 'NONCLINICAL_TOXICOLOGY',
    '34092-7': 'CLINICAL_STUDIES',
    '34069-5': 'HOW_SUPPLIED',
    '88436-1': 'INFORMATION_FOR_PATIENTS',
}
# --- END CORE CLINICAL SECTIONS ---

# --- FDA APPLICATION CODE MAPPING ---
# Maps SPL application codes to their meanings
APPLICATION_CODE_MAP = {
    'C73583': 'ANADA',
    'C73584': 'ANDA',
    'C132333': 'Approved Drug Product Manufactured Under Contract',
    'C73585': 'BLA',
    'C73626': 'Bulk ingredient',
    'C98252': 'Bulk Ingredient For Animal Drug Compounding',
    'C96793': 'Bulk Ingredient For Human Prescription Compounding',
    'C73588': 'Conditional NADA',
    'C86965': 'Cosmetic',
    'C86952': 'Dietary Supplement',
    'C94795': 'Drug for Further Processing',
    'C96966': 'Emergency Use Authorization',
    'C80438': 'Exempt device',
    'C73590': 'Export only',
    'C75302': 'IND',
    'C80440': 'Humanitarian Device Exemption',
    'C92556': 'Legally Marketed Unapproved New Animal Drugs for Minor Species',
    'C175238': 'Multi-Market Approved Product',
    'C73593': 'NADA',
    'C73594': 'NDA',
    'C73605': 'NDA authorized generic',
    'C200263': 'OTC Monograph Drug',
    'C132334': 'OTC Monograph Drug Product Manufactured Under Contract',
    'C181659': 'Outsourcing Facility Compounded Human Drug Product (Exempt From Approval Requirements)',
    'C190698': 'Outsourcing Facility Compounded Human Drug Product (Not Marketed - Not Distributed)',
    'C80441': 'Premarket Application',
    'C80442': 'Premarket Notification',
    'C175462': 'SIP Approved Drug',
    'C101533': 'Unapproved drug for use in drug shortage',
    'C73627': 'Unapproved drug other',
    'C132335': 'Unapproved Drug Product Manufactured Under Contract',
    'C73614': 'Unapproved homeopathic',
    'C73613': 'Unapproved medical gas',
}
# --- END APPLICATION CODE MAPPING ---

# --- ENHANCED SUBSECTION MAPPING ---
# Maps subsection titles to their parent section types for cases without numerical prefixes.
SUBSECTION_PARENT_MAP = {
    # Adverse Reactions
    'Clinical Trials Experience': 'ADVERSE_REACTIONS',
    'Clinical Trials': 'ADVERSE_REACTIONS',
    'Postmarketing Experience': 'ADVERSE_REACTIONS',
    
    # Use in Specific Populations
    'Pregnancy': 'USE_IN_SPECIFIC_POPULATIONS',
    'Nursing Mothers': 'USE_IN_SPECIFIC_POPULATIONS',
    'Pediatric Use': 'USE_IN_SPECIFIC_POPULATIONS',
    'Geriatric Use': 'USE_IN_SPECIFIC_POPULATIONS',
    'Hepatic Impairment': 'USE_IN_SPECIFIC_POPULATIONS',
    'Renal Impairment': 'USE_IN_SPECIFIC_POPULATIONS',
    
    # Warnings and Precautions
    'General': 'WARNINGS_AND_PRECAUTIONS',
    'Laboratory Tests': 'WARNINGS_AND_PRECAUTIONS',
    'Drug Interactions': 'WARNINGS_AND_PRECAUTIONS', # Sometimes a sub-section of W&P
    'Carcinogenesis and Mutagenesis and Impairment of Fertility': 'WARNINGS_AND_PRECAUTIONS',
    'Information for Patients': 'WARNINGS_AND_PRECAUTIONS', # Added to catch nested under PRECAUTIONS
}
# --- END SUBSECTION MAPPING ---

# --- SECTION TITLE MAPPING FOR STANDALONE SECTIONS WITHOUT LOINC CODES ---
# Maps normalized section titles to their section types for standalone sections without LOINC codes
SECTION_TITLE_MAP = {
    'INDICATIONSANDUSAGE': 'INDICATIONS_AND_USAGE',
    'DOSAGEANDADMINISTRATION': 'DOSAGE_AND_ADMINISTRATION',
    'DOSAGEFORMSANDSTRENGTHS': 'DOSAGE_FORMS_AND_STRENGTHS',
    'CONTRAINDICATIONS': 'CONTRAINDICATIONS',
    'WARNINGSANDPRECAUTIONS': 'WARNINGS_AND_PRECAUTIONS',
    'ADVERSEREACTIONS': 'ADVERSE_REACTIONS',
    'DRUGINTERACTIONS': 'DRUG_INTERACTIONS',
    'USEINSPECIFICPOPULATIONS': 'USE_IN_SPECIFIC_POPULATIONS',
    'DRUGABUSEANDDEPENDENCE': 'DRUG_ABUSE_AND_DEPENDENCE',
    'OVERDOSAGE': 'OVERDOSAGE',
    'DESCRIPTION': 'DESCRIPTION',
    'CLINICALPHARMACOLOGY': 'CLINICAL_PHARMACOLOGY',
    'NONCLINICALTOXICOLOGY': 'NONCLINICAL_TOXICOLOGY',
    'HOWSUPPLIED': 'HOW_SUPPLIED',
    'INFORMATIONFORPATIENTS': 'INFORMATION_FOR_PATIENTS',
    'CLINICALSTUDIES': 'CLINICAL_STUDIES',
    'REFERENCES': 'REFERENCES',
}
# --- END SECTION TITLE MAPPING ---

# --- ENHANCED SECTION TO RELATIONSHIP TYPE MAPPING ---
# Maps section types to specific relationship types for better semantic connectivity
SECTION_TO_RELATIONSHIP_MAP = {
    'BOXED_WARNING': 'HAS_BOXED_WARNING',
    'INDICATIONS_AND_USAGE': 'HAS_INDICATIONS',
    'DOSAGE_AND_ADMINISTRATION': 'HAS_DOSAGE_INFO',
    'DOSAGE_FORMS_AND_STRENGTHS': 'HAS_DOSAGE_FORMS',
    'CONTRAINDICATIONS': 'HAS_CONTRAINDICATIONS',
    'WARNINGS_AND_PRECAUTIONS': 'HAS_WARNINGS',
    'ADVERSE_REACTIONS': 'HAS_ADVERSE_REACTIONS',
    'DRUG_INTERACTIONS': 'HAS_DRUG_INTERACTIONS',
    'USE_IN_SPECIFIC_POPULATIONS': 'HAS_SPECIAL_POPULATIONS_INFO',
    'DRUG_ABUSE_AND_DEPENDENCE': 'HAS_ABUSE_INFO',
    'OVERDOSAGE': 'HAS_OVERDOSAGE_INFO',
    'DESCRIPTION': 'HAS_DESCRIPTION',
    'CLINICAL_PHARMACOLOGY': 'HAS_PHARMACOLOGY',
    'NONCLINICAL_TOXICOLOGY': 'HAS_TOXICOLOGY',
    'HOW_SUPPLIED': 'HAS_SUPPLY_INFO',
    'INFORMATION_FOR_PATIENTS': 'HAS_PATIENT_INFO',
    'CLINICAL_STUDIES': 'HAS_CLINICAL_STUDIES',
    'REFERENCES': 'HAS_REFERENCES',
    'OTHER': 'HAS_OTHER_INFO',
    
    # NEW: Additional relationship types for enhanced sections
    'RECENT_MAJOR_CHANGES': 'HAS_MAJOR_CHANGES',
    'TERATOGENIC_EFFECTS': 'HAS_TERATOGENIC_INFO',
    'NONTERATOGENIC_EFFECTS': 'HAS_NONTERATOGENIC_INFO',
    'INACTIVE_INGREDIENTS': 'HAS_INACTIVE_INGREDIENTS',
    'RISKS': 'HAS_RISKS',
    'COMPONENTS': 'HAS_COMPONENTS',
    'ACTIVE_INGREDIENTS': 'HAS_ACTIVE_INGREDIENTS',
    'OTC_KEEP_OUT_OF_REACH': 'HAS_OTC_SAFETY_INFO',
    'OTC_PURPOSE': 'HAS_OTC_PURPOSE',
    'OTHER_SAFETY_INFO': 'HAS_OTHER_SAFETY_INFO',
    'SAFE_HANDLING_WARNING': 'HAS_SAFE_HANDLING_INFO',
    'OTC_STOP_USE': 'HAS_OTC_STOP_USE',
    'OTC_DO_NOT_USE': 'HAS_OTC_DO_NOT_USE',
    'OTC_WHEN_USING': 'HAS_OTC_WHEN_USING',
    'OTC_QUESTIONS': 'HAS_OTC_QUESTIONS',
    'HEALTHCARE_PROVIDER_LETTER': 'HAS_HEALTHCARE_LETTER',
    'INFORMATION_FOR_CAREGIVERS': 'HAS_CAREGIVER_INFO',
    'SUPPLEMENTAL_PATIENT_MATERIAL': 'HAS_SUPPLEMENTAL_MATERIAL',
    'DISPOSAL_INSTRUCTIONS': 'HAS_DISPOSAL_INFO',
    'STATEMENT_OF_IDENTITY': 'HAS_IDENTITY_STATEMENT',
    'ENVIRONMENTAL_WARNING': 'HAS_ENVIRONMENTAL_WARNING',
    'OTC_PREGNANCY_BREASTFEEDING': 'HAS_OTC_PREGNANCY_INFO',
    'INTENDED_USE': 'HAS_INTENDED_USE',
    'USER_SAFETY_WARNINGS': 'HAS_USER_SAFETY_WARNINGS',
    'VETERINARY_INDICATIONS': 'HAS_VETERINARY_INDICATIONS',
    'REMS_MEDICATION_GUIDE': 'HAS_REMS_MEDICATION_GUIDE',
    'HEALTH_CLAIM': 'HAS_HEALTH_CLAIM',
    'OTC_ASK_DOCTOR_PHARMACIST': 'HAS_OTC_ASK_DOCTOR_PHARMACIST',
    'CLEANING_INSTRUCTIONS': 'HAS_CLEANING_INSTRUCTIONS',
    'ALARMS': 'HAS_ALARMS',
    'REMS_SUMMARY': 'HAS_REMS_SUMMARY',
    'ADMINISTRATION_METHODS': 'HAS_ADMINISTRATION_METHODS',
    'SAFETY_EFFECTIVENESS_SUMMARY': 'HAS_SAFETY_EFFECTIVENESS_SUMMARY',
    'REMS_ADMIN_INFO': 'HAS_REMS_ADMIN_INFO',
    'ACCESSORIES': 'HAS_ACCESSORIES',
    'COMPATIBLE_ACCESSORIES': 'HAS_COMPATIBLE_ACCESSORIES',
    'ASSEMBLY_INSTRUCTIONS': 'HAS_ASSEMBLY_INSTRUCTIONS',
    'DEVICE_DIAGRAM': 'HAS_DEVICE_DIAGRAM',
    'REMS_IMPLEMENTATION_SYSTEM': 'HAS_REMS_IMPLEMENTATION_SYSTEM',
    'REMS_COMMUNICATION_PLAN': 'HAS_REMS_COMMUNICATION_PLAN',
    'CALIBRATION_INSTRUCTIONS': 'HAS_CALIBRATION_INSTRUCTIONS',
    'TROUBLESHOOTING': 'HAS_TROUBLESHOOTING',
}
# --- END SECTION TO RELATIONSHIP MAPPING ---

# --- NEW: Progress Tracking Function ---
def update_progress(current, total, start_time):
    """Update and display progress information."""
    percent = (current / total) * 100
    elapsed = time.time() - start_time
    if current > 0:
        eta = (elapsed / current) * (total - current)
        eta_str = f"{eta/60:.1f} min" if eta > 60 else f"{eta:.1f} sec"
    else:
        eta_str = "calculating..."
    
    sys.stdout.write(f"\rProgress: {current}/{total} ({percent:.1f}%) - Elapsed: {elapsed/60:.1f} min - ETA: {eta_str}")
    sys.stdout.flush()
# --- END PROGRESS TRACKING ---

# --- ENHANCED PROVENANCE SYSTEM ---
class ProvenanceManager:
    """Manages provenance data for the drug knowledge graph."""
    def __init__(self, ledger_file: str):
        self.ledger_file = ledger_file
        self.ledger = self._load_ledger()
        
    def _load_ledger(self) -> Dict[str, Any]:
        # V21.1 FIX: Handle corrupted ledger files
        if os.path.exists(self.ledger_file):
            try:
                with open(self.ledger_file, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Could not load provenance ledger: {e}. Creating new ledger.")
                # Backup the corrupted file
                backup_file = f"{self.ledger_file}.corrupted_{int(time.time())}"
                try:
                    import shutil
                    shutil.copy2(self.ledger_file, backup_file)
                    logger.info(f"Backed up corrupted ledger to {backup_file}")
                except:
                    pass
                # Return a new empty ledger
                return {'metadata': {'created': datetime.now().isoformat(), 'version': '3.0'}, 'sources': {}, 'entities': {}, 'documents': {}, 'relationships': {}}
        return {'metadata': {'created': datetime.now().isoformat(), 'version': '3.0'}, 'sources': {}, 'entities': {}, 'documents': {}, 'relationships': {}}
    
    def save_ledger(self) -> None:
        os.makedirs(os.path.dirname(self.ledger_file), exist_ok=True)
        self.ledger['metadata']['last_modified'] = datetime.now().isoformat()
        with open(self.ledger_file, 'w') as f:
            json.dump(self.ledger, f, indent=2)
    
    def create_provenance_record(self, data_type: str, source: str, source_file: str, **kwargs) -> str:
        today = datetime.now().strftime('%Y-%m-%d')
        base_provenance = {'data_type': data_type, 'source': source, 'source_file': source_file, 'date_accessed': today}
        base_provenance.update(kwargs)
        
        prov_hash = hashlib.sha256(json.dumps(base_provenance, sort_keys=True).encode('utf-8')).hexdigest()[:16]
        
        if data_type not in self.ledger:
            self.ledger[data_type] = {}
        self.ledger[data_type][prov_hash] = base_provenance
        
        if source not in self.ledger['sources']:
            self.ledger['sources'][source] = {'description': 'FDA Structured Product Labels from DailyMed', 'first_used': today, 'usage_count': 0}
        self.ledger['sources'][source]['usage_count'] += 1
        self.ledger['sources'][source]['last_used'] = today
        
        return prov_hash
# --- END PROVENANCE SYSTEM ---

# --- AMA CITATION GENERATION ---
def generate_ama_citation(drug_name: str, manufacturer: str, effective_time: str) -> str:
    """Generate an AMA-style citation for a package insert."""
    # Parse the effective time to get the year
    year = "Unknown"
    if effective_time and len(effective_time) >= 4:
        year = effective_time[:4]
    
    # AMA format: Drug Name [package insert]. Manufacturer; Year.
    citation = f"{drug_name} [package insert]. {manufacturer}; {year}."
    
    return citation
# --- END AMA CITATION GENERATION ---

def extract_text(element: ET.Element) -> str:
    """Extract text from an XML element, handling nested elements."""
    if element is None: return ""
    if element.tag.endswith('renderMultiMedia'):
        ref = element.get('referencedObject')
        return f"[Image: {ref}]" if ref else "[Image]"
    
    text_parts = []
    if element.text: text_parts.append(element.text)
    for child in element:
        child_text = extract_text(child)
        if child_text: text_parts.append(child_text)
        if child.tail: text_parts.append(child.tail)
    return ' '.join(text_parts).strip()

def clean_text(text: str) -> str:
    """Clean and normalize text content."""
    if not text: return ""
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'<[^>]+>', '', text)
    text = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>').replace('&quot;', '"').replace('&apos;', "'")
    return text.strip()

def normalize_section_name(section_name: str) -> str:
    """Normalize section name for comparison by removing spaces, underscores, etc."""
    return re.sub(r'[\s_]', '', section_name).upper()

# --- FIXED: Extract ANDA/NDA information ---
def extract_application_info(root: ET.Element) -> Dict[str, Any]:
    """FIXED: Extract application information (ANDA/NDA) from the XML."""
    app_info = {}
    seen_applications = set()  # Track seen applications to avoid duplicates
    
    try:
        # Look for approval elements (not application elements)
        for approval in root.findall('.//ns0:approval', SPL_NS):
            # Get application number from the id element
            id_elem = approval.find('.//ns0:id', SPL_NS)
            if id_elem is not None:
                app_id = id_elem.get('extension')
                if not app_id:
                    continue
                
                # Skip if we've already seen this application
                if app_id in seen_applications:
                    continue
                seen_applications.add(app_id)
                
                # Get application type code from the code element
                code_elem = approval.find('.//ns0:code', SPL_NS)
                if code_elem is not None:
                    app_code = code_elem.get('code')
                    if app_code:
                        app_type = APPLICATION_CODE_MAP.get(app_code, app_code)
                        app_info['application_type'] = app_type
                        app_info['application_code'] = app_code
                        app_info['application_number'] = app_id
                        break  # We only need one application per document
        
        # Look for approval date if we found an application
        if app_info:
            for approval in root.findall('.//ns0:approval', SPL_NS):
                approval_date = approval.find('.//ns0:approvalDate', SPL_NS)
                if approval_date is not None:
                    app_info['approval_date'] = approval_date.get('value')
                    break
    
    except Exception as e:
        logger.debug(f"Error extracting application info: {str(e)}")
    
    return app_info
# --- END APPLICATION INFO EXTRACTION ---

def extract_fda_drug_info(root: ET.Element, file_path: str, prov_manager: ProvenanceManager) -> Dict[str, Any]:
    """Extract drug information from the XML using FDA SPL identifiers for provenance."""
    drug_info = {}
    try:
        doc_id_elem = root.find('.//ns0:id', SPL_NS)
        set_id_elem = root.find('.//ns0:setId', SPL_NS)
        version_elem = root.find('.//ns0:versionNumber', SPL_NS)
        if doc_id_elem is not None: drug_info['fda_document_id'] = doc_id_elem.get('root')
        if set_id_elem is not None: drug_info['fda_set_id'] = set_id_elem.get('root')
        if version_elem is not None: drug_info['version_number'] = version_elem.get('value')

        # --- FIX: Prioritize manufacturedProduct/name for drug name ---
        drug_names = set()
        for product in root.findall('.//ns0:manufacturedProduct/ns0:name', SPL_NS):
            name = clean_text(extract_text(product))
            if name: drug_names.add(name)
        
        # Fallback to title if no product names found
        if not drug_names:
            title_elem = root.find('.//ns0:title', SPL_NS)
            if title_elem is not None:
                title_text = clean_text(extract_text(title_elem))
                # Attempt to extract drug name from the start of the title
                match = re.match(r'^([A-Za-z0-9\-]+(?:\s+[A-Za-z0-9\-]+)*)\s+', title_text)
                if match: drug_names.add(match.group(1))

        if drug_names:
            drug_info['drug_names'] = sorted(list(drug_names))
            drug_info['title'] = drug_info['drug_names'][0] # Use the first name as the main title
        
        eff_time = root.find('.//ns0:effectiveTime', SPL_NS)
        if eff_time is not None: drug_info['effective_time'] = eff_time.get('value')
        
        manufacturer = root.find('.//ns0:author//ns0:representedOrganization//ns0:name', SPL_NS)
        if manufacturer is not None: drug_info['manufacturer'] = clean_text(extract_text(manufacturer))

        ndc_codes = set()
        for ndc in root.findall('.//ns0:containerPackagedProduct/ns0:code', SPL_NS):
            code = ndc.get('code')
            if code:
                normalized = code.replace('-', '').zfill(11)
                formatted = f"{normalized[:5]}-{normalized[5:9]}-{normalized[9:11]}"
                ndc_codes.add(formatted)
        if ndc_codes: drug_info['ndc_codes'] = list(ndc_codes)

        # --- FIXED: Extract ANDA/NDA information ---
        app_info = extract_application_info(root)
        drug_info.update(app_info)

        # --- Generate AMA citation ---
        if 'title' in drug_info and 'manufacturer' in drug_info and 'effective_time' in drug_info:
            drug_info['ama_citation'] = generate_ama_citation(
                drug_info['title'], 
                drug_info['manufacturer'], 
                drug_info['effective_time']
            )

        unique_id = drug_info.get('fda_set_id', drug_info.get('fda_document_id', hashlib.md5(file_path.encode()).hexdigest()))
        drug_info['unique_id'] = unique_id
        doc_prov_hash = prov_manager.create_provenance_record(
            data_type='documents', source='fda_spl', source_file=file_path,
            fda_document_id=drug_info.get('fda_document_id'), fda_set_id=drug_info.get('fda_set_id'),
            version_number=drug_info.get('version_number'), drug_name=drug_info.get('title', '')
        )
        drug_info['provenance_hash'] = doc_prov_hash
    except Exception as e:
        logger.error(f"Error extracting drug info from {file_path}: {str(e)}")
        drug_info = {'file_path': file_path, 'unique_id': hashlib.md5(file_path.encode()).hexdigest(), 'provenance_hash': prov_manager.create_provenance_record(data_type='documents', source='fda_spl', source_file=file_path, reasoning=f"Error during extraction: {str(e)}")}
    return drug_info

def extract_section_content(section: ET.Element) -> str:
    """Extract content from a section, handling both direct text elements and nested sections within components."""
    content_parts = []
    
    # First try to get content from direct text element
    text_elem = section.find('ns0:text', SPL_NS)
    if text_elem is not None:
        content_parts.append(extract_text(text_elem))
    
    # Also check for nested sections within components
    for component in section.findall('ns0:component', SPL_NS):
        nested_section = component.find('ns0:section', SPL_NS)
        if nested_section is not None:
            # Extract content from the nested section
            nested_text = nested_section.find('ns0:text', SPL_NS)
            if nested_text is not None:
                content_parts.append(extract_text(nested_text))
            else:
                # If no direct text element, extract all text from the nested section
                content_parts.append(extract_text(nested_section))
    
    # Join all content parts
    return ' '.join(content_parts).strip()

# --- NEW: SPL Section Census Function ---
def get_spl_section_census(root: ET.Element) -> Set[str]:
    """
    Scans an XML document and returns a set of all LOINC codes found.
    This is our ground truth for what's available in the source document.
    """
    found_loinc_codes = set()
    try:
        all_sections = root.findall('.//ns0:section', SPL_NS)
        for section in all_sections:
            code_elem = section.find('ns0:code', SPL_NS)
            if code_elem is not None:
                loinc_code = code_elem.get('code', '')
                if loinc_code:
                    found_loinc_codes.add(loinc_code)
    except Exception as e:
        logger.error(f"Error during SPL census: {str(e)}")
    return found_loinc_codes
# --- END CENSUS FUNCTION ---

def extract_sections_with_provenance(root: ET.Element, doc_id: str, prov_manager: ProvenanceManager, doc_prov_hash: str, ama_citation: str) -> List[Dict[str, Any]]:
    """
    Extract sections using a hybrid LOINC code and enhanced hierarchy approach with AMA citations.
    LOGIC:
    1. A section is a PARENT if and ONLY if its LOINC code maps to a known type.
    2. A section is a SUBSECTION if its title is numbered (e.g., "5.1") OR it's in the SUBSECTION_PARENT_MAP.
    3. We use the numbering or the map to attach subsections to their parents.
    4. NEW: Also create parent sections for standalone sections with matching titles but no LOINC codes.
    5. FALLBACK: If DOSAGE_FORMS_AND_STRENGTHS is missing, create it from DOSAGE_AND_ADMINISTRATION.
    6. Only create synthetic DOSAGE_FORMS_AND_STRENGTHS if HOW_SUPPLIED is also missing.
    7. FIXED: Extract content from both direct text elements and nested sections within components.
    8. NEW: Add AMA citation to each section.
    9. CRITICAL FIX: Protect parent sections (like BOXED_WARNING) from being processed as subsections.
    """
    sections = []
    try:
        all_sections = root.findall('.//ns0:section', SPL_NS)
        
        # --- First Pass: Identify all PARENT sections using LOINC code or matching title ---
        parent_sections = {} 
        for section in all_sections:
            code_elem = section.find('ns0:code', SPL_NS)
            title_elem = section.find('ns0:title', SPL_NS)
            id_elem = section.find('ns0:id', SPL_NS)
            
            if title_elem is None or id_elem is None:
                continue

            title = clean_text(extract_text(title_elem))
            section_id = id_elem.get('root', '')
            normalized_title = normalize_section_name(title)
            
            # Check by LOINC code first
            section_type = 'OTHER'
            loinc_code = ''
            if code_elem is not None:
                loinc_code = code_elem.get('code', '')
                section_type = LOINC_CODE_MAP.get(loinc_code, 'OTHER')
            
            # If no LOINC code or LOINC code maps to OTHER, check by title
            if section_type == 'OTHER' and normalized_title in SECTION_TITLE_MAP:
                section_type = SECTION_TITLE_MAP[normalized_title]
                loinc_code = 'TITLE_MATCH'
            
            if section_type != 'OTHER':
                # FIXED: Use the improved content extraction function
                content = extract_section_content(section)
                parent_sections[section_id] = {
                    'type': section_type,
                    'title': title,
                    'content': content,
                    'section_id': section_id,
                    'loinc_code': loinc_code
                }

        # --- Second Pass: Aggregate content from all sections into the correct parents ---
        for section in all_sections:
            section_id_elem = section.find('ns0:id', SPL_NS)
            title_elem = section.find('ns0:title', SPL_NS)

            if section_id_elem is None or title_elem is None:
                continue

            section_id = section_id_elem.get('root', '')
            title = clean_text(extract_text(title_elem))

            # --- CRITICAL FIX: If this section IS a parent, skip it in the aggregation pass ---
            # This prevents parent sections (like BOXED_WARNING) from being misinterpreted as subsections
            # and having their content overwritten or incorrectly aggregated.
            if section_id in parent_sections:
                continue

            # --- FIX: Enhanced Subsection Detection ---
            subsection_match = re.match(r'^(\d+)\.(\d+)\s+(.*)', title)
            parent_type = SUBSECTION_PARENT_MAP.get(title)
            
            if subsection_match or parent_type:
                parent_found = False
                target_parent_type = ''
                
                # FIXED: Extract content from subsections using the improved function
                content = extract_section_content(section)
                
                if subsection_match:
                    parent_num, sub_num, sub_title = subsection_match.groups()
                    # Find parent by number
                    for parent_id, parent_data in parent_sections.items():
                        if re.match(rf'^{re.escape(parent_num)}\b', parent_data['title']):
                            parent_sections[parent_id]['content'] += f"\n\n--- {sub_title.strip()} ---\n{content}"
                            parent_found = True
                            break
                elif parent_type:
                    # Find parent by type using the map
                    target_parent_type = parent_type
                    for parent_id, parent_data in parent_sections.items():
                        if parent_data['type'] == target_parent_type:
                            parent_sections[parent_id]['content'] += f"\n\n--- {title.strip()} ---\n{content}"
                            parent_found = True
                            break
                
                if not parent_found:
                    logger.debug(f"Orphan subsection found and ignored: {title} for document {doc_id} (Target Parent: {target_parent_type})")
            else:
                logger.debug(f"Ignoring top-level section without LOINC code: {title} for document {doc_id}")
        
        # --- FINAL FALLBACK LOGIC ---
        has_strengths_section = any(sec['type'] == 'DOSAGE_FORMS_AND_STRENGTHS' for sec in parent_sections.values())
        has_dosage_section = any(sec['type'] == 'DOSAGE_AND_ADMINISTRATION' for sec in parent_sections.values())
        has_how_supplied_section = any(sec['type'] == 'HOW_SUPPLIED' for sec in parent_sections.values())
        
        # Only create synthetic DOSAGE_FORMS_AND_STRENGTHS if both DOSAGE_FORMS_AND_STRENGTHS and HOW_SUPPLIED are missing
        # but DOSAGE_AND_ADMINISTRATION is available
        if not has_strengths_section and not has_how_supplied_section and has_dosage_section:
            logger.info(f"FALLBACK: Creating DOSAGE_FORMS_AND_STRENGTHS from DOSAGE_AND_ADMINISTRATION for {doc_id}")
            dosage_section_data = None
            for sec_data in parent_sections.values():
                if sec_data['type'] == 'DOSAGE_AND_ADMINISTRATION':
                    dosage_section_data = sec_data
                    break
            
            if dosage_section_data:
                synthetic_id = hashlib.md5(f"{doc_id}_synthetic_strengths".encode()).hexdigest()
                parent_sections[synthetic_id] = {
                    'type': 'DOSAGE_FORMS_AND_STRENGTHS',
                    'title': 'DOSAGE FORMS AND STRENGTHS (Synthesized from Dosage and Administration)',
                    'content': dosage_section_data['content'],
                    'section_id': synthetic_id,
                    'loinc_code': 'SYNTHETIC'
                }

        # --- Final Pass: Convert the aggregated parent sections into the final list ---
        for sec_id, sec_data in parent_sections.items():
            prov_hash = prov_manager.create_provenance_record(
                data_type='entities', source='fda_spl', source_file='section',
                fda_document_id=doc_id, fda_section_id=sec_data['section_id'],
                fda_loinc_code=sec_data['loinc_code'], section_type=sec_data['type']
            )
            
            # --- Add section citation ---
            section_title = sec_data['title']
            section_citation = f"{section_title}. In: {ama_citation}"
            
            sections.append({
                'section_id': hashlib.md5(f"{doc_id}_{sec_id}".encode()).hexdigest(),
                'section_unique_id': hashlib.md5(f"{doc_id}_section_{sec_id}".encode()).hexdigest(),
                'section_type': sec_data['type'],
                'title': sec_data['title'],
                'content': sec_data['content'].strip(),
                'provenance_hash': prov_hash,
                'citation': section_citation,  # Add citation to each section
                'loinc_code': sec_data['loinc_code']  # Add LOINC code for tracking
            })

    except Exception as e:
        logger.error(f"Error extracting sections: {str(e)}")
    
    return sections

def create_knowledge_graph(documents: List[Dict[str, Any]], prov_manager: ProvenanceManager) -> Dict[str, Any]:
    """Create a knowledge graph from the processed documents using FDA SPL identifiers and enhanced relationship types."""
    nodes = []
    relationships = []
    for doc in documents:
        try:
            doc_id = doc.get('unique_id', '')
            doc_prov_hash = doc.get('provenance_hash', '')
            
            # --- Include AMA citation and application info in document node ---
            doc_properties = {
                'fda_set_id': doc.get('fda_set_id', ''), 
                'title': doc.get('title', ''),
                'manufacturer': doc.get('manufacturer', ''), 
                'ndc_codes': doc.get('ndc_codes', []),
                'provenance_fda_spl': doc_prov_hash,
                'ama_citation': doc.get('ama_citation', '')  # Add AMA citation
            }
            
            # --- NEW: Add application information if available ---
            if 'application_type' in doc:
                doc_properties['application_type'] = doc.get('application_type')
            if 'application_number' in doc:
                doc_properties['application_number'] = doc.get('application_number')
            if 'approval_date' in doc:
                doc_properties['approval_date'] = doc.get('approval_date')
            
            # --- NEW: Add SPL Completeness Score ---
            if 'spl_completeness_score' in doc:
                doc_properties['spl_completeness_score'] = doc.get('spl_completeness_score')
            
            # --- NEW: Add Core Clinical Completeness Score ---
            if 'core_clinical_completeness' in doc:
                doc_properties['core_clinical_completeness'] = doc.get('core_clinical_completeness')
            
            doc_node = {
                'id': doc_id, 
                'labels': ['Document', 'PackageInsert'], 
                'properties': doc_properties
            }
            nodes.append(doc_node)
            
            for section in doc.get('sections', []):
                section_id = section.get('section_unique_id', '')
                section_type = section.get('section_type', 'OTHER')
                section_prov_hash = section.get('provenance_hash', '')
                
                # --- Include citation and LOINC code in section node ---
                section_node = {
                    'id': section_id, 
                    'labels': ['Section', section_type],
                    'properties': {
                        'title': section.get('title', ''), 
                        'content': section.get('content', ''),
                        'provenance_fda_spl': section_prov_hash,
                        'citation': section.get('citation', ''),  # Add section citation
                        'loinc_code': section.get('loinc_code', '')  # Add LOINC code
                    }
                }
                nodes.append(section_node)
                
                # ENHANCED: Use section-specific relationship types based on section type
                relationship_type = SECTION_TO_RELATIONSHIP_MAP.get(section_type, 'HAS_SECTION')
                
                # FIXED: Add provenance to relationships with enhanced relationship type
                rel_prov_hash = prov_manager.create_provenance_record(
                    data_type='relationships', source='fda_spl', source_file='document_section_relation',
                    fda_document_id=doc.get('fda_document_id', ''), fda_set_id=doc.get('fda_set_id', ''),
                    relationship_type=relationship_type, section_type=section_type
                )
                
                rel = {
                    'id': hashlib.md5(f"{doc_id}_{relationship_type}_{section_id}".encode()).hexdigest(),
                    'type': relationship_type, 'start_node': doc_id, 'end_node': section_id,
                    'properties': {
                        'section_type': section_type,
                        'provenance_fda_spl': rel_prov_hash
                    }
                }
                relationships.append(rel)
        except Exception as e:
            logger.error(f"Error creating KG for doc {doc.get('file_path', 'unknown')}: {str(e)}")
    return {'nodes': nodes, 'relationships': relationships}

def process_xml_files(xml_dir: str, limit: Optional[int] = None, output_dir: str = 'output') -> Dict[str, Any]:
    """Process XML files and extract drug information using FDA SPL identifiers."""
    xml_path = Path(xml_dir)
    ledger_file = os.path.join(output_dir, 'provenance_ledger.json')
    prov_manager = ProvenanceManager(ledger_file)
    xml_files = list(xml_path.glob('*.xml'))
    if limit: xml_files = xml_files[:limit]
    logger.info(f"Processing {len(xml_files)} files" + (" (limited)" if limit else ""))
    
    documents = []
    
    # Initialize counters for both section instances and unique drugs
    section_counts = defaultdict(int)  # Total section instances
    drug_section_counts = defaultdict(int)  # Unique drugs with each section type
    relationship_type_counts = defaultdict(int)
    application_type_counts = defaultdict(int)  # NEW: Count application types
    
    # --- NEW: Variables for SPL Completeness Score ---
    all_valid_scores = []
    low_score_docs = []
    
    # --- NEW: Variables for Core Clinical Completeness Score ---
    all_core_clinical_scores = []

    # NEW: Track start time for progress reporting
    start_time = time.time()
    
    # --- V21 FIX: Track processed set IDs to prevent duplicates ---
    processed_set_ids = set()
    duplicates_skipped = 0

    for i, xml_file in enumerate(xml_files):
        try:
            tree = ET.parse(xml_file)
            root = tree.getroot()
            
            # --- V21 FIX: Check if we've already processed this set ID ---
            set_id_elem = root.find('.//ns0:setId', SPL_NS)
            if set_id_elem is not None:
                set_id = set_id_elem.get('root', '')
                if set_id in processed_set_ids:
                    duplicates_skipped += 1
                    continue
                processed_set_ids.add(set_id)
            
            # --- NEW: Perform the ground truth census ---
            ground_truth_loinc_codes = get_spl_section_census(root)

            drug_info = extract_fda_drug_info(root, str(xml_file), prov_manager)
            
            # --- Pass AMA citation to section extraction ---
            ama_citation = drug_info.get('ama_citation', '')
            sections = extract_sections_with_provenance(
                root, 
                drug_info.get('fda_document_id', ''), 
                prov_manager, 
                drug_info.get('provenance_hash', ''),
                ama_citation
            )
            
            drug_info['sections'] = sections

            # --- NEW: Compare parsed results to the ground truth ---
            extracted_loinc_codes = set()
            for section in sections:
                loinc_code = section.get('loinc_code')
                if loinc_code and loinc_code != 'TITLE_MATCH' and loinc_code != 'SYNTHETIC':
                    extracted_loinc_codes.add(loinc_code)

            # --- FIXED: Calculate the score for this document ---
            # The denominator is the number of "important" sections the FDA provided.
            # We only care about sections in our master map.
            relevant_ground_truth = ground_truth_loinc_codes.intersection(LOINC_CODE_MAP.keys())
            
            # The numerator is the number of those sections we successfully parsed.
            relevant_extracted = extracted_loinc_codes.intersection(LOINC_CODE_MAP.keys())

            spl_score = 100.0
            if len(relevant_ground_truth) > 0:
                spl_score = (len(relevant_extracted) / len(relevant_ground_truth)) * 100
            
            # Store this score with the document data for later analysis
            drug_info['spl_completeness_score'] = spl_score
            all_valid_scores.append(spl_score)
            
            if spl_score < 100.0:
                drug_info['ground_truth_sections'] = list(relevant_ground_truth)
                drug_info['extracted_sections'] = list(relevant_extracted)
                drug_info['missing_sections'] = list(relevant_ground_truth - relevant_extracted)
                low_score_docs.append(drug_info)

            # --- NEW: Calculate core clinical completeness score ---
            core_clinical_ground_truth = ground_truth_loinc_codes.intersection(CORE_CLINICAL_LOINC_CODES.keys())
            core_clinical_extracted = extracted_loinc_codes.intersection(CORE_CLINICAL_LOINC_CODES.keys())
            
            core_clinical_score = 100.0
            if len(core_clinical_ground_truth) > 0:
                core_clinical_score = (len(core_clinical_extracted) / len(core_clinical_ground_truth)) * 100
            
            drug_info['core_clinical_completeness'] = core_clinical_score
            all_core_clinical_scores.append(core_clinical_score)

            documents.append(drug_info)
            
            drug_id = drug_info.get('unique_id', 'unknown')
            found_sections = set()
            
            for section in sections:
                section_type = section.get('section_type', 'OTHER')
                section_counts[section_type] += 1
                found_sections.add(section_type)
                
                # Count relationship types
                relationship_type = SECTION_TO_RELATIONSHIP_MAP.get(section_type, 'HAS_SECTION')
                relationship_type_counts[relationship_type] += 1
            
            # Count unique drugs with each section type
            for section_type in found_sections:
                drug_section_counts[section_type] += 1
            
            # --- Count application types ---
            app_type = drug_info.get('application_type')
            if app_type:
                application_type_counts[app_type] += 1
            
            # NEW: Update progress
            update_progress(i+1, len(xml_files), start_time)
                
        except Exception as e:
            logger.error(f"Error processing {xml_file}: {str(e)}")
    
    # Add a final newline to the progress output
    print()
    
    # --- V21 FIX: Report duplicate statistics ---
    if duplicates_skipped > 0:
        logger.info(f"Skipped {duplicates_skipped:,} duplicate documents based on set ID")
    
    kg = create_knowledge_graph(documents, prov_manager)
    prov_manager.save_ledger()
    
    # --- NEW: Calculate and store the overall SPL Completeness Score ---
    overall_spl_completeness_score = 0.0
    if all_valid_scores:
        overall_spl_completeness_score = sum(all_valid_scores) / len(all_valid_scores)
    
    # --- NEW: Calculate and store the overall Core Clinical Completeness Score ---
    overall_core_clinical_completeness = 0.0
    if all_core_clinical_scores:
        overall_core_clinical_completeness = sum(all_core_clinical_scores) / len(all_core_clinical_scores)
    
    # Return both section instance counts and drug section counts
    return {
        'documents': documents, 
        'knowledge_graph': kg, 
        'section_counts': dict(section_counts),
        'section_drug_counts': dict(drug_section_counts),
        'relationship_type_counts': dict(relationship_type_counts),
        'application_type_counts': dict(application_type_counts),  # Add application type counts
        'spl_completeness_score': overall_spl_completeness_score,
        'core_clinical_completeness': overall_core_clinical_completeness,  # Add core clinical score
        'low_score_documents': low_score_docs,
        'duplicates_skipped': duplicates_skipped  # V21 FIX: Report duplicates skipped
    }

def verify_counts(documents: List[Dict[str, Any]], reported_counts: Dict[str, int]) -> bool:
    """Verify the reported counts by directly analyzing the documents."""
    logger.info("Performing self-verification of section counts...")
    verified_counts = defaultdict(int)
    critical_sections = ['INDICATIONS_AND_USAGE', 'DOSAGE_AND_ADMINISTRATION', 'DOSAGE_FORMS_AND_STRENGTHS']
    
    # Count unique drugs with each section type, not total section instances
    for doc in documents:
        found_sections = set()
        for section in doc.get('sections', []):
            section_type = section.get('section_type', 'OTHER')
            found_sections.add(section_type)
        
        for section_type in found_sections:
            verified_counts[section_type] += 1
    
    all_match = True
    for section in critical_sections:
        reported = reported_counts.get(section, 0)
        verified = verified_counts.get(section, 0)
        if reported != verified:
            logger.error(f"COUNT MISMATCH for {section}: Reported {reported}, Verified {verified}")
            all_match = False
        else:
            logger.info(f"Verified {section}: {verified} out of {len(documents)} drugs")
    
    return all_match

def main():
    parser = argparse.ArgumentParser(description='Process DailyMed XML files and build a drug knowledge graph.')
    parser.add_argument('--xml-dir', required=True, help='Directory containing XML files')
    parser.add_argument('--output-dir', default='output', help='Output directory for processed data')
    parser.add_argument('--limit', type=int, help='Limit the number of files to process')
    args = parser.parse_args()
    
    output_dir = Path(args.output_dir)
    output_dir.mkdir(exist_ok=True)
    
    result = process_xml_files(args.xml_dir, args.limit, str(output_dir))
    
    # Verify using the correct drug section counts
    is_valid = verify_counts(result['documents'], result['section_drug_counts'])
    if not is_valid:
        logger.error("CRITICAL: Self-verification failed. The reported counts may be inaccurate.")
    
    with open(output_dir / 'enhanced_chunked_documents.json', 'w') as f:
        json.dump(result['documents'], f, indent=2)
    with open(output_dir / 'enhanced_kg_chunks.json', 'w') as f:
        json.dump(result['knowledge_graph'], f, indent=2)
    with open(output_dir / 'section_counts.json', 'w') as f:
        json.dump(result['section_counts'], f, indent=2)
    with open(output_dir / 'section_drug_counts.json', 'w') as f:
        json.dump(result['section_drug_counts'], f, indent=2)
    with open(output_dir / 'relationship_type_counts.json', 'w') as f:
        json.dump(result['relationship_type_counts'], f, indent=2)
    with open(output_dir / 'application_type_counts.json', 'w') as f:  # Save application type counts
        json.dump(result['application_type_counts'], f, indent=2)
    with open(output_dir / 'low_score_documents.json', 'w') as f: # Save low score docs for debugging
        json.dump(result['low_score_documents'], f, indent=2)

    set_ids = [doc.get('fda_set_id', '') for doc in result['documents'] if doc.get('fda_set_id')]
    with open(output_dir / 'fda_set_ids.json', 'w') as f:
        json.dump(set_ids, f, indent=2)

    logger.info(f"Exported {len(result['documents'])} documents.")
    logger.info(f"Exported {len(result['knowledge_graph']['nodes'])} nodes and {len(result['knowledge_graph']['relationships'])} relationships.")
    logger.info(f"Provenance ledger saved to {output_dir}/provenance_ledger.json")
    
    # Calculate total sections and overall hit rate
    total_docs = len(result['documents'])
    total_sections = sum(result['section_counts'].values())
    
    print("\n=== Document Processing Summary ===")
    print(f"Total files: {total_docs}")
    print(f"Total chunks: {total_sections}")
    
    # --- V21 FIX: Report duplicates skipped ---
    if 'duplicates_skipped' in result:
        print(f"Duplicates skipped: {result['duplicates_skipped']:,}")
    
# --- NEW: Print the SPL Completeness Score ---
    print(f"\nOverall SPL Completeness Score: {result['spl_completeness_score']:.1f}%")
    print(f"Overall Core Clinical Completeness: {result['core_clinical_completeness']:.1f}%")
    
    # Print section statistics
    print("\n=== Section Statistics ===")
    print("Total Section Instances (by type):")
    for section_type, count in sorted(result['section_counts'].items(), key=lambda x: x[1], reverse=True):
        print(f"  {section_type}: {count}")
    
    print("\nUnique Drugs with Each Section Type:")
    for section_type, count in sorted(result['section_drug_counts'].items(), key=lambda x: x[1], reverse=True):
        percentage = (count / total_docs) * 100 if total_docs > 0 else 0
        print(f"  {section_type}: {count}/{total_docs} ({percentage:.1f}%)")
    
    # Print application type statistics
    print("\n=== Application Type Statistics ===")
    for app_type, count in sorted(result['application_type_counts'].items(), key=lambda x: x[1], reverse=True):
        percentage = (count / total_docs) * 100 if total_docs > 0 else 0
        print(f"  {app_type}: {count}/{total_docs} ({percentage:.1f}%)")
    
    # Print relationship type statistics
    print("\n=== Relationship Type Statistics ===")
    for rel_type, count in sorted(result['relationship_type_counts'].items(), key=lambda x: x[1], reverse=True):
        print(f"  {rel_type}: {count}")
    
    # Print low score documents summary
    if result['low_score_documents']:
        print(f"\n=== Documents with Incomplete SPL Parsing ===")
        print(f"Number of documents with <100% completeness: {len(result['low_score_documents'])}")
        for doc in result['low_score_documents'][:5]:  # Show first 5 examples
            print(f"  {doc.get('title', 'Unknown')}: {doc.get('spl_completeness_score', 0):.1f}%")
            if 'missing_sections' in doc:
                print(f"    Missing: {', '.join(doc['missing_sections'][:3])}{'...' if len(doc['missing_sections']) > 3 else ''}")
        if len(result['low_score_documents']) > 5:
            print(f"  ... and {len(result['low_score_documents']) - 5} more")

if __name__ == '__main__':
    main()
