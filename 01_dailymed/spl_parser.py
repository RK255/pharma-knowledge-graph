#!/usr/bin/env python3
"""
DailyMed SPL Parser - Streamlined Version
Parses DailyMed XML files and extracts structured drug information with sections.

Outputs:
- dailymed_documents.json: Parsed documents for GRC-20 conversion
"""

import os
import json
import logging
import argparse
import hashlib
import re
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Set, Any
from collections import defaultdict
from datetime import datetime
import xml.etree.ElementTree as ET

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# SPL XML namespace
SPL_NS = {'ns0': 'urn:hl7-org:v3'}

# =============================================================================
# LOINC CODE MAPPINGS
# =============================================================================

# Master LOINC code to section type mapping
# Format: 'LOINC_CODE': ('SECTION_TYPE', is_core_clinical)
LOINC_CODES = {
    # Core Clinical Sections (required for basic drug information)
    '34066-1': ('BOXED_WARNING', True),
    '34067-9': ('INDICATIONS_AND_USAGE', True),
    '34068-7': ('DOSAGE_AND_ADMINISTRATION', True),
    '43678-2': ('DOSAGE_FORMS_AND_STRENGTHS', True),
    '34070-3': ('CONTRAINDICATIONS', True),
    '43685-7': ('WARNINGS_AND_PRECAUTIONS', True),
    '42232-9': ('WARNINGS_AND_PRECAUTIONS', True),
    '34084-4': ('ADVERSE_REACTIONS', True),
    '90374-0': ('ADVERSE_REACTIONS', True),
    '90375-7': ('ADVERSE_REACTIONS', True),
    '34073-7': ('DRUG_INTERACTIONS', True),
    '34074-5': ('DRUG_INTERACTIONS', True),
    '43684-0': ('USE_IN_SPECIFIC_POPULATIONS', True),
    # Subsection LOINC codes are in SUBSECTION_LOINC_MAP and skipped in first pass
    # 42228-7, 77290-5, 34080-2, 34081-0, 34082-8, 77291-3, 88828-9, 88829-7, 88830-5, 34079-4
    '34088-5': ('OVERDOSAGE', True),
    '34089-3': ('DESCRIPTION', True),
    '34090-1': ('CLINICAL_PHARMACOLOGY', True),
    # Subsection codes (43679-0, 43681-6, 43682-4, 49489-8, 66106-6, 88830-5) in SUBSECTION_LOINC_MAP
    '43680-8': ('NONCLINICAL_TOXICOLOGY', True),
    # 34083-6, 34091-9 are subsection codes in SUBSECTION_LOINC_MAP
    '34069-5': ('HOW_SUPPLIED', True),
    '44425-7': ('HOW_SUPPLIED', True),
    '34076-0': ('INFORMATION_FOR_PATIENTS', True),
    '88436-1': ('INFORMATION_FOR_PATIENTS', True),
    '59845-8': ('INFORMATION_FOR_PATIENTS', True),
    '50744-2': ('INFORMATION_FOR_PATIENTS', True),
    '68498-5': ('INFORMATION_FOR_PATIENTS', True),
    '42230-3': ('INFORMATION_FOR_PATIENTS', True),
    '42231-1': ('INFORMATION_FOR_PATIENTS', True),
    '34092-7': ('CLINICAL_STUDIES', True),
    
    # Additional Sections
    '34093-5': ('REFERENCES', False),
    '42229-5': ('OTHER', False),
    '48780-1': ('OTHER', False),
    '48779-3': ('OTHER', False),
    '51945-4': ('OTHER', False),
    '43683-2': ('RECENT_MAJOR_CHANGES', False),
    '34077-8': ('TERATOGENIC_EFFECTS', False),
    '34078-6': ('NONTERATOGENIC_EFFECTS', False),
    # Additional LOINC codes identified by research
    '34071-1': ('WARNINGS_AND_PRECAUTIONS', False),  # Older WARNINGS section (pre-PLRR)
    '34072-9': ('OTHER', False),                     # General subsection
    '34075-2': ('OTHER', False),                     # Laboratory Tests subsection
    '51727-6': ('INACTIVE_INGREDIENTS', False),
    '69759-9': ('RISKS', False),
    '60559-2': ('COMPONENTS', False),
    '55106-9': ('ACTIVE_INGREDIENTS', False),
    '50565-1': ('OTC_KEEP_OUT_OF_REACH', False),
    '55105-1': ('OTC_PURPOSE', False),
    '60561-8': ('OTHER_SAFETY_INFO', False),
    '50741-8': ('SAFE_HANDLING_WARNING', False),
    '50566-9': ('OTC_STOP_USE', False),
    '50570-1': ('OTC_DO_NOT_USE', False),
    '50567-7': ('OTC_WHEN_USING', False),
    '53413-1': ('OTC_QUESTIONS', False),
    '71744-7': ('HEALTHCARE_PROVIDER_LETTER', False),
    '50569-3': ('OTC_ASK_DOCTOR', False),
    '50744-2': ('INFORMATION_FOR_CAREGIVERS', False),
    '38056-8': ('SUPPLEMENTAL_PATIENT_MATERIAL', False),
    '69763-1': ('DISPOSAL_INSTRUCTIONS', False),
    '69718-5': ('STATEMENT_OF_IDENTITY', False),
    '50742-6': ('ENVIRONMENTAL_WARNING', False),
    '53414-9': ('OTC_PREGNANCY_BREASTFEEDING', False),
    '60560-0': ('INTENDED_USE', False),
    '54433-8': ('USER_SAFETY_WARNINGS', False),
    '50745-9': ('VETERINARY_INDICATIONS', False),
    '82598-4': ('REMS_MEDICATION_GUIDE', False),
    '69719-3': ('HEALTH_CLAIM', False),
    '50568-5': ('OTC_ASK_DOCTOR_PHARMACIST', False),
    '60558-4': ('CLEANING_INSTRUCTIONS', False),
    '69761-5': ('ALARMS', False),
    '82347-6': ('REMS_SUMMARY', False),
    '60562-6': ('ADMINISTRATION_METHODS', False),
    '60563-4': ('SAFETY_EFFECTIVENESS_SUMMARY', False),
    '87523-7': ('REMS_ADMIN_INFO', False),
    '60555-0': ('ACCESSORIES', False),
    '69760-7': ('COMPATIBLE_ACCESSORIES', False),
    '60556-8': ('ASSEMBLY_INSTRUCTIONS', False),
    '69758-1': ('DEVICE_DIAGRAM', False),
    '82350-0': ('REMS_IMPLEMENTATION_SYSTEM', False),
    '82344-3': ('REMS_COMMUNICATION_PLAN', False),
    '60557-6': ('CALIBRATION_INSTRUCTIONS', False),
    '69762-3': ('TROUBLESHOOTING', False),
    # Drug Abuse sections
    '42227-9': ('DRUG_ABUSE_AND_DEPENDENCE', False),
    '34085-1': ('DRUG_ABUSE_AND_DEPENDENCE', False),
    '34087-7': ('DRUG_ABUSE_AND_DEPENDENCE', False),
    '34086-9': ('DRUG_ABUSE_AND_DEPENDENCE', False),
}

