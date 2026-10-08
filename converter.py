#!/usr/bin/env python3
"""
Converter for PageMaker (P65/PM5) and CorelDRAW (CDR) files to PDF.
Uses Inkscape for CDR conversion (via CLI).
Uses custom parser for PageMaker text extraction and PDF generation.
"""

import os
import sys
import subprocess
import argparse
import logging
import shutil
from pathlib import Path

try:
    from pagemaker_parser import P65Parser, PM5Parser
    from p65_pdf import P65PDFGenerator
    PAGE_MAKER_AVAILABLE = True
except ImportError as e:
    PAGE_MAKER_AVAILABLE = False
    P65Parser = None
    PM5Parser = None
    P65PDFGenerator = None

try:
    from cdr_pdf import convert_cdr_to_composite_pdf
    CDR_PDF_AVAILABLE = True
except ImportError as e:
    CDR_PDF_AVAILABLE = False
    convert_cdr_to_composite_pdf = None

try:
    from prv_extractor import is_prv_file, extract_prv_preview
    PRV_AVAILABLE = True
except ImportError as e:
    PRV_AVAILABLE = False
    is_prv_file = None
    extract_prv_preview = None

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def find_files(directory: str, extensions: list) -> list:
    """Find all files with given extensions in directory."""
    dir_path = Path(directory)
    files = set()
    for ext in extensions:
        files.update(dir_path.glob(f'*.{ext}'))
        files.update(dir_path.glob(f'*.{ext.upper()}'))
    return sorted(files)


def is_inkscape_available() -> bool:
    """Check if Inkscape is installed and functional."""
    inkscape_path = shutil.which('inkscape')
    if not inkscape_path:
        return False
    try:
        result = subprocess.run(
            ['inkscape', '--version'],
            capture_output=True, timeout=10
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, Exception):
        return False


def convert_cdr_to_pdf(input_path: str, output_path: str) -> bool:
    """Convert CDR file to PDF using composite method (Inkscape + bitmaps)."""
    if CDR_PDF_AVAILABLE:
        return convert_cdr_to_composite_pdf(input_path, output_path)

    # Fallback: try Inkscape only (no bitmaps)
    import shutil
    import subprocess
    inkscape_path = shutil.which('inkscape')
    if not inkscape_path:
        logger.error("Inkscape is not installed or not found in PATH. Please install Inkscape to convert CDR files.")
        return False

    if not os.path.exists(input_path):
        logger.error(f"Input file not found: {input_path}")
        return False

    try:
        cmd = [
            'inkscape',
            '--export-filename', output_path,
            input_path
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300
        )
        if result.returncode == 0:
            logger.info(f"Converted (Inkscape only, no bitmaps): {input_path} -> {output_path}")
            return True
        else:
            logger.error(f"Inkscape error: {result.stderr}")
            return False
    except subprocess.TimeoutExpired:
        logger.error(f"Timeout converting: {input_path}")
        return False
    except Exception as e:
        logger.error(f"Error converting {input_path}: {e}")
        return False


def convert_pagemaker_to_pdf(input_path: str, output_path: str) -> bool:
    """Convert PageMaker file (P65 or PM5) to PDF using custom parser."""
    if not PAGE_MAKER_AVAILABLE:
        logger.error("PageMaker parsing module not available")
        return False

    if not os.path.exists(input_path):
        logger.error(f"Input file not found: {input_path}")
        return False

    ext = Path(input_path).suffix.lower()
    if ext in ['.pm5', '.pmd']:
        parser = PM5Parser(input_path)
    else:
        parser = P65Parser(input_path)

    try:
        if not parser.parse():
            logger.error(f"Failed to parse {input_path}")
            return False

        generator = P65PDFGenerator(parser)
        success = generator.generate(output_path)
        if not success:
            logger.error(f"Failed to generate PDF: {output_path}")
            return False

        logger.info(f"Converted: {input_path} -> {output_path}")
        return True

    except Exception as e:
        logger.error(f"Error converting {input_path}: {e}")
        return False


def handle_pagemaker(input_path: str, output_dir: str) -> bool:
    """Handle PageMaker files (P65, PM5, PMD) - try automatic conversion."""
    output_path = Path(output_dir)
    output_file = output_path / f"{Path(input_path).name}.pdf"

    if PAGE_MAKER_AVAILABLE:
        success = convert_pagemaker_to_pdf(input_path, str(output_file))
        if success:
            return True

    logger.warning(f"PageMaker file: {input_path}")
    logger.warning("  Note: Full layout conversion requires Adobe InDesign CS6")
    logger.warning("  Extracted text version created (may lose formatting)")
    logger.warning(f"  Output: {output_file}")
    return False


def handle_prv(input_path: str, output_dir: str) -> bool:
    """Handle PRV files - extract preview bitmap."""
    if not PRV_AVAILABLE:
        logger.info(f"Skipping PRV file (preview): {input_path}")
        return True

    output_path = Path(output_dir)
    output_file = output_path / f"{Path(input_path).name}.jpg"

    try:
        success = extract_prv_preview(input_path, str(output_file))
        if success:
            logger.info(f"Extracted preview: {input_path} -> {output_file}")
            return True
        else:
            logger.warning(f"Could not extract preview from: {input_path}")
            return False
    except Exception as e:
        logger.error(f"Error extracting PRV preview {input_path}: {e}")
        return False



def convert_directory(input_dir: str, output_dir: str) -> None:
    """Convert all supported files in directory."""
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    cdr_files = find_files(input_dir, ['cdr'])
    p65_files = find_files(input_dir, ['p65', 'pm6', 'pmd', 'pm5'])
    prv_files = find_files(input_dir, ['prv'])

    logger.info(f"Found {len(cdr_files)} CDR file(s), {len(p65_files)} PageMaker file(s), {len(prv_files)} PRV file(s)")

    converted = 0
    failed = 0

    for cdr_file in cdr_files:
        output_file = output_path / f"{cdr_file.name}.pdf"
        if convert_cdr_to_pdf(str(cdr_file), str(output_file)):
            converted += 1
        else:
            failed += 1

    for pm_file in p65_files:
        if handle_pagemaker(str(pm_file), str(output_path)):
            converted += 1
        else:
            failed += 1

    for prv_file in prv_files:
        if handle_prv(str(prv_file), str(output_path)):
            converted += 1
        else:
            failed += 1

    logger.info(f"Conversion complete: {converted} succeeded, {failed} failed")


def main():
    parser = argparse.ArgumentParser(
        description='Convert CDR/P65/PM5/PRV files to PDF'
    )
    parser.add_argument(
        'input',
        nargs='?',
        default='.',
        help='Input directory or file (default: current directory)'
    )
    parser.add_argument(
        '-o', '--output',
        default='output',
        help='Output directory (default: output)'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose output'
    )

    args = parser.parse_args()

    if args.verbose:
        logger.setLevel(logging.DEBUG)

    input_path = Path(args.input)

    if input_path.is_file():
        if input_path.suffix.lower() == '.cdr':
            output_file = Path(args.output) / f"{input_path.name}.pdf"
            convert_cdr_to_pdf(str(input_path), str(output_file))
        elif input_path.suffix.lower() in ['.p65', '.pm6', '.pmd', '.pm5']:
            handle_pagemaker(str(input_path), args.output)
        elif input_path.suffix.lower() == '.prv':
            handle_prv(str(input_path), args.output)
    else:
        convert_directory(str(input_path), args.output)


if __name__ == '__main__':
    main()
