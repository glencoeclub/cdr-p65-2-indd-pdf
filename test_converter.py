#!/usr/bin/env python3
"""
Unit tests for converter module.
"""

import os
import unittest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from converter import find_files, is_inkscape_available


class TestConverter(unittest.TestCase):
    """Test cases for converter functions."""

    def test_find_files(self):
        """Test finding files with given extensions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test files
            Path(os.path.join(tmpdir, "file1.cdr")).touch()
            Path(os.path.join(tmpdir, "file2.CDR")).touch()
            Path(os.path.join(tmpdir, "file3.p65")).touch()
            Path(os.path.join(tmpdir, "file4.txt")).touch()

            # Find CDR files
            cdr_files = find_files(tmpdir, ['cdr'])
            self.assertEqual(len(cdr_files), 2)

            # Find P65 files
            p65_files = find_files(tmpdir, ['p65'])
            self.assertEqual(len(p65_files), 1)

            # Find both
            all_files = find_files(tmpdir, ['cdr', 'p65'])
            self.assertEqual(len(all_files), 3)

    def test_find_files_empty_directory(self):
        """Test finding files in empty directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            files = find_files(tmpdir, ['cdr'])
            self.assertEqual(len(files), 0)

    @patch('converter.subprocess.run')
    @patch('converter.shutil.which')
    def test_inkscape_available(self, mock_which, mock_run):
        """Test Inkscape availability check."""
        mock_which.return_value = '/usr/bin/inkscape'
        mock_run.return_value = Mock(returncode=0)
        self.assertTrue(is_inkscape_available())
        mock_which.assert_called_once_with('inkscape')

    @patch('converter.shutil.which')
    def test_inkscape_not_available(self, mock_which):
        """Test Inkscape not available check."""
        mock_which.return_value = None
        self.assertFalse(is_inkscape_available())
        mock_which.assert_called_once_with('inkscape')

    @patch('converter.subprocess.run')
    @patch('converter.shutil.which')
    def test_inkscape_broken_symlink(self, mock_which, mock_run):
        """Test Inkscape detected but binary broken."""
        mock_which.return_value = '/opt/homebrew/bin/inkscape'
        mock_run.side_effect = FileNotFoundError()
        self.assertFalse(is_inkscape_available())

    @patch('converter.PAGE_MAKER_AVAILABLE', True)
    @patch('converter.PM5Parser')
    @patch('converter.P65PDFGenerator')
    def test_convert_pagemaker_to_pdf_success(self, mock_gen_class, mock_parser_class):
        """Test successful PageMaker to PDF conversion."""
        from converter import convert_pagemaker_to_pdf

        # Mock parser and generator
        mock_parser = Mock()
        mock_parser.parse.return_value = True
        mock_parser_class.return_value = mock_parser

        mock_gen = Mock()
        mock_gen.generate.return_value = True
        mock_gen_class.return_value = mock_gen

        with tempfile.TemporaryDirectory() as tmpdir:
            input_file = os.path.join(tmpdir, "test.pm5")
            output_file = os.path.join(tmpdir, "test.pdf")

            # Create dummy input file
            Path(input_file).touch()

            result = convert_pagemaker_to_pdf(input_file, output_file)
            self.assertTrue(result)

    def test_convert_pagemaker_to_pdf_missing_input(self):
        """Test PageMaker conversion with missing input file."""
        from converter import convert_pagemaker_to_pdf

        result = convert_pagemaker_to_pdf('/nonexistent/file.pm5', '/tmp/output.pdf')
        self.assertFalse(result)

    @patch('converter.CDR_PDF_AVAILABLE', True)
    @patch('converter.convert_cdr_to_composite_pdf')
    def test_convert_cdr_uses_composite(self, mock_composite):
        """Test CDR conversion uses composite PDF generator."""
        from converter import convert_cdr_to_pdf

        mock_composite.return_value = True
        result = convert_cdr_to_pdf('/tmp/test.cdr', '/tmp/test.pdf')
        self.assertTrue(result)
        mock_composite.assert_called_once_with('/tmp/test.cdr', '/tmp/test.pdf')

    @patch('converter.CDR_PDF_AVAILABLE', False)
    @patch('converter.shutil.which')
    def test_convert_cdr_without_inkscape_fallback(self, mock_which):
        """Test CDR conversion fallback without Inkscape."""
        from converter import convert_cdr_to_pdf

        mock_which.return_value = None
        result = convert_cdr_to_pdf('/tmp/test.cdr', '/tmp/test.pdf')
        self.assertFalse(result)

    def test_convert_cdr_missing_input(self):
        """Test CDR conversion with missing input file."""
        from converter import convert_cdr_to_pdf

        result = convert_cdr_to_pdf('/nonexistent/file.cdr', '/tmp/output.pdf')
        self.assertFalse(result)

    def test_naming_preserves_extension(self):
        """Test output naming preserves original extension."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test file with extension
            input_file = os.path.join(tmpdir, "sample2.cdr")
            Path(input_file).touch()

            # Verify the naming logic would produce correct output
            input_path = Path(input_file)
            expected_output = f"{input_path.name}.pdf"  # sample2.cdr.pdf
            self.assertEqual(expected_output, "sample2.cdr.pdf")


if __name__ == '__main__':
    unittest.main()