# Build lookup dictionaries
LOINC_TO_SECTION = {code: data[0] for code, data in LOINC_CODES.items()}
CORE_CLINICAL_CODES = {code for code, data in LOINC_CODES.items() if data[1]}

# Section title fallback mapping (normalized title -> section type)
SECTION_TITLE_FALLBACK = {
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
    'BOXEDWARNING': 'BOXED_WARNING',
}

# Subsection to parent mapping (by title)
# Used as fallback when LOINC code is missing or maps to OTHER
SUBSECTION_PARENTS = {
    'Clinical Trials Experience': 'ADVERSE_REACTIONS',
    'Clinical Trials': 'ADVERSE_REACTIONS',
    'Postmarketing Experience': 'ADVERSE_REACTIONS',
    'Pregnancy': 'USE_IN_SPECIFIC_POPULATIONS',
    'Labor and Delivery': 'USE_IN_SPECIFIC_POPULATIONS',
    'Nursing Mothers': 'USE_IN_SPECIFIC_POPULATIONS',
    'Lactation': 'USE_IN_SPECIFIC_POPULATIONS',
    'Pediatric Use': 'USE_IN_SPECIFIC_POPULATIONS',
    'Geriatric Use': 'USE_IN_SPECIFIC_POPULATIONS',
    'Hepatic Impairment': 'USE_IN_SPECIFIC_POPULATIONS',
    'Renal Impairment': 'USE_IN_SPECIFIC_POPULATIONS',
    'Females and Males of Reproductive Potential': 'USE_IN_SPECIFIC_POPULATIONS',
    'Female and Male of Reproductive Potential': 'USE_IN_SPECIFIC_POPULATIONS',
    'General': 'WARNINGS_AND_PRECAUTIONS',
    'Laboratory Tests': 'WARNINGS_AND_PRECAUTIONS',
    'Carcinogenesis and Mutagenesis and Impairment of Fertility': 'NONCLINICAL_TOXICOLOGY',
    'Carcinogenesis, Mutagenesis, Impairment of Fertility': 'NONCLINICAL_TOXICOLOGY',
    'Mechanism of Action': 'CLINICAL_PHARMACOLOGY',
    'Pharmacodynamics': 'CLINICAL_PHARMACOLOGY',
    'Pharmacokinetics': 'CLINICAL_PHARMACOLOGY',
    'Microbiology': 'CLINICAL_PHARMACOLOGY',
    'Pharmacogenomics': 'CLINICAL_PHARMACOLOGY',
    'Immunogenicity': 'CLINICAL_PHARMACOLOGY',
}

# =============================================================================
# FDA STANDARD SECTION NUMBERING
# =============================================================================

