#!/usr/bin/env python3
"""
Unit tests for PageMaker parser module (P65 and PM5).
"""

import os
import unittest
from pagemaker_parser import P65Parser, PM5Parser
from p65_pdf import P65PDFGenerator

try:
    from prv_extractor import is_prv_file, extract_prv_preview
    PRV_AVAILABLE = True
except ImportError:
    PRV_AVAILABLE = False


class TestP65Parser(unittest.TestCase):
    """Test cases for P65Parser class."""

    def setUp(self):
        """Set up test fixtures."""
        self.test_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'samples')
        self.sample1_path = os.path.join(self.test_dir, 'sample1.p65')
        self.sample2_path = os.path.join(self.test_dir, 'sample2.p65')

    def test_parser_initialization(self):
        """Test parser initializes correctly."""
        parser = P65Parser(self.sample1_path)
        self.assertEqual(parser.filepath, self.sample1_path)
        self.assertIsNone(parser.page_maker_data)
        self.assertEqual(parser.fonts, [])
        self.assertEqual(parser.styles, [])
        self.assertEqual(parser.colors, [])
        self.assertEqual(parser.content_strings, [])

    def test_parse_existing_file(self):
        """Test parsing an existing P65 file."""
        if not os.path.exists(self.sample1_path):
            self.skipTest("Sample file not found")

        parser = P65Parser(self.sample1_path)
        result = parser.parse()
        self.assertTrue(result)
        self.assertIsNotNone(parser.page_maker_data)
        self.assertTrue(len(parser.page_maker_data) > 0)

    def test_parse_nonexistent_file(self):
        """Test parsing a non-existent file."""
        parser = P65Parser('/nonexistent/file.p65')
        result = parser.parse()
        self.assertFalse(result)

    def test_extract_metadata(self):
        """Test metadata extraction."""
        if not os.path.exists(self.sample1_path):
            self.skipTest("Sample file not found")

        parser = P65Parser(self.sample1_path)
        parser.parse()

        info = parser.get_info()
        self.assertIn('version', info)
        self.assertIn('page_width_pt', info)
        self.assertIn('page_height_pt', info)
        self.assertIn('fonts', info)
        self.assertIn('styles', info)
        self.assertIn('colors', info)
        self.assertIn('content_count', info)

    def test_extract_strings(self):
        """Test string extraction."""
        if not os.path.exists(self.sample1_path):
            self.skipTest("Sample file not found")

        parser = P65Parser(self.sample1_path)
        parser.parse()

        # Should extract some content strings
        self.assertTrue(len(parser.content_strings) > 0)

    def test_get_text_content(self):
        """Test getting text content as string."""
        if not os.path.exists(self.sample1_path):
            self.skipTest("Sample file not found")

        parser = P65Parser(self.sample1_path)
        parser.parse()

        text = parser.get_text_content()
        self.assertIsInstance(text, str)
        if parser.content_strings:
            self.assertTrue(len(text) > 0)

    def test_is_content_string_filtering(self):
        """Test content string filtering logic."""
        parser = P65Parser(self.sample1_path)

        # Test short strings are filtered
        self.assertFalse(parser._is_content_string("ab"))

        # Test numeric strings are filtered
        self.assertFalse(parser._is_content_string("12345"))

        # Test file paths are filtered
        self.assertFalse(parser._is_content_string("C:\\Windows\\System32"))

        # Test metadata patterns are filtered
        self.assertFalse(parser._is_content_string("Adobe PageMaker"))
        self.assertFalse(parser._is_content_string("PANTONE Color"))

        # Test EF prefix is filtered
        self.assertFalse(parser._is_content_string("EFSpotColors"))
        self.assertFalse(parser._is_content_string("EFPureBlack"))

        # Test internal naming patterns are filtered
        self.assertFalse(parser._is_content_string("lgobloda"))
        self.assertFalse(parser._is_content_string("gobjLISTJ"))
        self.assertFalse(parser._is_content_string("pageflgs"))

        # Test document structure words are filtered
        self.assertFalse(parser._is_content_string("DISPLAY"))
        self.assertFalse(parser._is_content_string("None"))
        self.assertFalse(parser._is_content_string("Default"))

        # Test repeated-character strings are filtered
        self.assertFalse(parser._is_content_string("TDDDDDDDDDDDH"))

        # Test single very short words are filtered
        self.assertFalse(parser._is_content_string("None"))
        self.assertFalse(parser._is_content_string("Default"))

        # Test valid content passes
        self.assertTrue(parser._is_content_string("Schedule of Events"))
        self.assertTrue(parser._is_content_string("Monday Morning Session"))
        self.assertTrue(parser._is_content_string("This is a longer body text that should pass the filter"))

    def test_parse_second_sample(self):
        """Test parsing second sample file."""
        if not os.path.exists(self.sample2_path):
            self.skipTest("Sample2 file not found")

        parser = P65Parser(self.sample2_path)
        result = parser.parse()
        self.assertTrue(result)


