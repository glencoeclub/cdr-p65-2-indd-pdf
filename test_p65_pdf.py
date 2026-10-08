#!/usr/bin/env python3
"""
Unit tests for P65 PDF generator module.
"""

import os
import unittest
import tempfile
from unittest.mock import Mock, patch
from p65_pdf import P65PDFGenerator


class TestP65PDFGenerator(unittest.TestCase):
    """Test cases for P65PDFGenerator class."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_parser = Mock()
        self.mock_parser.content_strings = [
            "Sample Title",
            "Monday",
            "This is some body text content",
            "Another section",
            "9:00 AM - Meeting",
        ]
        self.mock_parser.metadata = {}
        self.generator = P65PDFGenerator(self.mock_parser)

    def test_generator_initialization(self):
        """Test generator initializes with custom styles."""
        self.assertIn('P65Title', self.generator.styles)
        self.assertIn('P65Heading', self.generator.styles)
        self.assertIn('P65Body', self.generator.styles)

    def test_classify_text_title(self):
        """Test title classification."""
        # Title case short text
        self.assertEqual(
            self.generator._classify_text("Annual Report 2024"),
            'P65Title'
        )
        # All caps short text
        self.assertEqual(
            self.generator._classify_text("MEETING SCHEDULE"),
            'P65Title'
        )

    def test_classify_text_heading(self):
        """Test heading classification."""
        # Text ending with colon
        self.assertEqual(
            self.generator._classify_text("Schedule:"),
            'P65Heading'
        )
        # Short lowercase phrase
        self.assertEqual(
            self.generator._classify_text("section one"),
            'P65Heading'
        )

    def test_classify_text_body(self):
        """Test body text classification."""
        # Longer text with punctuation
        self.assertEqual(
            self.generator._classify_text("This is a longer piece of text that should be classified as body."),
            'P65Body'
        )
        # Text with sentence punctuation
        self.assertEqual(
            self.generator._classify_text("Hello world. How are you?"),
            'P65Body'
        )

    def test_map_font(self):
        """Test font mapping."""
        self.assertEqual(
            self.generator._map_font('Times New Roman'),
            'Times-Roman'
        )
        self.assertEqual(
            self.generator._map_font('Arial'),
            'Helvetica'
        )
        self.assertEqual(
            self.generator._map_font('UnknownFont'),
            'Helvetica'  # Default fallback
        )

    def test_escape_xml(self):
        """Test XML escaping."""
        self.assertEqual(
            self.generator._escape_xml("Hello & World"),
            "Hello &amp; World"
        )
        self.assertEqual(
            self.generator._escape_xml("Test <tag>"),
            "Test &lt;tag&gt;"
        )

    def test_extract_title_from_content(self):
        """Test title extraction from content."""
        self.mock_parser.content_strings = [
            "Annual Conference Schedule",
            "Monday",
            "Body text",
        ]
        title = self.generator._extract_title()
        self.assertEqual(title, "Annual Conference Schedule")

    def test_extract_title_fallback(self):
        """Test title extraction fallback."""
        self.mock_parser.content_strings = [
            "short",
            "Another piece of text that is longer",
        ]
        title = self.generator._extract_title()
        self.assertEqual(title, "Another piece of text that is longer")

    def test_extract_title_default(self):
        """Test default title."""
        self.mock_parser.content_strings = []
        title = self.generator._extract_title()
        self.assertEqual(title, "PageMaker Document")

    def test_generate_pdf(self):
        """Test PDF generation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "test_output.pdf")
            result = self.generator.generate(output_path)
            self.assertTrue(result)
            self.assertTrue(os.path.exists(output_path))
            # Check file has some content
            self.assertGreater(os.path.getsize(output_path), 0)

    def test_generate_pdf_empty_content(self):
        """Test PDF generation with empty content."""
        self.mock_parser.content_strings = []
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "test_empty.pdf")
            result = self.generator.generate(output_path)
            self.assertTrue(result)
            self.assertTrue(os.path.exists(output_path))


if __name__ == '__main__':
    unittest.main()
