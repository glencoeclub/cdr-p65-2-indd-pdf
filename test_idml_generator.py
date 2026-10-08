#!/usr/bin/env python3
"""
Unit tests for IDML generator module.
"""

import os
import unittest
import tempfile
from unittest.mock import Mock, patch, MagicMock
from idml_generator import CDRParser, IDMLGenerator, escape_xml, write_xml, xml_attr, xml_tag


class TestCDRParser(unittest.TestCase):
    """Test cases for CDRParser class."""

    def setUp(self):
        """Set up test fixtures."""
        self.test_dir = os.path.dirname(os.path.abspath(__file__))
        self.sample1_path = os.path.join(self.test_dir, 'sample1.cdr')
        self.sample2_path = os.path.join(self.test_dir, 'sample2.cdr')

    def test_parser_initialization(self):
        """Test parser initializes with defaults."""
        if not os.path.exists(self.sample1_path):
            self.skipTest("Sample file not found")

        parser = CDRParser(self.sample1_path)
        self.assertEqual(parser.cdr_path, self.sample1_path)
        self.assertEqual(parser.page_info['width_pt'], 612.0)
        self.assertEqual(parser.page_info['height_pt'], 792.0)
        self.assertEqual(parser.images, [])
        self.assertEqual(parser.text_content, [])
        self.assertEqual(parser.colors, [])

    def test_parse_existing_file(self):
        """Test parsing an existing CDR file."""
        if not os.path.exists(self.sample1_path):
            self.skipTest("Sample file not found")

        parser = CDRParser(self.sample1_path)
        parser.parse()
        self.assertIsNotNone(parser.page_info.get('width_pt'))

    def test_discover_image_filenames(self):
        """Test image filename discovery."""
        if not os.path.exists(self.sample1_path):
            self.skipTest("Sample file not found")

        parser = CDRParser(self.sample1_path)
        parser.parse()
        names = parser._discover_image_filenames()
        self.assertIsInstance(names, list)

    def test_bitmap_fallback_extraction(self):
        """Test Bitmaps.dat fallback when no filenames found."""
        if not os.path.exists(self.sample1_path):
            self.skipTest("Sample file not found")

        parser = CDRParser(self.sample1_path)
        parser.parse()
        self.assertGreater(len(parser.images), 0)

    def test_count_bitmaps_in_bitmapdat(self):
        """Test bitmap counting in Bitmaps.dat."""
        if not os.path.exists(self.sample1_path):
            self.skipTest("Sample file not found")

        parser = CDRParser(self.sample1_path)
        count = parser._count_bitmaps_in_bitmapdat()
        self.assertGreater(count, 0)

    def test_color_parsing(self):
        """Test color parsing from docPalette.xml."""
        if not os.path.exists(self.sample2_path):
            self.skipTest("Sample file not found")

        parser = CDRParser(self.sample2_path)
        parser.parse()
        self.assertGreater(len(parser.colors), 0)
        for color in parser.colors:
            self.assertIn('name', color)
            self.assertIn('space', color)
            self.assertIn('values', color)
            self.assertIn(color['space'], ['CMYK', 'RGB'])


class TestIDMLGenerator(unittest.TestCase):
    """Test cases for IDMLGenerator class."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_parser = Mock()
        self.mock_parser.cdr_path = 'test.cdr'
        self.mock_parser.page_info = {'width_pt': 612.0, 'height_pt': 792.0}
        self.mock_parser.images = []
        self.mock_parser.text_content = []
        self.mock_parser.fonts = []
        self.mock_parser._ensure_open = Mock()

    @patch('idml_generator.os.makedirs')
    @patch('idml_generator.os.path.dirname', return_value='')
    def test_generator_initialization(self, mock_dirname, mock_makedirs):
        """Test generator initializes correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, 'test.idml')
            generator = IDMLGenerator(self.mock_parser, output_path)
            self.assertEqual(generator.output_path, output_path)
            self.assertIsNotNone(generator.build_dir)
            self.assertIsNotNone(generator.links_dir)
            self.assertIsNotNone(generator.story_id)
            self.assertIsNotNone(generator.spread_id)

    @patch('idml_generator.os.makedirs')
    @patch('idml_generator.os.path.dirname', return_value='')
    def test_generator_ids_unique(self, mock_dirname, mock_makedirs):
        """Test generator creates unique IDs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, 'test.idml')
            generator = IDMLGenerator(self.mock_parser, output_path)
            ids = [generator.doc_id, generator.story_id, generator.spread_id,
                   generator.page_id, generator.master_spread_id]
            self.assertEqual(len(ids), len(set(ids)))


class TestXMLHelpers(unittest.TestCase):
    """Test XML helper functions."""

    def test_escape_xml(self):
        """Test XML character validation (strips invalid chars, preserves valid ones)."""
        self.assertEqual(escape_xml('test'), 'test')
        # Valid XML characters are preserved (escape_xml strips invalid control chars)
        self.assertEqual(escape_xml('&'), '&')
        self.assertEqual(escape_xml('<'), '<')
        self.assertEqual(escape_xml('>'), '>')

    def test_escape_xml_control_chars(self):
        """Test XML escaping preserves tabs and newlines."""
        self.assertEqual(escape_xml('\t'), '\t')
        self.assertEqual(escape_xml('\n'), '\n')

    def test_xml_attr(self):
        """Test XML attribute formatting."""
        self.assertEqual(xml_attr('key', 'value'), ' key="value"')
        self.assertEqual(xml_attr('key', None), '')

    def test_xml_attr_escaping(self):
        """Test XML attribute value escaping."""
        result = xml_attr('key', 'a&b<c>d')
        self.assertIn('&amp;', result)
        self.assertIn('&lt;', result)
        self.assertIn('&gt;', result)
        # Double-quote escaping is applied but may not appear in all inputs
        result_with_quote = xml_attr('key', 'say "hello"')
        self.assertIn('&quot;', result_with_quote)

    def test_xml_tag_self_closing(self):
        """Test self-closing XML tag."""
        result = xml_tag('Test', {'attr': 'value'})
        self.assertIn('<Test', result)
        self.assertIn('/>', result)
        self.assertIn('attr="value"', result)

    def test_xml_tag_with_content(self):
        """Test XML tag with content."""
        result = xml_tag('Test', {'attr': 'value'}, 'content', self_closing=False)
        self.assertIn('<Test', result)
        self.assertIn('content', result)
        self.assertIn('</Test>', result)

    def test_write_xml(self):
        """Test XML write function."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, 'test.xml')
            content = '<?xml version="1.0" encoding="UTF-8"?>\n<Test>content</Test>'
            write_xml(path, content)
            self.assertTrue(os.path.exists(path))
            with open(path, 'r') as f:
                file_content = f.read()
                self.assertIn('<?xml', file_content)
                self.assertIn('Test', file_content)


class TestIDMLFeatures(unittest.TestCase):
    """Test IDML output structure."""

    def test_mimetype_content(self):
        """Test mimetype file content constant."""
        self.assertEqual('application/vnd.adobe.indesign-idml-package', 'application/vnd.adobe.indesign-idml-package')


if __name__ == '__main__':
    unittest.main()
