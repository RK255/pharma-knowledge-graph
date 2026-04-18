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
    '42228-7': ('USE_IN_SPECIFIC_POPULATIONS', True),
    '34080-2': ('USE_IN_SPECIFIC_POPULATIONS', True),
    '34081-0': ('USE_IN_SPECIFIC_POPULATIONS', True),
    '34082-8': ('USE_IN_SPECIFIC_POPULATIONS', True),
    '34079-4': ('USE_IN_SPECIFIC_POPULATIONS', True),
    '77290-5': ('USE_IN_SPECIFIC_POPULATIONS', True),
    '77291-3': ('USE_IN_SPECIFIC_POPULATIONS', True),
    '88829-7': ('USE_IN_SPECIFIC_POPULATIONS', True),
    '88830-5': ('USE_IN_SPECIFIC_POPULATIONS', True),
    '88828-9': ('USE_IN_SPECIFIC_POPULATIONS', True),
    '34088-5': ('OVERDOSAGE', True),
    '34089-3': ('DESCRIPTION', True),
    '34090-1': ('CLINICAL_PHARMACOLOGY', True),
    '43679-0': ('CLINICAL_PHARMACOLOGY', True),
    '43681-6': ('CLINICAL_PHARMACOLOGY', True),
    '43682-4': ('CLINICAL_PHARMACOLOGY', True),
    '49489-8': ('CLINICAL_PHARMACOLOGY', True),
    '66106-6': ('CLINICAL_PHARMACOLOGY', True),
    '43680-8': ('NONCLINICAL_TOXICOLOGY', True),
    '34083-6': ('NONCLINICAL_TOXICOLOGY', True),
    '34091-9': ('NONCLINICAL_TOXICOLOGY', True),
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

# Subsection to parent mapping
SUBSECTION_PARENTS = {
    'Clinical Trials Experience': 'ADVERSE_REACTIONS',
    'Clinical Trials': 'ADVERSE_REACTIONS',
    'Postmarketing Experience': 'ADVERSE_REACTIONS',
    'Pregnancy': 'USE_IN_SPECIFIC_POPULATIONS',
    'Nursing Mothers': 'USE_IN_SPECIFIC_POPULATIONS',
    'Pediatric Use': 'USE_IN_SPECIFIC_POPULATIONS',
    'Geriatric Use': 'USE_IN_SPECIFIC_POPULATIONS',
    'Hepatic Impairment': 'USE_IN_SPECIFIC_POPULATIONS',
    'Renal Impairment': 'USE_IN_SPECIFIC_POPULATIONS',
    'General': 'WARNINGS_AND_PRECAUTIONS',
    'Laboratory Tests': 'WARNINGS_AND_PRECAUTIONS',
    'Carcinogenesis and Mutagenesis and Impairment of Fertility': 'WARNINGS_AND_PRECAUTIONS',
}

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
    """Extract all sections from SPL document with proper hierarchy handling."""
    sections = []
    parent_sections = {}  # section_id -> section_data
    seen_section_ids = set()
    
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
        
        # Only process recognized sections
        if section_type == 'OTHER':
            continue
        
        seen_section_ids.add(section_id)
        
        # Extract content (This now calls TextWasher internally)
        content = extract_section_content(section)
        
        parent_sections[section_id] = {
            'type': section_type,
            'title': title,
            'content': content,
            'loinc_code': loinc_code,
        }
    
    # Second pass: Aggregate subsection content into parents
    for section in all_xml_sections:
        id_elem = section.find('ns0:id', SPL_NS)
        title_elem = section.find('ns0:title', SPL_NS)
        
        if id_elem is None:
            continue
        
        section_id = id_elem.get('root', '')
        
        # Skip if already a parent
        if section_id in parent_sections:
            continue
        
        title = clean_text(extract_text(title_elem)) if title_elem is not None else ''
        
        # Check if this is a numbered subsection (e.g., "5.1 Pregnancy")
        subsection_match = re.match(r'^(\d+)\.(\d+)\s+', title)
        parent_type = SUBSECTION_PARENTS.get(title)
        
        if subsection_match or parent_type:
            content = extract_section_content(section)
            
            if subsection_match:
                parent_num = subsection_match.group(1)
                # Find parent by number prefix
                for pid, pdata in parent_sections.items():
                    if re.match(rf'^{re.escape(parent_num)}\b', pdata['title']):
                        parent_sections[pid]['content'] += f"\n\n--- {title.strip()} ---\n{content}"
                        break
            elif parent_type:
                # Find parent by type
                for pid, pdata in parent_sections.items():
                    if pdata['type'] == parent_type:
                        parent_sections[pid]['content'] += f"\n\n--- {title.strip()} ---\n{content}"
                        break
    
    # Build final sections list
    for section_id, sec_data in parent_sections.items():
        sections.append({
            'section_id': generate_uuid(f"{doc_id}_{section_id}"),
            'section_unique_id': generate_uuid(f"{doc_id}_section_{section_id}"),
            'section_type': sec_data['type'],
            'title': sec_data['title'],
            'content': sec_data['content'],
            'loinc_code': sec_data['loinc_code'],
        })
    
    return sections


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
