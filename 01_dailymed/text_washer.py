#!/usr/bin/env python3
"""
Text Washer for SPL XML Content
Produces semantic HTML from SPL XML elements, preserving structure
(tables, lists, paragraphs, inline formatting) instead of flattening to text.

SPL XML namespace: urn:hl7-org:v3 (elements use ns0: prefix in find() calls).
"""

import html
import re
import xml.etree.ElementTree as ET
from typing import List, Optional

# SPL Namespace
SPL_NS = {'ns0': 'urn:hl7-org:v3'}


def _local_tag(element: ET.Element) -> str:
    """Return the local name of an element tag (strip namespace)."""
    tag = element.tag
    if '}' in tag:
        return tag.split('}', 1)[1]
    return tag


class TextWasher:
    """
    Extracts text from SPL XML elements and produces semantic HTML.

    Features:
    - Converts SPL elements to HTML equivalents (tables, lists, paragraphs, etc.).
    - Preserves inline formatting: bold, italic, underline, subscript, superscript.
    - Escapes all text content with html.escape().
    - Light text cleaning: whitespace normalization, reference formatting fixes.
    """

    def __init__(self, max_line_width: int = 120):
        self.max_line_width = max_line_width

    def wash_element(self, element: ET.Element) -> str:
        """
        Main entry point: Extract semantic HTML from an element and return cleaned HTML string.
        """
        if element is None:
            return ""

        # Build semantic HTML from the element tree
        html_output = self._extract_text_content(element)

        return html_output.strip()

    def _extract_text_content(self, element: ET.Element) -> str:
        """
        Walk the SPL XML tree and produce semantic HTML.
        Processes the element's text, children, and tails.
        """
        parts = []

        # Handle the element's own text (direct text before any children)
        if element.text:
            parts.append(self._process_text(element.text))

        # Process each child element
        for child in element:
            parts.append(self._process_element(child))
            # Handle tail text (text after a child element, within the parent)
            if child.tail:
                parts.append(self._process_text(child.tail))

        return "".join(parts)

    def _process_element(self, element: ET.Element) -> str:
        """
        Process a single SPL element and return its HTML representation.
        Handles the SPL -> HTML mappings defined in the task spec.
        """
        tag = _local_tag(element)
        handler = self._ELEMENT_HANDLERS.get(tag)

        if handler:
            return handler(self, element)

        # Unknown element: process children recursively (don't crash)
        return self._process_children(element)

    def _process_children(self, element: ET.Element) -> str:
        """Process the children and text of an element, returning concatenated HTML."""
        parts = []

        if element.text:
            parts.append(self._process_text(element.text))

        for child in element:
            parts.append(self._process_element(child))
            if child.tail:
                parts.append(self._process_text(child.tail))

        return "".join(parts)

    # -------------------------------------------------------------------------
    # Element-specific handlers
    # -------------------------------------------------------------------------

    def _handle_paragraph(self, element: ET.Element) -> str:
        """<ns0:paragraph> -> <p>...</p>"""
        inner = self._process_children(element)
        inner = inner.strip()
        if not inner:
            return ""
        return f"<p>{inner}</p>"

    def _handle_table(self, element: ET.Element) -> str:
        """<ns0:table> -> <table class="spl-table">...</table>"""
        parts = []
        has_thead = False
        has_tbody = False
        has_tfoot = False
        direct_rows = []

        for child in element:
            tag = _local_tag(child)

            if tag == 'thead':
                has_thead = True
                parts.append(self._handle_table_section(child, 'thead'))
            elif tag == 'tbody':
                has_tbody = True
                parts.append(self._handle_table_section(child, 'tbody'))
            elif tag == 'tfoot':
                has_tfoot = True
                parts.append(self._handle_table_section(child, 'tfoot'))
            elif tag == 'caption':
                # Caption inside table
                caption_html = self._process_children(child).strip()
                if caption_html:
                    parts.append(f"<caption>{caption_html}</caption>")
            elif tag == 'tr':
                # Direct rows (no thead/tbody/tfoot wrapper)
                direct_rows.append(child)
            # Skip <col> elements - they're layout hints, not content

        # If there were direct <tr> rows (no thead/tbody wrapper), process them
        if direct_rows and not has_tbody and not has_thead:
            tbody_inner = []
            for tr in direct_rows:
                row_html = self._handle_table_row(tr, is_header=False)
                if row_html:
                    tbody_inner.append(row_html)
            if tbody_inner:
                parts.append("<tbody>" + "".join(tbody_inner) + "</tbody>")

        inner = "".join(parts)
        if not inner.strip():
            return ""
        return f'<table class="spl-table">{inner}</table>'

    def _handle_table_section(self, element: ET.Element, section_tag: str) -> str:
        """Handle <ns0:thead>, <ns0:tbody>, <ns0:tfoot>."""
        rows = []
        is_header = (section_tag == 'thead')

        for child in element:
            if _local_tag(child) == 'tr':
                row_html = self._handle_table_row(child, is_header=is_header)
                if row_html:
                    rows.append(row_html)

        if not rows:
            return ""
        return f"<{section_tag}>" + "".join(rows) + f"</{section_tag}>"

    def _handle_table_row(self, element: ET.Element, is_header: bool) -> str:
        """Handle <ns0:tr> - process cells."""
        cells = []
        for child in element:
            tag = _local_tag(child)
            if tag == 'th':
                cells.append(self._handle_table_cell(child, 'th'))
            elif tag == 'td':
                cells.append(self._handle_table_cell(child, 'td'))
            # Skip unknown children

        if not cells:
            return ""
        return "<tr>" + "".join(cells) + "</tr>"

    def _handle_table_cell(self, element: ET.Element, cell_tag: str) -> str:
        """Handle <ns0:th> or <ns0:td>."""
        inner = self._process_children(element)
        inner = inner.strip()
        if not inner:
            return f"<{cell_tag}></{cell_tag}>"
        return f"<{cell_tag}>{inner}</{cell_tag}>"

    def _handle_list(self, element: ET.Element) -> str:
        """<ns0:list> -> <ul> or <ol> based on listType attribute."""
        list_type = element.get('listType', '')
        list_tag = 'ol' if list_type.lower() == 'ordered' else 'ul'

        items = []
        for child in element:
            if _local_tag(child) == 'item':
                item_html = self._handle_list_item(child)
                if item_html:
                    items.append(item_html)

        if not items:
            return ""
        return f"<{list_tag}>" + "".join(items) + f"</{list_tag}>"

    def _handle_list_item(self, element: ET.Element) -> str:
        """<ns0:item> -> <li>...</li>"""
        inner = self._process_children(element)
        inner = inner.strip()
        if not inner:
            return ""
        return f"<li>{inner}</li>"

    def _handle_content(self, element: ET.Element) -> str:
        """<ns0:content> -> inline formatting based on styleCode attribute."""
        inner = self._process_children(element)

        style = element.get('styleCode', '')
        style_lower = style.lower() if style else ''

        if style_lower in ('bold',):
            return f"<strong>{inner}</strong>"
        elif style_lower in ('ital', 'italic', 'italics'):
            return f"<em>{inner}</em>"
        elif style_lower in ('underline',):
            return f"<u>{inner}</u>"
        else:
            # No styleCode or unknown: just return children inline
            return inner

    def _handle_sup(self, element: ET.Element) -> str:
        """<ns0:sup> -> <sup>...</sup>"""
        inner = self._process_children(element)
        if not inner.strip():
            return ""
        return f"<sup>{inner}</sup>"

    def _handle_sub(self, element: ET.Element) -> str:
        """<ns0:sub> -> <sub>...</sub>"""
        inner = self._process_children(element)
        if not inner.strip():
            return ""
        return f"<sub>{inner}</sub>"

    def _handle_br(self, element: ET.Element) -> str:
        """<ns0:br> -> <br>"""
        return "<br>"

    def _handle_link_html(self, element: ET.Element) -> str:
        """<ns0:linkHtml> -> inline text or <a href="...">...</a>"""
        # Extract text content
        text = self._process_children(element)
        text = text.strip()

        if not text:
            return ""

        href = element.get('href', '')
        if href:
            # Escape the href for use in an attribute
            escaped_href = html.escape(href, quote=True)
            return f'<a href="{escaped_href}">{text}</a>'

        # No href: render as plain text
        return text

    def _handle_render_multi_media(self, element: ET.Element) -> str:
        """<ns0:renderMultiMedia> -> [Image: {referencedObject}]"""
        ref = element.get('referencedObject', '')
        if not ref:
            return ""
        return f"[Image: {ref}]"

    def _handle_caption(self, element: ET.Element) -> str:
        """<ns0:caption> -> <caption> or <figcaption> depending on context."""
        inner = self._process_children(element).strip()
        if not inner:
            return ""
        # We don't have parent context here easily in ElementTree,
        # so we check if we're likely inside a table by looking at siblings.
        # Default to <figcaption> for standalone captions,
        # but if the parent is a <table>, the table handler already
        # processes caption as <caption>. So when _process_element
        # encounters caption directly, it's likely standalone.
        return f"<figcaption>{inner}</figcaption>"

    def _handle_title(self, element: ET.Element) -> str:
        """<ns0:title> inside a text element -> <h5>...</h5>"""
        inner = self._process_children(element).strip()
        if not inner:
            return ""
        return f"<h5>{inner}</h5>"

    # -------------------------------------------------------------------------
    # Text processing
    # -------------------------------------------------------------------------

    def _process_text(self, text: str) -> str:
        """
        Process a text node: escape HTML and apply light cleaning.
        Does NOT collapse whitespace across element boundaries.
        """
        if not text:
            return ""

        # Apply light cleaning to the raw text
        cleaned = self._clean_text_node(text)

        # Escape HTML special characters
        return html.escape(cleaned, quote=False)

    def _clean_text_node(self, text: str) -> str:
        """
        Light cleaning for text nodes (not full HTML).
        - Collapse multiple spaces into single space
        - Fix reference formatting like "( 5.1 )" -> "(5.1)"
        - Strip leading/trailing whitespace (but preserve internal spacing)
        """
        if not text:
            return ""

        # Collapse multiple spaces/tabs into single space (but keep newlines)
        text = re.sub(r'[ \t]+', ' ', text)

        # Fix section references like "( 5.1 )" -> "(5.1)"
        text = re.sub(r'\(\s*(\d+(?:\.\d+)?)\s*\)', r'(\1)', text)

        # Fix comma spacing in references "( 5.1 ,  5.2 )" -> "(5.1, 5.2)"
        text = re.sub(r',\s+', ', ', text)

        return text

    def _clean_text(self, text: str) -> str:
        """
        Clean and normalize raw text (legacy method, kept for compatibility).
        Applied only to text nodes now, not to HTML output.
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
        final_text = re.sub(r'\(\s*(\d+(?:\.\d+)?)\s*\)', r'(\1)', final_text)

        # Fix comma spacing in lists "( 5.1 ,  5.2 )" -> "(5.1, 5.2)"
        final_text = re.sub(r',\s+', ', ', final_text)

        # Remove trailing whitespace
        final_text = final_text.strip()

        return final_text

    # -------------------------------------------------------------------------
    # Handler dispatch table (built after method definitions)
    # -------------------------------------------------------------------------

    # Will be populated below
    _ELEMENT_HANDLERS = {}


# Build the handler dispatch table
TextWasher._ELEMENT_HANDLERS = {
    'paragraph': TextWasher._handle_paragraph,
    'table': TextWasher._handle_table,
    'list': TextWasher._handle_list,
    'content': TextWasher._handle_content,
    'sup': TextWasher._handle_sup,
    'sub': TextWasher._handle_sub,
    'br': TextWasher._handle_br,
    'linkHtml': TextWasher._handle_link_html,
    'renderMultiMedia': TextWasher._handle_render_multi_media,
    'caption': TextWasher._handle_caption,
    'title': TextWasher._handle_title,
}


def wash_section_text(element: ET.Element, max_line_width: int = 120) -> str:
    """
    Convenience function to wash text from a section element.
    Returns semantic HTML.
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
                print("WASHED HTML OUTPUT:")
                print("=" * 80)
                output = washer.wash_element(text_elem)
                print(output[:3000])
                if len(output) > 3000:
                    print(f"\n... [{len(output)} total chars]")
            else:
                print("No <text> element found in first section")
        else:
            print("No <section> element found")

        # Also try washing all text elements and show stats
        print("\n" + "=" * 80)
        print("ALL SECTIONS SUMMARY:")
        print("=" * 80)
        sections = root.findall('.//ns0:section', SPL_NS)
        for i, sec in enumerate(sections):
            title = sec.find('ns0:title', SPL_NS)
            title_text = ""
            if title is not None and title.text:
                title_text = title.text.strip()[:50]
            text_elem = sec.find('ns0:text', SPL_NS)
            if text_elem is not None:
                html_out = washer.wash_element(text_elem)
                tag_counts = {}
                for tag_name in ['<p>', '<table', '<ul>', '<ol>', '<li>', '<strong>', '<em>', '<sup>', '<sub>', '<br>', '<a ', '<figcaption>', '<h5>']:
                    count = html_out.count(tag_name)
                    if count:
                        tag_counts[tag_name] = count
                print(f"  Section {i}: '{title_text}' -> {len(html_out)} chars, tags: {tag_counts}")
    else:
        print("Usage: python text_washer.py <xml_file>")
