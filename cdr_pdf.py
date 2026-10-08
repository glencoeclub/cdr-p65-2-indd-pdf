#!/usr/bin/env python3
"""
Composite PDF generator for CorelDRAW CDR files.

Uses Inkscape for vector rendering and overlays bitmaps extracted from
Bitmaps.dat using pikepdf for the final composite PDF.
"""

import os
import tempfile
import logging
from pathlib import Path
from io import BytesIO

import struct
import zipfile
import re

try:
    import pikepdf
    PIKEPDF_AVAILABLE = True
except ImportError:
    PIKEPDF_AVAILABLE = False

try:
    from PIL import Image
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter

logger = logging.getLogger(__name__)


class CDRParser:
    """Parse CDR files to extract bitmaps and their positions."""

    def __init__(self, cdr_path):
        self.cdr_path = cdr_path
        self._zf = None
        self.page_info = {'width_pt': 612.0, 'height_pt': 792.0}
        self.images = []

    def parse(self):
        """Parse CDR file: extract metadata, image positions, bitmaps."""
        self._parse_metadata()
        self._parse_image_positions()

    def _ensure_open(self):
        if self._zf is None:
            self._zf = zipfile.ZipFile(self.cdr_path, 'r')
        return self._zf

    def close(self):
        if self._zf is not None:
            self._zf.close()
            self._zf = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def _parse_metadata(self):
        zf = self._ensure_open()
        try:
            metadata = zf.read('META-INF/metadata.xml').decode('utf-8')
        except KeyError:
            return
        rect_attrs = {}
        for attr in ['left', 'top', 'right', 'bottom']:
            m = re.search(rf'rect:{attr}="([^"]+)"', metadata)
            if m:
                rect_attrs[attr] = int(m.group(1))
        if len(rect_attrs) == 4:
            self.page_info['clip_rect'] = rect_attrs
            self.page_info['coord_width'] = rect_attrs['right'] - rect_attrs['left']
            self.page_info['coord_height'] = rect_attrs['top'] - rect_attrs['bottom']
            self.page_info['coord_origin_x'] = rect_attrs['left']
            self.page_info['coord_origin_y'] = rect_attrs['bottom']

    def _discover_image_filenames(self):
        discovered = []
        zf = self._ensure_open()
        try:
            content_xml = zf.read('META-INF/content.xml').decode('utf-8')
            for m in re.finditer(r'fileName="([^"]+\.(?:jpeg|jpg|png|tif|tiff))"',
                                 content_xml, re.IGNORECASE):
                discovered.append(m.group(1))
        except KeyError:
            pass
        if not discovered:
            discovered = self._find_images_in_data1()
        return discovered

    def _find_images_in_data1(self):
        discovered = []
        zf = self._ensure_open()
        try:
            data1 = zf.read('content/data/data1.dat')
            for encoding in ['utf-16-le', 'utf-8']:
                try:
                    text = data1.decode(encoding, errors='ignore')
                    for m in re.finditer(r'([A-Za-z0-9_-]+\.(?:jpeg|jpg|png|tif|tiff))', text):
                        img_name = m.group(1)
                        if img_name not in discovered and len(img_name) > 3:
                            discovered.append(img_name)
                except Exception:
                    continue
        except KeyError:
            pass
        return discovered

    def _count_bitmaps_in_bitmapdat(self):
        try:
            zf = self._ensure_open()
            bitmap_data = zf.read('content/data/Bitmaps.dat')
        except KeyError:
            return 0
        count = 0
        p = 0
        while True:
            p = bitmap_data.find(b'UI\x00\x00', p)
            if p == -1:
                break
            if p >= 8:
                try:
                    c = struct.unpack('<I', bitmap_data[p-8:p-4])[0]
                    v = struct.unpack('<I', bitmap_data[p-4:p])[0]
                    if c < 100 and v <= 5:
                        count += 1
                except struct.error:
                    pass
            p += 2
        return count

    def _parse_image_positions(self):
        zf = self._ensure_open()
        try:
            data1 = zf.read('content/data/data1.dat')
        except KeyError:
            data1 = None

        image_names = self._discover_image_filenames()
        if not image_names:
            return

        if data1 is None:
            pw, ph = self.page_info['width_pt'], self.page_info['height_pt']
            for i, name in enumerate(image_names):
                self.images.append({
                    'name': name, 'index': i,
                    'x': 0, 'y': 0, 'width': pw, 'height': ph,
                })
            return

        found_count = 0
        for idx, name in enumerate(image_names):
            for enc in ['utf-16-le', 'utf-8']:
                try:
                    encoded_name = name.encode(enc)
                    pos = data1.find(encoded_name)
                    if pos < 0:
                        pos = data1.find(encoded_name.lower())
                    if pos < 0:
                        continue
                except Exception:
                    continue

                offset = 0x60
                if pos < offset:
                    continue
                try:
                    coords = [struct.unpack('<i', data1[pos - offset + i*4:pos - offset + i*4 + 4])[0]
                              for i in range(4)]
                    x1, y1, x2, y2 = coords
                    if x1 == 0 and y1 == 0 and x2 == 0 and y2 == 0:
                        continue
                    cw = self.page_info.get('coord_width', 1)
                    ch = self.page_info.get('coord_height', 1)
                    ox = self.page_info.get('coord_origin_x', 0)
                    oy = self.page_info.get('coord_origin_y', 0)
                    nx1, ny1 = (x1 - ox) / cw, (y1 - oy) / ch
                    nx2, ny2 = (x2 - ox) / cw, (y2 - oy) / ch
                    pw, ph = self.page_info['width_pt'], self.page_info['height_pt']
                    l, r = min(nx1, nx2) * pw, max(nx1, nx2) * pw
                    t, b = min((1-ny1)*ph, (1-ny2)*ph), max((1-ny1)*ph, (1-ny2)*ph)
                    self.images.append({
                        'name': name, 'index': found_count,
                        'x': l, 'y': t, 'width': r-l, 'height': b-t,
                    })
                    found_count += 1
                    break
                except (struct.error, IndexError):
                    continue

        if found_count == 0 and image_names:
            count = self._count_bitmaps_in_bitmapdat()
            if count > 0:
                pw, ph = self.page_info['width_pt'], self.page_info['height_pt']
                for i in range(count):
                    self.images.append({
                        'name': f'bitmap_{i}.jpg', 'index': i,
                        'x': 0, 'y': 0, 'width': pw, 'height': ph,
                    })

    def extract_image(self, bitmap_data, img_info, out_dir):
        """Extract a single bitmap from Bitmaps.dat and save as JPEG."""
        if not PILLOW_AVAILABLE:
            return None

        positions = []
        p = 0
        while True:
            p = bitmap_data.find(b'UI\x00\x00', p)
            if p == -1:
                break
            if p >= 8:
                try:
                    c = struct.unpack('<I', bitmap_data[p-8:p-4])[0]
                    v = struct.unpack('<I', bitmap_data[p-4:p])[0]
                    if c < 100 and v <= 5:
                        positions.append(p - 8)
                except struct.error:
                    pass
            p += 2

        if img_info['index'] >= len(positions):
            return None

        try:
            h = positions[img_info['index']]
            chunk = bitmap_data[h:h+0x70]
            # Width and height are stored in the upper 16 bits of these 32-bit fields
            # (based on reverse engineering of CDR format; verify with actual files)
            w = (struct.unpack('<I', chunk[0x3C:0x40])[0] >> 16) & 0xFFFF
            ht = (struct.unpack('<I', chunk[0x40:0x44])[0] >> 16) & 0xFFFF

            if w == 0 or ht == 0 or w > 10000 or ht > 10000:
                return None

            ds = h + 0x70
            stride = ((w * 3 + 3) // 4) * 4
            needed = ds + ht * stride
            if needed > len(bitmap_data):
                ht = min(ht, (len(bitmap_data) - ds) // stride)
                if ht <= 0:
                    return None

            img = Image.new('RGB', (w, ht))
            px = img.load()
            for y in range(ht):
                row_start = ds + y * stride
                row_end = row_start + w * 3
                if row_end > len(bitmap_data):
                    break
                row = bitmap_data[row_start:row_end]
                if len(row) < w * 3:
                    break
                for x in range(w):
                    b_val, g_val, r_val = row[x*3], row[x*3+1], row[x*3+2]
                    px[x, y] = (r_val, g_val, b_val)

            img = img.transpose(Image.FLIP_TOP_BOTTOM)
            path = os.path.join(out_dir, img_info['name'].rsplit('.', 1)[0] + '.jpg')
            img.save(path, 'JPEG', quality=90)
            return path
        except (struct.error, IndexError, ValueError):
            return None


def _create_bitmap_overlay_pdf(images, page_width, page_height):
    """Create a PDF with bitmaps at their positions (transparent background)."""
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=(page_width, page_height))

    for img_info in images:
        link_path = img_info.get('link_path')
        if not link_path or not os.path.exists(link_path):
            continue

        x = img_info.get('x', 0)
        y = img_info.get('y', 0)
        w = img_info.get('width', 0)
        h = img_info.get('height', 0)

        if w <= 0 or h <= 0:
            continue

        try:
            c.drawImage(link_path, x, y, width=w, height=h, mask='auto')
        except Exception as e:
            logger.warning(f"Failed to draw image {img_info['name']}: {e}")

    c.save()
    buf.seek(0)
    return buf


def convert_cdr_to_composite_pdf(input_path: str, output_path: str) -> bool:
    """
    Convert CDR file to PDF using Inkscape (vectors) + bitmap overlay.

    Flow:
    1. Run Inkscape to get base PDF with vectors
    2. Extract bitmaps from Bitmaps.dat
    3. Create transparent overlay PDF with bitmaps
    4. Merge overlay onto base PDF using pikepdf
    """
    if not PIKEPDF_AVAILABLE:
        logger.error("pikepdf not available. Install with: pip install pikepdf")
        return False

    if not os.path.exists(input_path):
        logger.error(f"Input file not found: {input_path}")
        return False

    # Ensure output directory exists
    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    # Check Inkscape availability
    import shutil
    import subprocess
    inkscape_path = shutil.which('inkscape')
    if not inkscape_path:
        logger.error("Inkscape not available. Cannot convert CDR to PDF.")
        return False

    # Step 1: Run Inkscape to get base PDF
    logger.info(f"[1/4] Running Inkscape on {input_path}...")
    with tempfile.TemporaryDirectory() as tmpdir:
        base_pdf_path = os.path.join(tmpdir, 'base.pdf')
        try:
            result = subprocess.run(
                ['inkscape', '--export-filename', base_pdf_path, input_path],
                capture_output=True, text=True, timeout=300
            )
            if result.returncode != 0:
                logger.error(f"Inkscape error: {result.stderr}")
                return False
        except subprocess.TimeoutExpired:
            logger.error(f"Inkscape timeout converting {input_path}")
            return False
        except Exception as e:
            logger.error(f"Error running Inkscape: {e}")
            return False

        if not os.path.exists(base_pdf_path):
            logger.error("Inkscape did not produce output PDF")
            return False

        base_size = os.path.getsize(base_pdf_path)
        logger.info(f"[1/4] Inkscape produced {base_size:,} byte PDF")

        # Step 2: Parse CDR and extract bitmaps
        logger.info(f"[2/4] Parsing CDR for bitmaps...")
        with CDRParser(input_path) as parser:
            parser.parse()
            logger.info(f"[2/4] Found {len(parser.images)} image(s)")

            if not parser.images:
                # No bitmaps found, just use Inkscape output
                logger.info("[3/4] No bitmaps to overlay, using Inkscape output directly")
                import shutil
                shutil.copy2(base_pdf_path, output_path)
                return True

            # Extract bitmaps to temp dir
            with tempfile.TemporaryDirectory() as imgdir:
                try:
                    zf = parser._ensure_open()
                    bitmap_data = zf.read('content/data/Bitmaps.dat')
                except KeyError:
                    logger.warning("Bitmaps.dat not found, using Inkscape output")
                    shutil.copy2(base_pdf_path, output_path)
                    return True

                extracted = 0
                for img_info in parser.images:
                    path = parser.extract_image(bitmap_data, img_info, imgdir)
                    if path:
                        img_info['link_path'] = path
                        extracted += 1

                logger.info(f"[2/4] Extracted {extracted}/{len(parser.images)} bitmap(s)")

                if extracted == 0:
                    logger.info("[3/4] No bitmaps extracted, using Inkscape output")
                    shutil.copy2(base_pdf_path, output_path)
                    return True

                # Step 3: Get page dimensions from Inkscape PDF
                logger.info(f"[3/4] Creating bitmap overlay...")
                with pikepdf.open(base_pdf_path) as pdf:
                    page = pdf.pages[0]
                    mb = page.MediaBox
                    page_width = float(mb[2]) - float(mb[0])
                    page_height = float(mb[3]) - float(mb[1])

                # Create overlay PDF with bitmaps
                overlay_buf = _create_bitmap_overlay_pdf(
                    parser.images, page_width, page_height
                )

                # Step 4: Merge overlay onto base
                logger.info(f"[4/4] Compositing bitmaps onto PDF...")
                with pikepdf.open(base_pdf_path) as base:
                    with pikepdf.open(overlay_buf) as overlay:
                        base.pages[0].add_overlay(overlay.pages[0])
                        base.save(output_path)

        logger.info(f"Converted: {input_path} -> {output_path}")
        return True