# Maps section_type -> FDA standard section number
SECTION_NUMBERING = {
    'INDICATIONS_AND_USAGE': '1',
    'DOSAGE_AND_ADMINISTRATION': '2',
    'DOSAGE_FORMS_AND_STRENGTHS': '3',
    'CONTRAINDICATIONS': '4',
    'WARNINGS_AND_PRECAUTIONS': '5',
    'ADVERSE_REACTIONS': '6',
    'DRUG_INTERACTIONS': '7',
    'USE_IN_SPECIFIC_POPULATIONS': '8',
    'DRUG_ABUSE_AND_DEPENDENCE': '9',
    'OVERDOSAGE': '10',
    'DESCRIPTION': '11',
    'CLINICAL_PHARMACOLOGY': '12',
    'NONCLINICAL_TOXICOLOGY': '13',
    'CLINICAL_STUDIES': '14',
    'REFERENCES': '15',
    'HOW_SUPPLIED': '16',
    'INFORMATION_FOR_PATIENTS': '17',
}

# LOINC codes that are SUBSECTIONS (not parent sections).
# Maps loinc_code -> (parent_section_type, standard_subsection_number)
SUBSECTION_LOINC_MAP = {
    # USE_IN_SPECIFIC_POPULATIONS subsections (parent=8)
    '42228-7': ('USE_IN_SPECIFIC_POPULATIONS', '8.1'),   # Pregnancy
    '77290-5': ('USE_IN_SPECIFIC_POPULATIONS', '8.2'),   # Lactation
    '34080-2': ('USE_IN_SPECIFIC_POPULATIONS', '8.2'),   # Nursing Mothers (old code for Lactation)
    '77291-3': ('USE_IN_SPECIFIC_POPULATIONS', '8.3'),   # Females and Males of Reproductive Potential
    '34081-0': ('USE_IN_SPECIFIC_POPULATIONS', '8.4'),   # Pediatric Use
    '34082-8': ('USE_IN_SPECIFIC_POPULATIONS', '8.5'),   # Geriatric Use
    '88828-9': ('USE_IN_SPECIFIC_POPULATIONS', '8.6'),   # Renal Impairment
    '88829-7': ('USE_IN_SPECIFIC_POPULATIONS', '8.7'),   # Hepatic Impairment
    '34079-4': ('USE_IN_SPECIFIC_POPULATIONS', '8.6'),   # Renal Impairment (older code)
    # CLINICAL_PHARMACOLOGY subsections (parent=12)
    '43679-0': ('CLINICAL_PHARMACOLOGY', '12.1'),        # Mechanism of Action
    '43681-6': ('CLINICAL_PHARMACOLOGY', '12.2'),        # Pharmacodynamics
    '43682-4': ('CLINICAL_PHARMACOLOGY', '12.3'),        # Pharmacokinetics
    '49489-8': ('CLINICAL_PHARMACOLOGY', '12.4'),        # Microbiology
    '66106-6': ('CLINICAL_PHARMACOLOGY', '12.5'),        # Pharmacogenomics
    '88830-5': ('CLINICAL_PHARMACOLOGY', '12.6'),        # Immunogenicity
    # NONCLINICAL_TOXICOLOGY subsections (parent=13)
    '34083-6': ('NONCLINICAL_TOXICOLOGY', '13.1'),       # Carcinogenesis/Mutagenesis/Fertility
    '34091-9': ('NONCLINICAL_TOXICOLOGY', '13.1'),       # Carcinogenesis/Mutagenesis/Fertility (alt code)
    # 34079-4 is sometimes a parent "Use in Specific Populations" in older labels
    # 34091-9 is sometimes a parent "Nonclinical Toxicology" in older labels
    # Both are left out of subsection map to avoid losing sections in old labels
}

# LOINC codes that should be treated as subsections (aggregated into parent, not standalone)
SUBSECTION_LOINC_CODES = set(SUBSECTION_LOINC_MAP.keys())

# FDA Application codes
APPLICATION_CODES = {
    'C73583': 'ANADA', 'C73584': 'ANDA', 'C73585': 'BLA', 'C73594': 'NDA',
    'C73605': 'NDA authorized generic', 'C200263': 'OTC Monograph Drug',
    'C75302': 'IND', 'C73593': 'NADA', 'C73590': 'Export only',
    'C73627': 'Unapproved drug other', 'C73614': 'Unapproved homeopathic',
}

# =============================================================================
# TEXT WASHER INTEGRATION
# =============================================================================

sys.path.insert(0, str(Path(__file__).parent))
try:
    from text_washer import TextWasher
    TEXT_WASHER_AVAILABLE = True
except ImportError:
    TEXT_WASHER_AVAILABLE = False
    logger.warning("text_washer.py not found. Falling back to basic text extraction.")


def wash_section_content(element: ET.Element) -> str:
    """
    Extracts text from an element and cleans it using TextWasher if available.
    Falls back to basic extraction if not.
    """
    if element is None:
        return ""
    
    if TEXT_WASHER_AVAILABLE:
        washer = TextWasher()
        return washer.wash_element(element)
    else:
        # Fallback logic mirrors the TextWasher's basic extraction + basic cleaning
        return clean_text(extract_text(element))


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def extract_text(element: ET.Element) -> str:
    """Extract all text from an XML element recursively."""
    if element is None:
        return ""
    
    # Handle multimedia references
    if element.tag.endswith('renderMultiMedia'):
        ref = element.get('referencedObject')
        return f"[Image: {ref}]" if ref else "[Image]"
    
    parts = []
    if element.text:
        parts.append(element.text)
    
    for child in element:
        child_text = extract_text(child)
        if child_text:
            parts.append(child_text)
        if child.tail:
            parts.append(child.tail)
    
    return ' '.join(parts).strip()


