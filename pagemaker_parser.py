#!/usr/bin/env python3
"""
PageMaker file parsers for P65 (6.5) and PM5 (5.0) formats.

P65 files are OLE/CFB containers with a /PageMaker stream.
PM5 files are flat binary files with a record-based structure.

Both formats embed ASCII text at varying offsets. This module extracts
content strings using a shared string-scanning approach.
"""

import struct
import re
import logging
from typing import Dict, List, Optional, Any

try:
    import olefile
    OLEFILE_AVAILABLE = True
except ImportError:
    olefile = None
    OLEFILE_AVAILABLE = False

logger = logging.getLogger(__name__)

ENDIANNESS_MARKER_OFFSET = 0x06


class PageMakerBaseParser:
    """Base class for PageMaker file parsers.

    Subclasses must implement _load_data() to return raw bytes.
    """

    def __init__(self, filepath: str):
        self.filepath = filepath
        self.page_maker_data: Optional[bytes] = None
        self.metadata: Dict[str, Any] = {}
        self.fonts: List[str] = []
        self.styles: List[str] = []
        self.colors: List[str] = []
        self.content_strings: List[str] = []

    def parse(self) -> bool:
        try:
            data = self._load_data()
            if not data or len(data) < 128:
                return False

            self.page_maker_data = data
            self._detect_endianness(data)
            self._extract_page_dimensions(data)
            self._extract_strings(data)
            self._analyze_content()
            return True
        except Exception as e:
            logger.error(f"Error parsing {self.filepath}: {e}", exc_info=True)
            return False

    def _load_data(self) -> Optional[bytes]:
        raise NotImplementedError

    def _detect_endianness(self, data: bytes):
        if len(data) < ENDIANNESS_MARKER_OFFSET + 2:
            self.metadata['big_endian'] = True
            return
        endian_marker = struct.unpack('>H', data[ENDIANNESS_MARKER_OFFSET:ENDIANNESS_MARKER_OFFSET + 2])[0]
        self.metadata['big_endian'] = (endian_marker == 0xFF99)
        self.metadata['endian_marker'] = f"0x{endian_marker:04X}"

    def _extract_page_dimensions(self, data: bytes):
        if len(data) < 0x1A:
            return
        for fmt, label in [('>f', 'float'), ('>I', 'int')]:
            try:
                w = struct.unpack(fmt, data[0x12:0x16])[0]
                h = struct.unpack(fmt, data[0x16:0x1A])[0]
                if 36 < w < 10000 and 36 < h < 10000:
                    self.metadata['page_width_pt'] = int(w)
                    self.metadata['page_height_pt'] = int(h)
                    return
            except Exception:
                pass

    def _extract_strings(self, data: bytes):
        if not data:
            return
        font_patterns = [
            b'Times New Roman', b'Helvetica', b'Arial', b'Courier',
            b'Optima', b'Curlz', b'Garamond', b'Bookman', b'Palatino',
            b'Avant Garde', b'Zapf Chancery', b'New York', b'Monaco',
            b'Chicago', b'Geneva', b'Symbol', b'Wingdings',
        ]
        style_patterns = [
            b'Body text', b'Headline', b'Subhead', b'Caption',
            b'Normal', b'Bold', b'Italic', b'Regular',
        ]
        color_patterns = [
            b'Registration', b'Paper', b'Black', b'White',
            b'Red', b'Green', b'Blue', b'Cyan', b'Magenta', b'Yellow',
            b'Process', b'Spot', b'Custom',
        ]
        current_string = []
        for i in range(len(data)):
            byte = data[i]
            if 32 <= byte <= 126:
                current_string.append(chr(byte))
            else:
                if current_string:
                    string = ''.join(current_string)
                    if len(string) >= 3:
                        sb = string.encode('ascii')
                        if any(p in sb for p in font_patterns):
                            if string not in self.fonts:
                                self.fonts.append(string)
                        elif any(p in sb for p in style_patterns):
                            if string not in self.styles:
                                self.styles.append(string)
                        elif any(p in sb for p in color_patterns):
                            if string not in self.colors:
                                self.colors.append(string)
                        elif self._is_content_string(string):
                            self.content_strings.append((i - len(string), string))
                    current_string = []

    def _is_content_string(self, s: str) -> bool:
        score = 0.0
        length = len(s)
        if length < 4:
            return False
        elif length < 8:
            score -= 1.0
        elif length < 12:
            score += 1.0
        elif length < 100:
            score += 3.0
        elif length < 300:
            score += 2.0
        else:
            score -= 1.0

        alpha_count = sum(1 for c in s if c.isalpha())
        alpha_ratio = alpha_count / length if length > 0 else 0
        if alpha_ratio > 0.7:
            score += 3.0
        elif alpha_ratio > 0.4:
            score += 1.0
        elif alpha_ratio > 0.2:
            score -= 1.0
        else:
            score -= 3.0

        word_count = len(s.split())
        if word_count < 2:
            score -= 4.0
        elif word_count < 5:
            score += 1.0
        elif word_count >= 5:
            score += 3.0

        vowel_count = sum(1 for c in s.lower() if c in 'aeiou')
        if vowel_count >= 5:
            score += 2.0
        elif vowel_count >= 2:
            score += 1.0
        else:
            score -= 3.0

        special_chars = sum(1 for c in s if not c.isalnum() and c not in ' .,:;!?-\'"()&/')
        special_ratio = special_chars / length if length > 0 else 0
        if special_ratio > 0.15:
            score -= 3.0

        if '\\' in s or (len(s) >= 2 and s[1] == ':'):
            return False
        if any(ord(c) < 32 or ord(c) > 126 for c in s):
            return False

        if '.' in s and len(s) < 50 and len(s.split('.')[-1]) <= 4:
            parts = s.split('.')
            if len(parts) == 2 and parts[0].isalnum() and parts[1].isalpha():
                return False

        s_upper = s.upper()
        if s_upper.startswith('EF'):
            return False

        metadata_patterns = [
            'PM65', 'RSRC', 'TIFF', 'EPSF', 'PANTONE',
            'MediaType', 'AutoSelect', 'PPD',
            'Adobe', 'PageMaker', 'CorelDRAW', 'pagemaker', 'coreldraw',
            'Acrobat', 'Photoshop', 'Illustrator', 'InDesign',
        ]
        for pattern in metadata_patterns:
            if pattern.upper() in s_upper:
                return False

        s_lower = s.lower()
        software_indicators = [
            'times new roman', 'helvetica', 'arial', 'courier', 'optima',
            'avantgarde', 'zapf', 'chancery', 'symbol', 'wingdings',
            'rgb', 'cmyk', 'paragraph text', 'artistic text', 'graphic',
        ]
        if any(indicator in s_lower for indicator in software_indicators):
            score -= 5.0

        internal_patterns = [
            'lgobloda', 'gobj', 'pageflgs', 'doc stsh', 'infoikey',
            'otltoutl', 'filtfill', 'grp spnd', 'obj spnd',
            'outld', 'outltoutl', 'dDesktop', 'dLayer',
        ]
        for pattern in internal_patterns:
            if pattern.lower() in s_lower:
                return False

        doc_structure = [
            'DISPLAY', 'None', 'False', 'Default', 'Contents',
            'Index', 'Guides', 'Document Master', 'Body-in',
            'METAFILEPICT', 'RIFF',
        ]
        for pattern in doc_structure:
            if s.strip() == pattern:
                return False

        if length > 3:
            unique_chars = len(set(s.lower()))
            if unique_chars < length * 0.3:
                return False

        return score >= 2.0

    def _analyze_content(self):
        self.content_strings.sort(key=lambda x: x[0])
        seen = set()
        cleaned = []
        for pos, text in self.content_strings:
            if text in seen:
                continue
            seen.add(text)
            cleaned.append(text)
        self.content_strings = cleaned

    def get_text_content(self) -> str:
        return '\n'.join(self.content_strings)

    def get_info(self) -> Dict:
        return {
            'version': self.metadata.get('version', 'unknown'),
            'endian': 'big' if self.metadata.get('big_endian', True) else 'little',
            'endian_marker': self.metadata.get('endian_marker', 'unknown'),
            'page_width_pt': self.metadata.get('page_width_pt', 0),
            'page_height_pt': self.metadata.get('page_height_pt', 0),
            'fonts': self.fonts,
            'styles': self.styles,
            'colors': self.colors,
            'content_count': len(self.content_strings),
        }


class P65Parser(PageMakerBaseParser):
    """Parse PageMaker P65 (6.5) files.

    P65 files are OLE/CFB containers with a /PageMaker stream.
    """

    def _load_data(self) -> Optional[bytes]:
        if not OLEFILE_AVAILABLE:
            logger.error("olefile module not available. Install with: pip install olefile")
            return None
        try:
            ole = olefile.OleFileIO(self.filepath)
            data = ole.openstream(['PageMaker']).read()
            ole.close()
            return data
        except Exception as e:
            logger.error(f"Error opening P65 file: {e}")
            return None


class PM5Parser(PageMakerBaseParser):
    """Parse PageMaker PM5 (5.0) files.

    PM5 files are flat binary files with a record-based structure.
    Unlike P65, they are NOT OLE containers.
    """

    def _load_data(self) -> Optional[bytes]:
        try:
            with open(self.filepath, 'rb') as f:
                return f.read()
        except Exception as e:
            logger.error(f"Error reading PM5 file: {e}")
            return None
