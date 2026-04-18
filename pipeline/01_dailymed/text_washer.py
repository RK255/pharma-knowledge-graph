#!/usr/bin/env python3
"""
Text Washer for SPL XML Content
Provides functions to extract and clean text from XML elements while
preserving structure (tables, lists, paragraphs) and normalizing formatting.
"""

import re
import xml.etree.ElementTree as ET
from typing import List, Optional

# SPL Namespace
SPL_NS = {'ns0': 'urn:hl7-org:v3'}


class TextWasher:
    """
    Extracts and formats text from SPL XML elements.
    
    Features:
    - Normalizes whitespace and newlines.
    - Preserves paragraph structure.
    - Cleans up common XML artifacts and formatting issues.
    """
    
    def __init__(self, max_line_width: int = 120):
        self.max_line_width = max_line_width
    
    def wash_element(self, element: ET.Element) -> str:
        """
        Main entry point: Extract text from an element and return cleaned string.
        """
        if element is None:
            return ""
        
        # Recursively extract all text
        text = self._extract_text_content(element)
        
        # Clean the extracted text
        washed_text = self._clean_text(text)
        
        return washed_text
    
    def _extract_text_content(self, element: ET.Element) -> str:
        """
        Recursively extract all text content from an element.
        """
        parts = []
        
        if element.text:
            parts.append(element.text)
        
        for child in element:
            parts.append(self._extract_text_content(child))
            if child.tail:
                parts.append(child.tail)
        
        return "".join(parts)
    
    def _clean_text(self, text: str) -> str:
        """
        Clean and normalize raw text extracted from XML.
        """
        if not text:
            return ""
        
        # 1. Normalize line endings to \n
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        
        # 2. Remove excessive newlines (more than 2 consecutive)
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        # 3. Normalize whitespace within lines
        lines = text.split('\n')
        cleaned_lines = []
        for line in lines:
            # Remove leading/trailing whitespace
            stripped = line.strip()
            if stripped:
                # Collapse multiple spaces into single spaces
                cleaned_line = re.sub(r'\s+', ' ', stripped)
                cleaned_lines.append(cleaned_line)
        
        # 4. Rejoin paragraphs with double newlines
        final_text = '\n\n'.join(cleaned_lines)
        
        # 5. Fix specific formatting artifacts
        
        # Fix section references like "( 5.1 )" -> "(5.1)"
        final_text = re.sub(r'$$\s*(\d+(?:\.\d+)?)\s*$$', r'(\1)', final_text)
        
        # Fix comma spacing in lists "( 5.1 ,  5.2 )" -> "(5.1, 5.2)"
        final_text = re.sub(r',\s+', ', ', final_text)
        
        # Remove trailing whitespace
        final_text = final_text.strip()
        
        return final_text


def wash_section_text(element: ET.Element, max_line_width: int = 120) -> str:
    """
    Convenience function to wash text from a section element.
    """
    washer = TextWasher(max_line_width=max_line_width)
    return washer.wash_element(element)


if __name__ == '__main__':
    # Test with a sample file if run directly
    import sys
    if len(sys.argv) > 1:
        xml_file = sys.argv[1]
        tree = ET.parse(xml_file)
        root = tree.getroot()
        
        washer = TextWasher()
        
        # Find first section and wash it
        section = root.find('.//ns0:section', SPL_NS)
        if section is not None:
            text_elem = section.find('ns0:text', SPL_NS)
            if text_elem is not None:
                print("ORIGINAL (first 500 chars):")
                print(text_elem.text[:500] if text_elem.text else "No text")
                print("\n" + "=" * 80 + "\n")
                print("WASHED:")
                print(washer.wash_element(text_elem)[:1000])
    else:
        print("Usage: python text_washer.py <xml_file>")