def clean_text(text: str) -> str:
    """Normalize text content (Basic fallback)."""
    if not text:
        return ""
    # 1. Normalize line endings
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    # 2. Normalize whitespace
    text = re.sub(r'\s+', ' ', text)
    # 3. Remove HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    # 4. Decode entities
    for old, new in [('&amp;', '&'), ('&lt;', '<'), ('&gt;', '>'), ('&quot;', '"'), ('&apos;', "'")]:
        text = text.replace(old, new)
    return text.strip()


def normalize_section_name(name: str) -> str:
    """Normalize section name for comparison."""
    return re.sub(r'[\s_\-]', '', name).upper()


def strip_existing_number(title: str) -> str:
    """Strip a leading section number (e.g. '5 ' or '5.1 ' or '5.1\t') from a title."""
    return re.sub(r'^\s*\d+(?:\.\d+)?\s*', '', title).strip()


def add_section_number(title: str, section_type: str) -> str:
    """
    Prepend the FDA standard section number to a parent section title.
    If the title already starts with the correct number, keep as-is.
    If it starts with a wrong number, replace it.
    If it has no number, prepend the correct one.
    If the title is empty, generate a default from the section type.
    Handles formats: "5 Title", "5. Title", "5\tTitle", "5.1 Title".
    """
    number = SECTION_NUMBERING.get(section_type)
    if not number:
        return title

    title = title.strip()
    if not title:
        # Generate default title from section type (e.g. "INDICATIONS_AND_USAGE" -> "INDICATIONS AND USAGE")
        default_title = section_type.replace('_', ' ').title()
        return f"{number} {default_title}"

    # Check if title already starts with a number (optionally followed by . or whitespace)
    match = re.match(r'^(\d+(?:\.\d+)?)[.\s]+(.*)', title)
    if match:
        existing_num = match.group(1)
        rest = match.group(2)
        if existing_num == number:
            # Already has correct number - normalize format to "N Title"
            return f"{number} {rest}"
        else:
            return f"{number} {rest}"  # Replace wrong number
    else:
        return f"{number} {title}"


def add_subsection_number(title: str, subsection_num: str, parent_type: str) -> str:
    """
    Prepend the FDA standard subsection number (e.g. '8.1') to a subsection title.
    If the title already starts with the correct number, keep as-is.
    If it starts with a wrong number, replace it.
    If it has no number, prepend the correct one.
    If the title is empty, return empty string (caller should skip).
    Handles formats: "8.1 Title", "8.1. Title", "8.1\tTitle".
    """
    full_num = subsection_num  # e.g. '8.1'

    title = title.strip()
    if not title:
        return ''  # Empty title - caller should skip this subsection

    # Check if title already starts with a number like N or N.M
    match = re.match(r'^(\d+(?:\.\d+)?)[.\s]+(.*)', title)
    if match:
        existing_num = match.group(1)
        rest = match.group(2)
        if existing_num == full_num:
            # Already has correct number - normalize format to "N.M Title"
            return f"{full_num} {rest}"
        else:
            return f"{full_num} {rest}"  # Replace wrong number
    else:
        return f"{full_num} {title}"


def generate_uuid(seed: str) -> str:
    """Generate deterministic UUID from seed."""
    return hashlib.md5(seed.encode()).hexdigest()


# =============================================================================
# XML EXTRACTION FUNCTIONS
# =============================================================================

def extract_document_metadata(root: ET.Element, file_path: str) -> Dict[str, Any]:
    """Extract core document metadata from SPL XML."""
    doc_info = {'file_path': file_path}
    
    # Document IDs
    for elem in root.findall('.//ns0:id', SPL_NS):
        root_id = elem.get('root')
        if root_id:
            doc_info['fda_document_id'] = root_id
            break
    
    for elem in root.findall('.//ns0:setId', SPL_NS):
        root_id = elem.get('root')
        if root_id:
            doc_info['fda_set_id'] = root_id
            break
    
    for elem in root.findall('.//ns0:versionNumber', SPL_NS):
        doc_info['version_number'] = elem.get('value')
        break
    
    # Drug names - prioritize manufacturedProduct/name
    drug_names = set()
    for name_elem in root.findall('.//ns0:manufacturedProduct/ns0:name', SPL_NS):
        name = clean_text(extract_text(name_elem))
        if name:
            drug_names.add(name)
    
    if not drug_names:
        title_elem = root.find('.//ns0:title', SPL_NS)
        if title_elem is not None:
            title = clean_text(extract_text(title_elem))
            # Extract first word(s) as drug name
            match = re.match(r'^([A-Za-z0-9\-]+(?:\s+[A-Za-z0-9\-]+)*)', title)
            if match:
                drug_names.add(match.group(1))
    
    if drug_names:
        doc_info['drug_names'] = sorted(drug_names)
        doc_info['title'] = sorted(drug_names)[0]
    
    # Effective time
    for elem in root.findall('.//ns0:effectiveTime', SPL_NS):
        doc_info['effective_time'] = elem.get('value')
        break
    
    # Manufacturer
    for elem in root.findall('.//ns0:author//ns0:representedOrganization//ns0:name', SPL_NS):
        doc_info['manufacturer'] = clean_text(extract_text(elem))
        break
    
    # NDC codes
    ndc_codes = set()
    for code_elem in root.findall('.//ns0:containerPackagedProduct/ns0:code', SPL_NS):
        code = code_elem.get('code')
        if code:
            # Normalize to 5-4-2 format
            clean = code.replace('-', '').zfill(11)
            ndc_codes.add(f"{clean[:5]}-{clean[5:9]}-{clean[9:11]}")
    if ndc_codes:
        doc_info['ndc_codes'] = sorted(ndc_codes)
    
    # Application info (ANDA/NDA)
    for approval in root.findall('.//ns0:approval', SPL_NS):
        id_elem = approval.find('.//ns0:id', SPL_NS)
        code_elem = approval.find('.//ns0:code', SPL_NS)
        
        if id_elem is not None and code_elem is not None:
            app_id = id_elem.get('extension')
            app_code = code_elem.get('code')
            
            if app_id and app_code:
                doc_info['application_number'] = app_id
                doc_info['application_type'] = APPLICATION_CODES.get(app_code, app_code)
                doc_info['application_code'] = app_code
                break
    
    # Generate unique ID
    unique_id = doc_info.get('fda_set_id') or doc_info.get('fda_document_id') or generate_uuid(file_path)
    doc_info['unique_id'] = unique_id
    
    return doc_info


