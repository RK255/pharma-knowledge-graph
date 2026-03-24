#!/usr/bin/env python3
"""
Text Washer for SPL XML Content
Preserves structure from tables, lists, and paragraphs while cleaning whitespace.

This module provides functions to extract and format text from SPL XML elements
while preserving the semantic structure (tables, lists, paragraphs).
"""

import re
import xml.etree.ElementTree as ET
from typing import List, Optional, Tuple
from collections import defaultdict

SPL_NS = {'ns0': 'urn:hl7-org:v3'}


class TextWasher:
    """
    Extracts and formats text from SPL XML elements while preserving structure.
    
    Features:
    - Tables formatted as readable ASCII tables
    - Lists rendered with bullets/numbers
    - Paragraphs preserved with proper spacing
    - Bold/italic markers preserved
    - Cross-references formatted
    """
    
    def __init__(self, preserve_formatting: bool = True, max_table_width: int = 120):
        self.preserve_formatting = preserve_formatting
        self.max_table_width = max_table_width
    
    def wash_element(self, element: ET.Element) -> str:
        """
        Main entry point: extract and format text from any SPL element.
        """
        if element is None:
            return ""
        
        # Get all content parts
        parts = self._process_element(element)
        text = "\n\n".join(parts)
        
        # Final cleanup
        text = self._final_cleanup(text)
        return text
    
    def _process_element(self, element: ET.Element) -> List[str]:
        """
        Recursively process an element and its children.
        Returns a list of text blocks.
        """
        parts = []
        
        # Handle tables specially
        if self._is_table(element):
            table_text = self._format_table(element)
            if table_text.strip():
                parts.append(table_text)
            return parts
        
        # Handle lists
        if self._is_list(element):
            list_text = self._format_list(element)
            if list_text.strip():
                parts.append(list_text)
            return parts
        
        # Handle paragraphs
        if self._is_paragraph(element):
            para_text = self._extract_paragraph(element)
            if para_text.strip():
                parts.append(para_text)
            return parts
        
        # Handle other elements - recurse into children
        child_parts = []
        if element.text:
            child_parts.append(element.text.strip())
        
        for child in element:
            child_result = self._process_element(child)
            child_parts.extend(child_result)
            
            if child.tail:
                tail = child.tail.strip()
                if tail:
                    child_parts.append(tail)
        
        parts.extend(child_parts)
        return parts
    
    def _is_table(self, element: ET.Element) -> bool:
        """Check if element is a table."""
        return element.tag.endswith('table')
    
    def _is_list(self, element: ET.Element) -> bool:
        """Check if element is a list."""
        return element.tag.endswith('list')
    
    def _is_paragraph(self, element: ET.Element) -> bool:
        """Check if element is a paragraph."""
        return element.tag.endswith('paragraph')
    
    def _is_item(self, element: ET.Element) -> bool:
        """Check if element is a list item."""
        return element.tag.endswith('item')
    
    def _extract_paragraph(self, element: ET.Element) -> str:
        """Extract text from a paragraph, preserving inline formatting."""
        text_parts = []
        
        if element.text:
            text_parts.append(element.text)
        
        for child in element:
            child_text = self._extract_inline_element(child)
            if child_text:
                text_parts.append(child_text)
            
            if child.tail:
                text_parts.append(child.tail)
        
        text = ' '.join(text_parts)
        text = self._clean_inline_text(text)
        return text
    
    def _extract_inline_element(self, element: ET.Element) -> str:
        """Extract text from inline elements (content, linkHtml, etc.)."""
        tag = element.tag.split('}')[-1] if '}' in element.tag else element.tag
        
        text_parts = []
        
        if element.text:
            text_parts.append(element.text)
        
        for child in element:
            child_text = self._extract_inline_element(child)
            if child_text:
                text_parts.append(child_text)
            if child.tail:
                text_parts.append(child.tail)
        
        content = ' '.join(text_parts)
        
        # Handle bold/italic markers
        style = element.get('styleCode', '')
        if self.preserve_formatting:
            if 'bold' in style.lower() and content.strip():
                content = f"**{content.strip()}**"
            elif 'italic' in style.lower() and content.strip():
                content = f"*{content.strip()}*"
        
        # Handle links - just extract text, ignore href for now
        if tag == 'linkHtml':
            # Internal links are just references, return text only
            pass
        
        return content
    
    def _format_table(self, element: ET.Element) -> str:
        """
        Format a table as readable ASCII text.
        """
        # Get caption
        caption = ""
        caption_elem = element.find('ns0:caption', SPL_NS)
        if caption_elem is not None:
            caption = self._extract_text_content(caption_elem).strip()
        
        # Extract table data
        rows = []
        
        # Process thead
        thead = element.find('ns0:thead', SPL_NS)
        if thead is not None:
            header_rows = self._extract_table_rows(thead)
            rows.extend(header_rows)
        
        # Process tbody
        tbody = element.find('ns0:tbody', SPL_NS)
        if tbody is not None:
            body_rows = self._extract_table_rows(tbody)
            rows.extend(body_rows)
        
        # Process tfoot
        tfoot = element.find('ns0:tfoot', SPL_NS)
        footnotes = []
        if tfoot is not None:
            foot_rows = self._extract_table_rows(tfoot)
            for row in foot_rows:
                for cell in row:
                    if cell.strip():
                        footnotes.append(cell.strip())
        
        if not rows:
            return caption if caption else ""
        
        # Calculate column widths
        num_cols = max(len(row) for row in rows)
        col_widths = [0] * num_cols
        
        for row in rows:
            for i, cell in enumerate(row):
                # Wrap text if needed
                lines = self._wrap_text(cell, 30)
                max_line_len = max(len(line) for line in lines) if lines else 0
                col_widths[i] = max(col_widths[i], max_line_len, 10)
        
        # Limit total width
        total_width = sum(col_widths) + (num_cols - 1) * 3 + 4  # borders and separators
        if total_width > self.max_table_width:
            # Scale down column widths proportionally
            scale = (self.max_table_width - (num_cols - 1) * 3 - 4) / sum(col_widths)
            col_widths = [max(8, int(w * scale)) for w in col_widths]
        
        # Build the table
        lines = []
        
        if caption:
            lines.append(caption)
            lines.append("")
        
        # Header separator
        separator = "+" + "+".join("-" * (w + 2) for w in col_widths) + "+"
        lines.append(separator)
        
        # Rows
        for row_idx, row in enumerate(rows):
            # Pad row to num_cols
            padded_row = row + [''] * (num_cols - len(row))
            
            # Wrap cells and build row lines
            wrapped_cells = []
            max_lines = 1
            for i, cell in enumerate(padded_row):
                wrapped = self._wrap_text(cell, col_widths[i])
                wrapped_cells.append(wrapped)
                max_lines = max(max_lines, len(wrapped))
            
            # Build each line of the wrapped row
            for line_idx in range(max_lines):
                row_parts = []
                for i in range(num_cols):
                    if line_idx < len(wrapped_cells[i]):
                        text = wrapped_cells[i][line_idx]
                    else:
                        text = ""
                    row_parts.append(f" {text:<{col_widths[i]}} ")
                lines.append("|" + "|".join(row_parts) + "|")
            
            # Add separator after header
            if row_idx == 0:
                lines.append(separator)
        
        lines.append(separator)
        
        # Add footnotes
        if footnotes:
            lines.append("")
            for fn in footnotes:
                lines.append(f"  {fn}")
        
        return "\n".join(lines)
    
    def _extract_table_rows(self, container: ET.Element) -> List[List[str]]:
        """Extract rows from thead, tbody, or tfoot."""
        rows = []
        for tr in container.findall('ns0:tr', SPL_NS):
            cells = []
            for td in tr.findall('ns0:td', SPL_NS):
                cell_text = self._extract_text_content(td).strip()
                cells.append(cell_text)
            if cells and any(c.strip() for c in cells):
                rows.append(cells)
        return rows
    
    def _format_list(self, element: ET.Element, indent: int = 0) -> str:
        """
        Format a list with bullets or numbers.
        Handles nested lists recursively.
        """
        list_type = element.get('listType', 'unordered')
        items = []
        
        for idx, item in enumerate(element.findall('ns0:item', SPL_NS), 1):
            # Extract the item text, but handle nested lists separately
            item_text = self._extract_list_item_text(item, indent, list_type, idx)
            if item_text.strip():
                items.append(item_text)
        
        return "\n".join(items)
    
    def _extract_list_item_text(self, item: ET.Element, indent: int, list_type: str, idx: int) -> str:
        """
        Extract text from a list item, handling nested lists.
        """
        # Get direct text content (not from nested lists)
        text_parts = []
        
        if item.text:
            text_parts.append(item.text)
        
        for child in item:
            tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
            
            if tag == 'list':
                # Handle nested list
                nested_list = self._format_list(child, indent + 2)
                text_parts.append('\n' + nested_list)
            else:
                # Extract inline content
                child_text = self._extract_inline_element(child)
                if child_text:
                    text_parts.append(child_text)
            
            if child.tail:
                text_parts.append(child.tail)
        
        # Combine and clean
        content = ' '.join(text_parts)
        content = self._clean_inline_text(content)
        
        # Remove any existing bullet/number prefixes that might be in the source
        content = re.sub(r'^[\s]*[•\-\*]\s*', '', content)
        content = re.sub(r'^[\s]*\d+\.\s*', '', content)
        
        # Add our prefix
        prefix = "  " * indent
        if list_type == 'ordered':
            prefix += f"{idx}. "
        else:
            prefix += "• "
        
        # Handle multi-line content (from nested lists)
        if '\n' in content:
            lines = content.split('\n')
            first_line = prefix + lines[0]
            other_lines = ['  ' * (indent + 1) + line for line in lines[1:]]
            return '\n'.join([first_line] + other_lines)
        else:
            return prefix + content
    
    def _extract_text_content(self, element: ET.Element) -> str:
        """Extract all text content from an element recursively."""
        parts = []
        
        if element.text:
            parts.append(element.text)
        
        for child in element:
            parts.append(self._extract_text_content(child))
            if child.tail:
                parts.append(child.tail)
        
        return ' '.join(parts)
    
    def _wrap_text(self, text: str, max_width: int) -> List[str]:
        """Wrap text to a maximum width, returning list of lines."""
        if not text:
            return [""]
        
        words = text.split()
        lines = []
        current_line = []
        current_length = 0
        
        for word in words:
            if current_length + len(word) + 1 <= max_width:
                current_line.append(word)
                current_length += len(word) + 1
            else:
                if current_line:
                    lines.append(' '.join(current_line))
                current_line = [word]
                current_length = len(word)
        
        if current_line:
            lines.append(' '.join(current_line))
        
        return lines if lines else [""]
    
    def _clean_inline_text(self, text: str) -> str:
        """Clean up inline text."""
        # Normalize whitespace
        text = re.sub(r'\s+', ' ', text)
        # Remove leading/trailing whitespace
        text = text.strip()
        # Clean up section references like "( 5.1 )" -> "(5.1)"
        text = re.sub(r'$$\s*(\d+(?:\.\d+)?)\s*$$', r'(\1)', text)
        # Clean up multiple references "( 5.1 ,  5.2 )" -> "(5.1, 5.2)"
        text = re.sub(r',\s+', ', ', text)
        return text
    
    def _final_cleanup(self, text: str) -> str:
        """Final cleanup of the entire text."""
        # Normalize line endings
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        
        # Remove more than 2 consecutive newlines
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        # Remove trailing whitespace on lines
        text = re.sub(r'[ \t]+\n', '\n', text)
        
        # Remove leading/trailing whitespace
        text = text.strip()
        
        return text