class TestP65ParserEdgeCases(unittest.TestCase):
    """Edge case tests for P65Parser."""

    def test_empty_data_handling(self):
        """Test handling of empty data."""
        parser = P65Parser.__new__(P65Parser)
        parser.filepath = "test.p65"
        parser.page_maker_data = b""
        parser.fonts = []
        parser.styles = []
        parser.colors = []
        parser.content_strings = []
        parser.metadata = {}

        # Should not crash
        parser._extract_page_dimensions(b"")
        parser._extract_strings(b"")
        parser._analyze_content()

        self.assertEqual(parser.content_strings, [])

    def test_content_string_deduplication(self):
        """Test content string deduplication."""
        parser = P65Parser.__new__(P65Parser)
        parser.filepath = "test.p65"
        parser.page_maker_data = None
        parser.fonts = []
        parser.styles = []
        parser.colors = []
        parser.metadata = {}
        parser.content_strings = [
            (100, "Hello World"),
            (120, "Hello World"),  # Duplicate
            (500, "Another String"),
            (520, "Another String"),  # Duplicate
        ]

        parser._analyze_content()

        # Duplicates should be removed
        self.assertEqual(len(parser.content_strings), 2)
        self.assertEqual(parser.content_strings[0], "Hello World")
        self.assertEqual(parser.content_strings[1], "Another String")


class TestPM5Parser(unittest.TestCase):
    """Test cases for PM5Parser class."""

    def setUp(self):
        """Set up test fixtures."""
        self.test_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'samples')
        self.sample_paths = [
            os.path.join(self.test_dir, '94INVITE.PM5'),
            os.path.join(self.test_dir, '96INVITE.PM5'),
        ]
        self.available_samples = [p for p in self.sample_paths if os.path.exists(p)]

    def test_parser_initialization(self):
        """Test PM5Parser initializes correctly."""
        if not self.available_samples:
            self.skipTest("No PM5 samples found")
        parser = PM5Parser(self.available_samples[0])
        self.assertEqual(parser.filepath, self.available_samples[0])
        self.assertIsNone(parser.page_maker_data)

    def test_parse_flat_binary(self):
        """Test parsing PM5 flat binary files."""
        for path in self.available_samples:
            with self.subTest(file=os.path.basename(path)):
                parser = PM5Parser(path)
                result = parser.parse()
                self.assertTrue(result, f"Failed to parse {path}")
                self.assertIsNotNone(parser.page_maker_data)
                self.assertTrue(len(parser.page_maker_data) > 0)

    def test_extract_strings_from_pm5(self):
        """Test string extraction from PM5 files."""
        for path in self.available_samples:
            with self.subTest(file=os.path.basename(path)):
                parser = PM5Parser(path)
                parser.parse()
                self.assertGreater(len(parser.content_strings), 0,
                    f"No content strings extracted from {path}")

    def test_extract_metadata_from_pm5(self):
        """Test metadata extraction from PM5 files."""
        for path in self.available_samples:
            with self.subTest(file=os.path.basename(path)):
                parser = PM5Parser(path)
                parser.parse()
                info = parser.get_info()
                self.assertIn('version', info)
                self.assertIn('page_width_pt', info)
                self.assertIn('page_height_pt', info)

    def test_generate_pdf_from_pm5(self):
        """Test PDF generation from PM5 files."""
        for path in self.available_samples:
            with self.subTest(file=os.path.basename(path)):
                parser = PM5Parser(path)
                parser.parse()
                output_path = os.path.join(self.test_dir,
                    f"{os.path.basename(path).split('.')[0]}_test.pdf")
                try:
                    generator = P65PDFGenerator(parser)
                    success = generator.generate(output_path)
                    self.assertTrue(success, f"Failed to generate PDF from {path}")
                    self.assertTrue(os.path.exists(output_path))
                    self.assertGreater(os.path.getsize(output_path), 1000)
                finally:
                    if os.path.exists(output_path):
                        os.remove(output_path)


class TestPRVExtractor(unittest.TestCase):
    """Test cases for PRVExtractor class."""

    def setUp(self):
        """Set up test fixtures."""
        self.test_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'samples')
        self.prv_path = os.path.join(self.test_dir, '96INVITE.PRV')

    def test_prv_detection(self):
        """Test PRV file detection."""
        if not os.path.exists(self.prv_path):
            self.skipTest("PRV sample not found")

        self.assertTrue(is_prv_file(self.prv_path))
        self.assertFalse(is_prv_file("/nonexistent/file.prv"))
        self.assertFalse(is_prv_file(__file__))  # This Python file

    def test_extract_preview(self):
        """Test preview bitmap extraction."""
        if not os.path.exists(self.prv_path):
            self.skipTest("PRV sample not found")

        output_path = os.path.join(self.test_dir, 'test_preview.jpg')
        try:
            success = extract_prv_preview(self.prv_path, output_path)
            self.assertTrue(success)
            self.assertTrue(os.path.exists(output_path))
            self.assertGreater(os.path.getsize(output_path), 1000)

            # Verify it's a valid JPEG
            with open(output_path, 'rb') as f:
                header = f.read(3)
                self.assertEqual(header[:2], b'\xff\xd8')  # JPEG SOI marker
        finally:
            if os.path.exists(output_path):
                os.remove(output_path)


if __name__ == '__main__':
    unittest.main()