def extract_section_content(section: ET.Element) -> str:
    """
    Extract text content from a section element.
    NOW USES TEXT WASHER.
    """
    content_parts = []
    
    # Direct text element
    text_elem = section.find('ns0:text', SPL_NS)
    if text_elem is not None:
        # --- TEXT WASHER CALL ---
        # We pass the XML element to the washer for deep cleaning
        content_parts.append(wash_section_content(text_elem))
    
    # Nested sections in components
    for component in section.findall('ns0:component', SPL_NS):
        nested = component.find('ns0:section', SPL_NS)
        if nested is not None:
            nested_text = nested.find('ns0:text', SPL_NS)
            if nested_text is not None:
                # --- TEXT WASHER CALL ---
                content_parts.append(wash_section_content(nested_text))
    
    return '\n\n'.join(p for p in content_parts if p.strip()).strip()


def extract_sections(root: ET.Element, doc_id: str) -> List[Dict[str, Any]]:
    """
    Extract all sections from SPL document with proper hierarchy handling.
    
    Parent sections are numbered per FDA standard (1-17).
    Subsections are kept as SEPARATE entries (not aggregated into parent content)
    so cross-references like 'see Warnings and Precautions (5.1)' resolve correctly.
    Each subsection gets its own numbered title (e.g. '8.1 Pregnancy').
    """
    sections = []
    parent_sections = {}  # section_id -> section_data
    subsection_entries = []  # list of subsection dicts to append as separate sections
    seen_section_ids = set()
    orphan_subsections = []  # (parent_type, numbered_title, content, subsection_num) for subs with no parent
    
    all_xml_sections = root.findall('.//ns0:section', SPL_NS)
    
    # First pass: Identify parent sections by LOINC code or title
    for section in all_xml_sections:
        code_elem = section.find('ns0:code', SPL_NS)
        title_elem = section.find('ns0:title', SPL_NS)
        id_elem = section.find('ns0:id', SPL_NS)
        
        if id_elem is None:
            continue
        
        section_id = id_elem.get('root', '')
        if not section_id or section_id in seen_section_ids:
            continue
        
        title = clean_text(extract_text(title_elem)) if title_elem is not None else ''
        
        # Determine section type
        section_type = 'OTHER'
        loinc_code = ''
        
        if code_elem is not None:
            loinc_code = code_elem.get('code', '')
            section_type = LOINC_TO_SECTION.get(loinc_code, 'OTHER')
        
        # Fallback to title matching
        if section_type == 'OTHER' and title:
            normalized = normalize_section_name(title)
            section_type = SECTION_TITLE_FALLBACK.get(normalized, 'OTHER')
        
        # Skip subsection LOINC codes - they'll be handled in the second pass
        if loinc_code in SUBSECTION_LOINC_CODES:
            continue
        
        # Only process recognized sections (not OTHER)
        if section_type == 'OTHER':
            # Check if this is a title-based subsection we should handle
            parent_type_from_title = SUBSECTION_PARENTS.get(title)
            if parent_type_from_title:
                # This is a subsection - will be handled in second pass
                continue
            # Skip unrecognized sections
            continue
        
        seen_section_ids.add(section_id)
        
        # Check if we already have a parent of this type (deduplicate)
        existing_same_type = None
        for pid, pdata in parent_sections.items():
            if pdata['type'] == section_type:
                existing_same_type = pid
                break
        
        # Extract content (This now calls TextWasher internally)
        content = extract_section_content(section)
        
        # Add FDA standard section number to title
        numbered_title = add_section_number(title, section_type)
        
        if existing_same_type:
            # Merge: append content to existing parent, skip duplicate
            if content:
                parent_sections[existing_same_type]['content'] += f"\n\n{content}"
            # If existing title is empty but this one isn't, use this title
            if not parent_sections[existing_same_type]['title'].strip() and numbered_title:
                parent_sections[existing_same_type]['title'] = numbered_title
                parent_sections[existing_same_type]['raw_title'] = title
            continue
        
        parent_sections[section_id] = {
            'type': section_type,
            'title': numbered_title,
            'raw_title': title,
            'content': content,
            'loinc_code': loinc_code,
            'section_id': section_id,
        }
    
    # Second pass: Process subsections as SEPARATE entries with proper numbering
    for section in all_xml_sections:
        id_elem = section.find('ns0:id', SPL_NS)
        title_elem = section.find('ns0:title', SPL_NS)
        code_elem = section.find('ns0:code', SPL_NS)
        
        if id_elem is None:
            continue
        
        section_id = id_elem.get('root', '')
        
        # Skip if already a parent
        if section_id in parent_sections or section_id in seen_section_ids:
            continue
        
        title = clean_text(extract_text(title_elem)) if title_elem is not None else ''
        loinc_code = code_elem.get('code', '') if code_elem is not None else ''
        
        # Determine if this is a subsection and find its parent + subsection number
        subsection_num = None
        parent_type = None
        
        # Case 1: LOINC-coded subsection (e.g. 42228-7 Pregnancy -> 8.1)
        if loinc_code in SUBSECTION_LOINC_MAP:
            parent_type, subsection_num = SUBSECTION_LOINC_MAP[loinc_code]
        
        # Case 2: Title-based subsection matching (SUBSECTION_PARENTS)
        if not parent_type:
            parent_type = SUBSECTION_PARENTS.get(title)
            # If we found a parent type via title, try to infer a subsection number
            if parent_type and not subsection_num:
                # Try to match by known LOINC code even if not in SUBSECTION_LOINC_MAP
                # (e.g. 34079-4 Renal Impairment -> 8.6)
                pass
        
        # Case 3: Numbered subsection title (e.g. "5.1 Myopathy...")
        # These have explicit numbers in the XML title
        subsection_match = re.match(r'^(\d+)\.(\d+)\s+(.+)', title) if title else None
        
        if subsection_num or parent_type or subsection_match:
            content = extract_section_content(section)
            
            # Skip empty-title AND empty-content subsections (truly empty duplicate XML elements)
            if not title and not content:
                continue
            
            # Check for duplicate subsection with same subsection_num for same parent
            if subsection_num and parent_type:
                dup_found = False
                for existing in subsection_entries:
                    if (existing.get('parent_type') == parent_type and 
                        existing.get('subsection_num') == subsection_num):
                        # Merge content into existing subsection
                        if content:
                            existing['content'] += f"\n\n{content}"
                        # If existing title is empty but this one isn't, use this title
                        if not existing['title'].strip() and title:
                            new_title = add_subsection_number(title, subsection_num, parent_type)
                            existing['title'] = new_title
                            existing['raw_title'] = title
                        dup_found = True
                        break
                if dup_found:
                    continue
            
            if subsection_match and not subsection_num:
                # Title has explicit number like "5.1 Myopathy" - extract and use it
                numbered_title = title.strip()
                # Extract the subsection number from the title (e.g. "8.6" from "8.6 Renal Impairment")
                subsection_num = f"{subsection_match.group(1)}.{subsection_match.group(2)}"
                # Try to find parent by the section number prefix
                parent_num = subsection_match.group(1)
                for pid, pdata in parent_sections.items():
                    if pdata['title'].startswith(f"{parent_num} "):
                        parent_type = pdata['type']
                        break
            elif subsection_num and parent_type:
                numbered_title = add_subsection_number(title, subsection_num, parent_type)
            elif parent_type:
                # Title-based subsection without explicit LOINC number
                # Find parent and assign sequential subsection number
                parent_num = SECTION_NUMBERING.get(parent_type)
                if parent_num:
                    # Count existing subsections for this parent to determine sequential number
                    existing_count = sum(1 for s in subsection_entries 
                                         if s.get('parent_type') == parent_type)
                    # Also count orphan subsections for this parent type
                    orphan_count = sum(1 for o in orphan_subsections 
                                       if o[0] == parent_type)
                    seq = existing_count + orphan_count + 1
                    subsection_num = f"{parent_num}.{seq}"
                    numbered_title = add_subsection_number(title, subsection_num, parent_type)
                else:
                    numbered_title = title.strip()
            else:
                numbered_title = title.strip()
            
            seen_section_ids.add(section_id)
            
            # If subsection has no title, merge its content into parent instead of separate entry
            if not numbered_title:
                if parent_type:
                    for pid, pdata in parent_sections.items():
                        if pdata['type'] == parent_type:
                            if content:
                                pdata['content'] += f"\n\n{content}"
                            break
                seen_section_ids.discard(section_id)
                continue
            
            sub_entry = {
                'type': parent_type or 'OTHER',
                'title': numbered_title,
                'raw_title': title,
                'content': content,
                'loinc_code': loinc_code,
                'section_id': section_id,
                'parent_type': parent_type,
                'subsection_num': subsection_num,
            }
            
            # Check if parent exists
            found_parent = False
            if parent_type:
                for pid, pdata in parent_sections.items():
                    if pdata['type'] == parent_type:
                        found_parent = True
                        break
            
            if found_parent:
                subsection_entries.append(sub_entry)
            elif parent_type and parent_type in SECTION_NUMBERING:
                # Orphan subsection - will create synthetic parent
                orphan_subsections.append((parent_type, numbered_title, content, subsection_num, section_id))
                seen_section_ids.discard(section_id)  # Allow re-processing
            # else: skip unrecognized subsections
    
    # Create synthetic parent sections for orphan subsections
    orphan_by_type = defaultdict(list)
    for ptype, title, content, sub_num, sid in orphan_subsections:
        orphan_by_type[ptype].append((title, content, sub_num, sid))
    
    for ptype, subs in orphan_by_type.items():
        has_parent = any(pdata['type'] == ptype for pdata in parent_sections.values())
        if not has_parent and ptype in SECTION_NUMBERING:
            synth_id = f"synthetic_{ptype}_{doc_id}"
            parent_num = SECTION_NUMBERING[ptype]
            readable_type = ptype.replace('_', ' ').title()
            synth_title = f"{parent_num} {readable_type}"
            parent_sections[synth_id] = {
                'type': ptype,
                'title': synth_title,
                'raw_title': readable_type,
                'content': '',  # Parent has no direct content, only subsections
                'loinc_code': '',
                'section_id': synth_id,
            }
            # Now add the orphan subsections as separate entries
            for title, content, sub_num, sid in subs:
                subsection_entries.append({
                    'type': ptype,
                    'title': title,
                    'raw_title': title,
                    'content': content,
                    'loinc_code': '',
                    'section_id': sid,
                    'parent_type': ptype,
                    'subsection_num': sub_num,
                })
    
    # Sort: parent sections first (by FDA number), then their subsections interleaved
    # Build a list with parents followed by their subsections
    # Group subsections by parent_type
    subs_by_parent = defaultdict(list)
    for sub in subsection_entries:
        subs_by_parent[sub['parent_type']].append(sub)
    
    # Sort subsections within each parent by subsection_num (numeric, not string)
    def _sub_sort_key(s):
        num = s.get('subsection_num') or '0.0'
        try:
            parts = num.split('.')
            return tuple(int(p) for p in parts)
        except (ValueError, TypeError):
            return (0,)
    
    for ptype in subs_by_parent:
        subs_by_parent[ptype].sort(key=_sub_sort_key)
    
    # Build final ordered list: for each parent (in FDA order), add parent then its subsections
    ordered_sections = []
    
    # Sort parent sections by FDA section number
    def get_section_order(pdata):
        num = SECTION_NUMBERING.get(pdata['type'], '99')
        try:
            return (int(num), pdata['title'])
        except (ValueError, TypeError):
            return (99, pdata['title'])
    
    sorted_parents = sorted(parent_sections.values(), key=get_section_order)
    
    for pdata in sorted_parents:
        ordered_sections.append({
            'section_id': generate_uuid(f"{doc_id}_{pdata['section_id']}"),
            'section_unique_id': generate_uuid(f"{doc_id}_section_{pdata['section_id']}"),
            'section_type': pdata['type'],
            'title': pdata['title'],
            'content': pdata['content'],
            'loinc_code': pdata['loinc_code'],
        })
        
        # Add subsections for this parent
        for sub in subs_by_parent.get(pdata['type'], []):
            ordered_sections.append({
                'section_id': generate_uuid(f"{doc_id}_{sub['section_id']}"),
                'section_unique_id': generate_uuid(f"{doc_id}_section_{sub['section_id']}"),
                'section_type': sub['type'],
                'title': sub['title'],
                'content': sub['content'],
                'loinc_code': sub['loinc_code'],
            })
    
    # Add any subsections whose parent_type doesn't match any parent (shouldn't happen, but safety)
    placed_subs = set()
    for s in subsection_entries:
        placed_subs.add(s['section_id'])
    
    return ordered_sections


