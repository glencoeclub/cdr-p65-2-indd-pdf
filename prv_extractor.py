#!/usr/bin/env python3
"""
Extensis PagePreview (.PRV) file extractor.

PRV files are created by the Extensis PagePreview utility for PageMaker.
They contain a low-resolution preview bitmap of the document.

File structure:
- Header: "Extensis PagePreview File" + version + null-terminated path
- Page dimensions (width/height in points, little-endian uint16 at 0x12A/0x12C)
- BITMAPINFOHEADER (40 bytes at 0x14C)
- 16-color EGA palette (64 bytes at 0x180, BGRx format)
- 4bpp pixel data (bottom-to-top scanlines)
"""

import struct
import logging

logger = logging.getLogger(__name__)

PRV_MAGIC = b'Extensis PagePreview File'
PRV_HEADER_SIZE = 0x128


def is_prv_file(filepath: str) -> bool:
    """Check if file is an Extensis PagePreview file."""
    try:
        with open(filepath, 'rb') as f:
            header = f.read(len(PRV_MAGIC))
            return header == PRV_MAGIC
    except Exception:
        return False


def extract_prv_preview(filepath: str, output_path: str) -> bool:
    """Extract preview bitmap from PRV file and save as JPEG.

    Args:
        filepath: Path to the .prv file
        output_path: Path to save the extracted JPEG

    Returns:
        True if extraction succeeded, False otherwise
    """
    try:
        from PIL import Image
    except ImportError:
        logger.error("Pillow not available. Install with: pip install Pillow")
        return False

    try:
        with open(filepath, 'rb') as f:
            data = f.read()
    except Exception as e:
        logger.error(f"Error reading PRV file: {e}")
        return False

    if data[:len(PRV_MAGIC)] != PRV_MAGIC:
        logger.error(f"Not a PRV file: {filepath}")
        return False

    if len(data) < PRV_HEADER_SIZE + 64:
        logger.error(f"PRV file too small: {filepath}")
        return False

    # Parse BITMAPINFOHEADER at 0x14C
    bih_offset = 0x14C
    bih_size = struct.unpack('<I', data[bih_offset:bih_offset + 4])[0]
    if bih_size != 40:
        logger.warning(f"Unexpected BITMAPINFOHEADER size: {bih_size}")

    bmp_width = struct.unpack('<I', data[bih_offset + 4:bih_offset + 8])[0]
    bmp_height = struct.unpack('<I', data[bih_offset + 8:bih_offset + 12])[0]
    planes = struct.unpack('<H', data[bih_offset + 12:bih_offset + 14])[0]
    bpp = struct.unpack('<H', data[bih_offset + 14:bih_offset + 16])[0]

    if planes != 1 or bpp != 4:
        logger.warning(f"Unexpected bitmap format: {planes} planes, {bpp} bpp")

    # Parse 16-color EGA palette at 0x180
    palette_offset = 0x180
    palette = []
    for i in range(16):
        off = palette_offset + i * 4
        b, g, r, _ = data[off:off + 4]
        palette.append((r, g, b))

    # Parse 4bpp pixel data at 0x1C0
    pixel_offset = 0x1C0
    row_stride = ((bmp_width + 7) // 8) * 4  # 4bpp, rows aligned to 4 bytes

    img = Image.new('RGB', (bmp_width, bmp_height))
    px = img.load()

    for y in range(bmp_height):
        row_start = pixel_offset + y * row_stride
        for x in range(bmp_width):
            byte_offset = row_start + x // 2
            if byte_offset >= len(data):
                break
            byte = data[byte_offset]
            if x % 2 == 0:
                idx = (byte >> 4) & 0x0F
            else:
                idx = byte & 0x0F
            if idx < len(palette):
                px[x, bmp_height - 1 - y] = palette[idx]

    # Save as JPEG
    try:
        img.save(output_path, 'JPEG', quality=85)
        logger.info(f"Extracted PRV preview: {output_path} ({bmp_width}x{bmp_height})")
        return True
    except Exception as e:
        logger.error(f"Error saving PRV preview: {e}")
        return False
