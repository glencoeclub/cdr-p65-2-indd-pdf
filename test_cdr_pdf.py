#!/usr/bin/env python3
"""
Unit tests for CDR composite PDF generator.
"""

import os
import unittest
import tempfile
from pathlib import Path

try:
    from cdr_pdf import CDRParser, convert_cdr_to_composite_pdf, PIKEPDF_AVAILABLE
    CDR_PDF_AVAILABLE = True
except ImportError:
    CDR_PDF_AVAILABLE = False
    PIKEPDF_AVAILABLE = False


class TestCDRParser(unittest.TestCase):
    """Test cases for CDRParser class."""

    def setUp(self):
        """Set up test fixtures."""
        self.test_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'samples')
        self.sample1_path = os.path.join(self.test_dir, 'sample1.cdr')
        self.sample2_path = os.path.join(self.test_dir, 'sample2.cdr')
        self.sample3_path = os.path.join(self.test_dir, 'sample3.cdr')
        self.available_samples = [
            p for p in [self.sample1_path, self.sample2_path, self.sample3_path]
            if os.path.exists(p)
        ]

    def test_parser_initialization(self):
        """Test CDRParser initializes correctly."""
        if not self.available_samples:
            self.skipTest("No CDR samples found")
        parser = CDRParser(self.available_samples[0])
        self.assertEqual(parser.cdr_path, self.available_samples[0])
        self.assertIsNone(parser._zf)

    def test_parse_metadata(self):
        """Test metadata parsing from CDR files."""
        for path in self.available_samples:
            with self.subTest(file=os.path.basename(path)):
                parser = CDRParser(path)
                parser.parse()
                # Check that page dimensions are set
                self.assertIn('width_pt', parser.page_info)
                self.assertIn('height_pt', parser.page_info)
                self.assertGreater(parser.page_info['width_pt'], 0)
                self.assertGreater(parser.page_info['height_pt'], 0)
                parser.close()

    def test_parse_images(self):
        """Test image parsing from CDR files."""
        for path in self.available_samples:
            with self.subTest(file=os.path.basename(path)):
                parser = CDRParser(path)
                parser.parse()
                # Just verify it doesn't crash; images list may be empty
                self.assertIsInstance(parser.images, list)
                parser.close()

    def test_extract_image(self):
        """Test bitmap extraction from Bitmaps.dat."""
        if not self.available_samples:
            self.skipTest("No CDR samples found")

        with tempfile.TemporaryDirectory() as tmpdir:
            parser = CDRParser(self.available_samples[0])
            parser.parse()

            if not parser.images:
                parser.close()
                self.skipTest("No images to extract")

            try:
                zf = parser._ensure_open()
                bitmap_data = zf.read('content/data/Bitmaps.dat')

                # Extract first image
                img_info = parser.images[0]
                result = parser.extract_image(bitmap_data, img_info, tmpdir)

                if result:
                    self.assertTrue(os.path.exists(result))
                    self.assertGreater(os.path.getsize(result), 100)
            finally:
                parser.close()

    def test_composite_conversion(self):
        """Test full composite CDR to PDF conversion."""
        if not CDR_PDF_AVAILABLE:
            self.skipTest("cdr_pdf module not available")
        if not PIKEPDF_AVAILABLE:
            self.skipTest("pikepdf not available")
        if not self.available_samples:
            self.skipTest("No CDR samples found")

        with tempfile.TemporaryDirectory() as tmpdir:
            for path in self.available_samples:
                with self.subTest(file=os.path.basename(path)):
                    output_path = os.path.join(tmpdir, f"{os.path.basename(path)}.pdf")
                    result = convert_cdr_to_composite_pdf(path, output_path)
                    self.assertTrue(result, f"Failed to convert {path}")
                    self.assertTrue(os.path.exists(output_path))
                    # Verify output is non-trivial size
                    self.assertGreater(os.path.getsize(output_path), 1000)

    def test_composite_missing_input(self):
        """Test composite conversion with missing input file."""
        if not CDR_PDF_AVAILABLE:
            self.skipTest("cdr_pdf module not available")

        result = convert_cdr_to_composite_pdf('/nonexistent/file.cdr', '/tmp/output.pdf')
        self.assertFalse(result)


class TestCDRParserEdgeCases(unittest.TestCase):
    """Edge case tests for CDRParser."""

    def test_close_without_open(self):
        """Test closing parser without opening."""
        parser = CDRParser("/tmp/fake.cdr")
        parser.close()  # Should not crash

    def test_context_manager(self):
        """Test using parser as context manager."""
        if not os.path.exists(os.path.join(os.path.dirname(__file__), 'samples', 'sample1.cdr')):
            self.skipTest("Sample not found")

        path = os.path.join(os.path.dirname(__file__), 'samples', 'sample1.cdr')
        with CDRParser(path) as parser:
            parser.parse()
            self.assertIsNotNone(parser._zf)
        # After context exit, should be closed
        self.assertIsNone(parser._zf)


if __name__ == '__main__':
    unittest.main()