def calculate_completeness(root: ET.Element, extracted_sections: List[Dict]) -> Dict[str, float]:
    """Calculate SPL completeness scores."""
    # Ground truth: all LOINC codes in source
    ground_truth = set()
    for section in root.findall('.//ns0:section', SPL_NS):
        code_elem = section.find('ns0:code', SPL_NS)
        if code_elem is not None:
            code = code_elem.get('code', '')
            if code in LOINC_TO_SECTION:
                ground_truth.add(code)
    
    # Extracted LOINC codes
    extracted = set()
    for sec in extracted_sections:
        code = sec.get('loinc_code', '')
        if code and code in LOINC_TO_SECTION:
            extracted.add(code)
    
    # Overall completeness
    overall = (len(extracted) / len(ground_truth) * 100) if ground_truth else 100.0
    
    # Core clinical completeness
    core_truth = ground_truth & CORE_CLINICAL_CODES
    core_extracted = extracted & CORE_CLINICAL_CODES
    core = (len(core_extracted) / len(core_truth) * 100) if core_truth else 100.0
    
    return {
        'spl_completeness': overall,
        'core_clinical_completeness': core,
        'missing_codes': list(ground_truth - extracted),
    }

# =============================================================================
# MAIN PROCESSING
# =============================================================================

def process_xml_file(file_path: str) -> tuple:
    """Process a single XML file and return parsed document."""
    try:
        tree = ET.parse(file_path)
        root = tree.getroot()
        
        # Check for set_id to detect duplicates
        set_id_elem = root.find('.//ns0:setId', SPL_NS)
        if set_id_elem is not None:
            set_id = set_id_elem.get('root', '')
        else:
            set_id = None
        
        # Extract metadata
        doc_info = extract_document_metadata(root, str(file_path))
        
        # Extract sections
        doc_id = doc_info.get('fda_document_id', '')
        sections = extract_sections(root, doc_id)
        doc_info['sections'] = sections
        
        # Calculate completeness
        completeness = calculate_completeness(root, sections)
        doc_info['spl_completeness_score'] = completeness['spl_completeness']
        doc_info['core_clinical_completeness'] = completeness['core_clinical_completeness']
        if completeness['missing_codes']:
            doc_info['missing_loinc_codes'] = completeness['missing_codes']
        
        return doc_info, set_id
        
    except Exception as e:
        logger.error(f"Error processing {file_path}: {e}")
        return None, None