def wash_section_text(element: ET.Element, preserve_formatting: bool = True) -> str:
    """
    Convenience function to wash text from a section element.
    
    Args:
        element: The XML element to extract text from
        preserve_formatting: Whether to preserve bold/italic markers
    
    Returns:
        Cleaned and formatted text
    """
    washer = TextWasher(preserve_formatting=preserve_formatting)
    return washer.wash_element(element)


# Standalone function for washing already-extracted text
def wash_raw_text(text: str, preserve_paragraphs: bool = True) -> str:
    """
    Wash already-extracted text to improve formatting.
    This is a fallback for text that was extracted with the old method.
    
    Args:
        text: Raw text to clean
        preserve_paragraphs: Try to detect and preserve paragraph boundaries
    
    Returns:
        Cleaned text
    """
    if not text:
        return ""
    
    # Normalize line endings
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    
    if preserve_paragraphs:
        # Try to detect paragraph boundaries
        lines = text.split('\n')
        paragraphs = []
        current_para = []
        
        for line in lines:
            line = line.strip()
            if not line:
                if current_para:
                    paragraphs.append(' '.join(current_para))
                    current_para = []
                continue
            
            current_para.append(line)
        
        if current_para:
            paragraphs.append(' '.join(current_para))
        
        text = '\n\n'.join(paragraphs)
    
    # Final cleanup
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = text.strip()
    
    return text


if __name__ == '__main__':
    # Test with a sample file
    import sys
    
    if len(sys.argv) > 1:
        xml_file = sys.argv[1]
        tree = ET.parse(xml_file)
        root = tree.getroot()
        
        washer = TextWasher()
        
        # Find sections with content
        count = 0
        for section in root.findall('.//ns0:section', SPL_NS):
            title_elem = section.find('ns0:title', SPL_NS)
            text_elem = section.find('ns0:text', SPL_NS)
            
            if title_elem is not None and text_elem is not None:
                title = washer._extract_text_content(title_elem).strip()
                print(f"\n{'='*60}")
                print(f"SECTION: {title}")
                print('='*60)
                
                washed = washer.wash_element(text_elem)
                print(washed[:1500])
                print("\n...")
                count += 1
                if count >= 3:
                    break
    else:
        print("Usage: python text_washer.py <xml_file>")
