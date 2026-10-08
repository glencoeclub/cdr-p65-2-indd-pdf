#!/usr/bin/env python3
"""
PDF generator for PageMaker P65 files.
Creates a PDF with extracted text content from P65 files.
"""

import os
import logging
from typing import List
from reportlab.lib.pagesizes import letter, legal
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY

TABLOID = (792, 1224)
HALFLETTER = (396, 612)

PAGE_SIZE_MAP = {
    (612, 792): letter,
    (612, 1008): legal,
    (792, 1224): TABLOID,
    (396, 612): HALFLETTER,
}

logger = logging.getLogger(__name__)


class P65PDFGenerator:
    """Generate PDF from parsed P65 content."""
    
    FONT_MAPPING = {
        # Serif fonts
        'Times New Roman': 'Times-Roman',
        'Times New Roman Bold': 'Times-Bold',
        'Times New Roman Italic': 'Times-Italic',
        'Times New Roman Bold Italic': 'Times-BoldItalic',
        'Times': 'Times-Roman',
        'Times Bold': 'Times-Bold',
        'Times Italic': 'Times-Italic',
        'Palatino': 'Times-Roman',
        'Palatino Linotype': 'Times-Roman',
        'Bookman': 'Times-Roman',
        'Garamond': 'Times-Roman',
        'New York': 'Times-Roman',
        'Georgia': 'Times-Roman',
        
        # Sans-serif fonts
        'Helvetica': 'Helvetica',
        'Helvetica Bold': 'Helvetica-Bold',
        'Helvetica Oblique': 'Helvetica-Oblique',
        'Helvetica Bold Oblique': 'Helvetica-BoldOblique',
        'Arial': 'Helvetica',
        'Arial Bold': 'Helvetica-Bold',
        'Arial Italic': 'Helvetica-Oblique',
        'Arial Bold Italic': 'Helvetica-BoldOblique',
        'Verdana': 'Helvetica',
        'Trebuchet MS': 'Helvetica',
        'Tahoma': 'Helvetica',
        'Geneva': 'Helvetica',
        'Chicago': 'Helvetica',
        'Optima': 'Helvetica',
        'Avant Garde': 'Helvetica',
        'AvantGarde': 'Helvetica',
        'Futura': 'Helvetica',
        'Gill Sans': 'Helvetica',
        'Century Gothic': 'Helvetica',
        'Franklin Gothic': 'Helvetica',
        'Lucida Grande': 'Helvetica',
        'Lucida Sans': 'Helvetica',
        
        # Monospace fonts
        'Courier': 'Courier',
        'Courier New': 'Courier',
        'Courier New Bold': 'Courier-Bold',
        'Courier New Italic': 'Courier-Oblique',
        'Courier New Bold Italic': 'Courier-BoldOblique',
        'Monaco': 'Courier',
        'Consolas': 'Courier',
        'Lucida Console': 'Courier',
        'Andale Mono': 'Courier',
        
        # Script/display fonts (fall back to Helvetica)
        'Curlz MT': 'Helvetica',
        'Zapf Chancery': 'Helvetica',
        'Zapfino': 'Helvetica',
        'Brush Script': 'Helvetica',
        'Comic Sans MS': 'Helvetica',
        'Papyrus': 'Helvetica',
        'Impact': 'Helvetica',
        
        # Symbol fonts
        'Symbol': 'Symbol',
        'Wingdings': 'ZapfDingbats',
        'Webdings': 'ZapfDingbats',
        'Zapf Dingbats': 'ZapfDingbats',
    }
    
    def __init__(self, parser):
        self.parser = parser
        self.styles = getSampleStyleSheet()
        self._create_custom_styles()
        
    def _create_custom_styles(self):
        """Create custom paragraph styles."""
        # Title style
        self.styles.add(ParagraphStyle(
            name='P65Title',
            parent=self.styles['Heading1'],
            fontSize=24,
            alignment=TA_CENTER,
            spaceAfter=12,
        ))
        
        # Heading style
        self.styles.add(ParagraphStyle(
            name='P65Heading',
            parent=self.styles['Heading2'],
            fontSize=14,
            alignment=TA_LEFT,
            spaceAfter=6,
            spaceBefore=12,
        ))
        
        # Body text style
        self.styles.add(ParagraphStyle(
            name='P65Body',
            parent=self.styles['Normal'],
            fontSize=10,
            alignment=TA_LEFT,
            spaceAfter=6,
            lineSpacing=1.2,
        ))
        
    def _classify_text(self, text: str) -> str:
        """Classify text to determine style using generic heuristics."""
        text_stripped = text.strip()
        text_lower = text_stripped.lower()

        # Heading detection first: short text ending with colon is almost always a heading
        if text_stripped.endswith(':') and len(text_stripped) < 80:
            return 'P65Heading'

        # Title detection: short text, title case or all caps, no ending punctuation
        if len(text_stripped) < 60 and len(text_stripped) > 3:
            alpha_count = sum(1 for c in text_stripped if c.isalpha())
            if alpha_count > len(text_stripped) * 0.5:
                # Title case or ALL CAPS (not just lowercase) suggests a title
                is_title_case = text_stripped.istitle()
                is_all_caps = text_stripped.isupper() and len(text_stripped.split()) <= 6
                if is_title_case or is_all_caps:
                    # But not if it's just a simple lowercase phrase that happens to be short
                    if '.' not in text_stripped and ',' not in text_stripped:
                        if len(text_stripped.split()) <= 8:
                            return 'P65Title'

        # Heading detection: shorter than body, often a single phrase
        if len(text_stripped) < 80:
            alpha_ratio = sum(1 for c in text_stripped if c.isalpha()) / max(len(text_stripped), 1)
            if alpha_ratio > 0.6:
                word_count = len(text_stripped.split())
                if word_count <= 4 and not any(c in text_stripped for c in '.!?,;'):
                    return 'P65Heading'

        return 'P65Body'
        
    def _map_font(self, font_name: str) -> str:
        """Map PageMaker font to PDF font."""
        return self.FONT_MAPPING.get(font_name, 'Helvetica')

    def _get_page_size(self):
        """Determine page size from parser metadata, fallback to letter."""
        metadata = getattr(self.parser, 'metadata', {})
        width = metadata.get('page_width_pt', 0)
        height = metadata.get('page_height_pt', 0)
        
        if width > 0 and height > 0:
            page_size = PAGE_SIZE_MAP.get((width, height))
            if page_size:
                logger.info(f"Using page size: {width}x{height} points")
                return page_size
            logger.info(f"Using custom page size: {width}x{height} points")
            return (width, height)
        
        logger.info("Using default page size: letter")
        return letter

    def _calculate_margins(self, pagesize):
        """Calculate appropriate margins based on page size."""
        width, height = pagesize
        margin = min(72, min(width, height) / 10)
        return {
            'right': margin,
            'left': margin,
            'top': margin,
            'bottom': margin,
        }
        
    def generate(self, output_path: str) -> bool:
        """Generate PDF from parsed content."""
        try:
            output_dir = os.path.dirname(output_path)
            if output_dir and not os.path.exists(output_dir):
                os.makedirs(output_dir, exist_ok=True)
                logger.info(f"Created output directory: {output_dir}")

            pagesize = self._get_page_size()
            margins = self._calculate_margins(pagesize)

            doc = SimpleDocTemplate(
                output_path,
                pagesize=pagesize,
                rightMargin=margins['right'],
                leftMargin=margins['left'],
                topMargin=margins['top'],
                bottomMargin=margins['bottom'],
            )

            story = []

            # Add title
            title_text = self._extract_title()
            if title_text:
                safe_title = self._escape_xml(title_text)
                story.append(Paragraph(safe_title, self.styles['P65Title']))
                story.append(Spacer(1, 0.25*inch))

            # Add content
            content = self.parser.content_strings

            if not content:
                logger.warning("No content found in P65 file")

            for text in content:
                style_name = self._classify_text(text)

                # Only add if meaningful content
                if len(text.strip()) > 1:
                    try:
                        safe_text = self._escape_xml(text)
                        story.append(Paragraph(safe_text, self.styles[style_name]))
                    except Exception as e:
                        logger.warning(f"Skipping problematic text: {text[:30]}... Error: {e}")
                        continue

            # Build PDF
            doc.build(story)
            logger.info(f"Generated PDF: {output_path}")
            return True

        except PermissionError as e:
            logger.error(f"Permission denied writing to {output_path}: {e}")
            return False
        except OSError as e:
            logger.error(f"OS error writing to {output_path}: {e}")
            return False
        except Exception as e:
            logger.error(f"Error generating PDF: {e}")
            return False
    
    def _escape_xml(self, text: str) -> str:
        """Escape special characters for PDF/HTML."""
        # Replace special characters
        text = text.replace('&', '&amp;')
        text = text.replace('<', '&lt;')
        text = text.replace('>', '&gt;')
        # Keep basic punctuation
        return text
            
    def _extract_title(self) -> str:
        """Extract document title from content."""
        content = self.parser.content_strings
        
        # Look for schedule title
        for text in content[:20]:
            if 'schedule' in text.lower():
                return text
                
        # Return first substantial text
        for text in content[:10]:
            if len(text) > 10 and len(text) < 60:
                return text
                
        return "PageMaker Document"