def process_all_files(xml_dir: str, limit: Optional[int] = None, output_dir: str = None, progress=None) -> Dict[str, Any]:
    """Process all XML files in directory."""
    xml_path = Path(xml_dir)
    xml_files = list(xml_path.glob('*.xml'))
    
    if limit:
        xml_files = xml_files[:limit]
    
    logger.info(f"Processing {len(xml_files)} files")
    
    documents = []
    processed_set_ids = set()
    stats = {
        'total_files': len(xml_files),
        'duplicates_skipped': 0,
        'errors': 0,
        'section_counts': defaultdict(int),
        'application_types': defaultdict(int),
    }
    
    start_time = time.time()
    
    for i, xml_file in enumerate(xml_files):
        if progress and i % 10 == 0:
            progress.report(i / len(xml_files), f"Processing {i+1}/{len(xml_files)}")
        
        result, set_id = process_xml_file(str(xml_file))
        
        if result is None:
            stats['errors'] += 1
            continue
        
        # Skip duplicates
        if set_id and set_id in processed_set_ids:
            stats['duplicates_skipped'] += 1
            continue
        
        if set_id:
            processed_set_ids.add(set_id)
        
        documents.append(result)
        
        # Update stats
        for section in result.get('sections', []):
            stats['section_counts'][section['section_type']] += 1
        
        if 'application_type' in result:
            stats['application_types'][result['application_type']] += 1
        
        # Progress output
        if (i + 1) % 100 == 0 or i == len(xml_files) - 1:
            elapsed = time.time() - start_time
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            eta = (len(xml_files) - i - 1) / rate if rate > 0 else 0
            sys.stdout.write(f"\rProgress: {i+1}/{len(xml_files)} ({(i+1)/len(xml_files)*100:.1f}%) - ETA: {eta/60:.1f}min")
            sys.stdout.flush()
    
    print()  # Newline after progress
    
    return {
        'documents': documents,
        'stats': dict(stats),
    }


def main():
    parser = argparse.ArgumentParser(description='Parse DailyMed XML files')
    parser.add_argument('--xml-dir', required=True, help='Directory containing XML files')
    parser.add_argument('--output-dir', default=None, help='Output directory')
    parser.add_argument('--limit', type=int, help='Limit number of files')
    args = parser.parse_args()
    
    # Default output directory
    if args.output_dir is None:
        base_dir = Path(__file__).parent.parent.parent.parent.parent
        output_dir = base_dir / "data" / "grc20_v2"
    else:
        output_dir = Path(args.output_dir)
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Process files
    result = process_all_files(args.xml_dir, args.limit, str(output_dir))
    
    # Save outputs
    documents = result['documents']
    stats = result['stats']
    
    with open(output_dir / 'dailymed_documents.json', 'w') as f:
        json.dump(documents, f, indent=2)
    
    with open(output_dir / 'parser_stats.json', 'w') as f:
        json.dump(stats, f, indent=2, default=str)
    
    # Print summary
    print(f"\n=== Processing Summary ===")
    print(f"Total documents: {len(documents)}")
    print(f"Duplicates skipped: {stats['duplicates_skipped']}")
    print(f"Errors: {stats['errors']}")
    print(f"\nSection counts:")
    for sec_type, count in sorted(stats['section_counts'].items(), key=lambda x: -x[1])[:20]:
        print(f"  {sec_type}: {count}")
    if stats['application_types']:
        print(f"\nApplication types:")
        for app_type, count in sorted(stats['application_types'].items(), key=lambda x: -x[1]):
            print(f"  {app_type}: {count}")
    
    logger.info(f"Output saved to {output_dir}")


if __name__ == '__main__':
    main()

# Alias for backwards compatibility with pipeline
def process_xml_files(xml_dir: str, limit: Optional[int] = None, output_dir: str = None, progress=None) -> Dict[str, Any]:
    """Alias for process_all_files for backwards compatibility."""
    return process_all_files(xml_dir, limit, output_dir, progress)
