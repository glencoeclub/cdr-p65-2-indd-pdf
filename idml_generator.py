#!/usr/bin/env python3
"""
Convert CorelDRAW (.cdr) files to Adobe InDesign IDML format.
Generates a complete, valid IDML package that InDesign can open.

Uses the IDML packaging namespace (xmlns:idPkg) as required by InDesign CS6+.
"""

import zipfile
import struct
import os
import sys
import uuid
import re
import shutil
import html
import xml.etree.ElementTree as ET
from xml.dom import minidom

# IDML uses the packaging namespace for content files
PKG_NS = "http://ns.adobe.com/AdobeInDesign/idml/1.0/packaging"
# The content elements use no default namespace - they get the idPkg prefix
ET.register_namespace('idPkg', PKG_NS)

DOM_VERSION = "19.0"

# ==============================================================================
# CDR Parser (unchanged)
# ==============================================================================

class CDRParser:
    IMAGE_UNITS = 100.0

    def __init__(self, cdr_path):
        self.cdr_path = cdr_path
        self._zf = None  # Opened lazily in parse()
        self.page_info = {'width_pt': 612.0, 'height_pt': 792.0}
        self.images = []
        self.text_content = []
        self.fonts = []
        self.colors = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def _ensure_open(self):
        """Open the zip file if not already open."""
        if self._zf is None:
            self._zf = zipfile.ZipFile(self.cdr_path, 'r')
        return self._zf

    def parse(self):
        self._parse_metadata()
        self._parse_text_content()
        self._parse_image_positions()
        self._parse_colors()

    def close(self):
        if self._zf is not None:
            self._zf.close()
            self._zf = None

    def _parse_metadata(self):
        zf = self._ensure_open()
        metadata = zf.read('META-INF/metadata.xml').decode('utf-8')
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
            print(f"  ClipRect: ({rect_attrs['left']}, {rect_attrs['top']}) to ({rect_attrs['right']}, {rect_attrs['bottom']})")
        print(f"  Page: {self.page_info['width_pt']:.0f} x {self.page_info['height_pt']:.0f} pt (Letter)")

    def _parse_text_content(self):
        zf = self._ensure_open()
        textinfo = zf.read('META-INF/textinfo.xml').decode('utf-8')
        for m in re.finditer(r'<TextStream[^>]*>(.*?)</TextStream>', textinfo, re.DOTALL):
            runs = []
            for rm in re.finditer(r'<TextRun([^>]*)>(.*?)</TextRun>', m.group(1)):
                text = html.unescape(rm.group(2))
                runs.append({
                    'text': text,
                    'break': re.search(r'break="(\w+)"', rm.group(1)).group(1) if re.search(r'break="(\w+)"', rm.group(1)) else 'none',
                })
            if runs:
                self.text_content.append(runs)
        print(f"  Text streams: {len(self.text_content)}")

    def _discover_image_filenames(self):
        discovered = []
        zf = self._ensure_open()
        try:
            content_xml = zf.read('META-INF/content.xml').decode('utf-8')
            for m in re.finditer(r'fileName="([^"]+\.(?:jpeg|jpg|png|tif|tiff))"', content_xml, re.IGNORECASE):
                discovered.append(m.group(1))
        except KeyError:
            pass
        if not discovered:
            discovered = self._find_images_in_data1()
        if not discovered:
            count = self._count_bitmaps_in_bitmapdat()
            if count > 0:
                discovered = [f'bitmap_{i}.jpg' for i in range(count)]
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

    def _parse_colors(self):
        zf = self._ensure_open()
        try:
            palette_xml = zf.read('color/docPalette.xml').decode('utf-8')
        except KeyError:
            return
        for m in re.finditer(r'<color\s+cs="([^"]+)"\s+name="([^"]+)"\s+tints="([^"]+)"', palette_xml):
            cs, name, tints_str = m.group(1), m.group(2), m.group(3)
            tints = [float(x) for x in tints_str.split(',') if x]
            if cs == 'CMYK' and len(tints) == 4:
                self.colors.append({
                    'name': name, 'space': 'CMYK',
                    'values': [int(v * 100) for v in tints],
                })
            elif cs == 'RGB' and len(tints) == 3:
                self.colors.append({
                    'name': name, 'space': 'RGB',
                    'values': [int(v * 255) for v in tints],
                })
            elif cs == 'Black':
                k_val = int(tints[0] * 100) if tints else 100
                self.colors.append({
                    'name': name, 'space': 'CMYK',
                    'values': [0, 0, 0, k_val],
                })
        print(f"  Colors: {len(self.colors)}")

    def _find_images_in_data1(self):
        discovered = []
        zf = self._ensure_open()
        try:
            data1 = zf.read('content/data/data1.dat')
            for encoding in ['utf-8', 'utf-16-le', 'latin-1']:
                try:
                    text = data1.decode(encoding, errors='ignore')
                    for m in re.finditer(r'([A-Za-z0-9_-]+\.(?:jpeg|jpg|png|tif|tiff))', text):
                        img_name = m.group(1)
                        if img_name not in discovered and len(img_name) > 3:
                            discovered.append(img_name)
                except:
                    continue
        except KeyError:
            pass
        return discovered

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
                print(f"  Image #{i}: {name} (no position data, full page)")
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
                except:
                    continue
                    
                offset = 0x60
                if pos < offset:
                    continue
                try:
                    coords = [struct.unpack('<i', data1[pos - offset + i*4:pos - offset + i*4 + 4])[0] for i in range(4)]
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
                    self.images.append({'name': name, 'index': found_count, 'x': l, 'y': t, 'width': r-l, 'height': b-t})
                    print(f"  Image #{found_count}: {name} at ({l:.0f}, {t:.0f}) {r-l:.0f}x{b-t:.0f} pt")
                    found_count += 1
                    break
                except (struct.error, IndexError) as e:
                    print(f"  Warning: Failed to parse coordinates for {name}: {e}")
                    continue

        if found_count == 0 and image_names:
            count = self._count_bitmaps_in_bitmapdat()
            if count > 0:
                pw, ph = self.page_info['width_pt'], self.page_info['height_pt']
                for i in range(count):
                    name = f'bitmap_{i}.jpg'
                    self.images.append({
                        'name': name, 'index': i,
                        'x': 0, 'y': 0, 'width': pw, 'height': ph,
                    })
                    print(f"  Image #{i}: {name} (fallback, no position data)")

    def extract_image(self, bitmap_data, img_info, out_dir):
        from PIL import Image
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
            print(f"  Warning: No bitmap position found for image #{img_info['index']} ({img_info.get('name', 'unknown')})")
            return None

        try:
            h = positions[img_info['index']]
            chunk = bitmap_data[h:h+0x70]
            # Width and height are stored in the upper 16 bits of these 32-bit fields
            # (based on reverse engineering of CDR format; verify with actual files)
            w = (struct.unpack('<I', chunk[0x3C:0x40])[0] >> 16) & 0xFFFF
            ht = (struct.unpack('<I', chunk[0x40:0x44])[0] >> 16) & 0xFFFF

            if w == 0 or ht == 0 or w > 10000 or ht > 10000:
                print(f"  Warning: Invalid image dimensions ({w}x{ht}) for {img_info.get('name', 'unknown')}")
                return None

            ds = h + 0x70
            stride = ((w * 3 + 3) // 4) * 4

            # Ensure we don't read past the buffer
            needed = ds + ht * stride
            if needed > len(bitmap_data):
                print(f"  Warning: Bitmap data truncated for {img_info.get('name', 'unknown')} (need {needed}, have {len(bitmap_data)})")
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
                    b, g, r = row[x*3], row[x*3+1], row[x*3+2]
                    px[x, y] = (r, g, b)

            img = img.transpose(Image.FLIP_TOP_BOTTOM)
            path = os.path.join(out_dir, img_info['name'].rsplit('.', 1)[0] + '.jpg')
            img.save(path, 'JPEG', quality=90)
            return path
        except (struct.error, IndexError, ValueError) as e:
            print(f"  Warning: Failed to extract image {img_info.get('name', 'unknown')}: {e}")
            return None


# ==============================================================================
# IDML Helpers
# ==============================================================================

def write_xml(path, content):
    """Write XML content directly as a complete XML string (no ElementTree)."""
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)


def escape_xml(text):
    """Escape text safely for XML content."""
    if not text:
        return text
    cleaned = []
    for c in text:
        code = ord(c)
        if code == 0x09 or code == 0x0A or code == 0x0D:
            cleaned.append(c)
        elif 0x20 <= code <= 0xD7FF:
            cleaned.append(c)
        elif 0xE000 <= code <= 0xFFFD:
            cleaned.append(c)
        elif 0x10000 <= code <= 0x10FFFF:
            cleaned.append(c)
        else:
            cleaned.append(' ')
    return ''.join(cleaned)


def xml_attr(key, value):
    """Format an XML attribute with proper escaping."""
    if value is None:
        return ''
    # Escape & < > " in attribute values
    v = str(value).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')
    return f' {key}="{v}"'


def xml_tag(name, attrs=None, content=None, self_closing=True):
    """Build an XML element string.
    attrs is a dict of attributes.
    content is optional text content (only for non-self-closing).
    If self_closing is False, creates open/close tags.
    """
    attr_str = ''
    if attrs:
        for k, v in attrs.items():
            if v is not None:
                attr_str += xml_attr(k, v)
    
    if self_closing:
        return f'<{name}{attr_str}/>'
    else:
        c = str(content) if content is not None else ''
        return f'<{name}{attr_str}>{c}</{name}>'


# ==============================================================================
# IDML Generator
# ==============================================================================

class IDMLGenerator:
    def __init__(self, parser, output_path):
        self.parser = parser
        self.output_path = output_path
        self.out_dir = os.path.dirname(output_path) or '.'
        self.build_dir = os.path.join(self.out_dir, '_idml')
        self.links_dir = os.path.join(self.build_dir, 'Links')
        
        # IDs
        self.doc_id = 'd'
        self.story_id = 's1'
        self.spread_id = 'sp1'
        self.page_id = 'pg1'
        self.master_spread_id = 'mp1'
        self.master_page_id = 'mp1p'
        self.layer_id = 'l1'
        self.tf_id = 'tf1'
        
        # Image IDs
        num_images = len(getattr(parser, 'images', []))
        self.img_ids = []
        for i in range(num_images):
            self.img_ids.append(f'img{i}')
        
        # Style group IDs
        self.rpg_id = 'rpg1'
        self.rcg_id = 'rcg1'

    def generate(self):
        os.makedirs(self.links_dir, exist_ok=True)
        os.makedirs(self.build_dir + '/META-INF', exist_ok=True)
        os.makedirs(self.build_dir + '/Resources', exist_ok=True)
        os.makedirs(self.build_dir + '/Spreads', exist_ok=True)
        os.makedirs(self.build_dir + '/Stories', exist_ok=True)
        os.makedirs(self.build_dir + '/MasterSpreads', exist_ok=True)

        # Extract images
        print("\n[2/6] Extracting images...")
        parser = self.parser
        zf = parser._ensure_open()
        try:
            bitmap = zf.read('content/data/Bitmaps.dat')
        except KeyError:
            print("  Warning: Bitmaps.dat not found, skipping image extraction")
            bitmap = b''
        for img in parser.images:
            p = parser.extract_image(bitmap, img, self.links_dir)
            if p:
                img['link_path'] = p
                img['link_name'] = os.path.basename(p)

        # Generate IDML files
        print("\n[3/6] Generating IDML...")
        self._mimetype()
        self._container()
        self._metadata()
        self._designmap()
        self._stories()
        self._spread()
        self._master_spread()
        self._resources()

        # Package
        print("\n[4/6] Packaging...")
        self._package()
        shutil.rmtree(self.build_dir, ignore_errors=True)
        print(f"\n✓ {self.output_path}  ({os.path.getsize(self.output_path)/1024:.0f} KB)")
        print(f"  {self.links_dir}/  ({len(self.parser.images)} images)")

    def xml_decl(self):
        return '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'

    def pkg_wrap(self, tag, inner, dom_version=None):
        """Wrap inner XML content in an idPkg:XXX element."""
        dv = dom_version or DOM_VERSION
        return (f'{self.xml_decl()}\n'
                f'<idPkg:{tag} xmlns:idPkg="{PKG_NS}" DOMVersion="{dv}">\n'
                f'{inner}\n'
                f'</idPkg:{tag}>\n')

    def _mimetype(self):
        with open(os.path.join(self.build_dir, 'mimetype'), 'w') as f:
            f.write('application/vnd.adobe.indesign-idml-package')

    def _container(self):
        content = (
            f'{self.xml_decl()}\n'
            f'<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">\n'
            f'  <rootfiles>\n'
            f'    <rootfile full-path="designmap.xml" media-type="text/xml"/>\n'
            f'  </rootfiles>\n'
            f'</container>\n'
        )
        write_xml(os.path.join(self.build_dir, 'META-INF/container.xml'), content)

    def _metadata(self):
        content = (
            f'{self.xml_decl()}\n'
            f'<x:xmpmeta xmlns:x="adobe:ns:meta/" x:xmptk="IDML Generator">\n'
            f'  <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">\n'
            f'    <rdf:Description rdf:about="" xmlns:dc="http://purl.org/dc/elements/1.1/">\n'
            f'      <dc:format>application/vnd.adobe.indesign-idml-package</dc:format>\n'
            f'    </rdf:Description>\n'
            f'  </rdf:RDF>\n'
            f'</x:xmpmeta>\n'
        )
        write_xml(os.path.join(self.build_dir, 'META-INF/metadata.xml'), content)

    def _designmap(self):
        pw = self.parser.page_info['width_pt']
        ph = self.parser.page_info['height_pt']
        content = (
            f'{self.xml_decl()}\n'
            f'<?aid style="50" type="document" readerVersion="6.0" featureSet="257" product="{DOM_VERSION}"?>\n'
            f'<Document xmlns:idPkg="{PKG_NS}" DOMVersion="{DOM_VERSION}" Self="{self.doc_id}" '
            f'StoryList="{self.story_id}" '
            f'Name="{os.path.basename(self.parser.cdr_path).replace(".cdr", "")}" '
            f'ZeroPoint="0 0" ActiveLayer="{self.layer_id}">\n'
            f'  <idPkg:Styles src="Resources/Styles.xml"/>\n'
            f'  <idPkg:Preferences src="Resources/Preferences.xml"/>\n'
            f'  <idPkg:Graphic src="Resources/Graphic.xml"/>\n'
            f'  <DocumentPreference Self="{self.doc_id}/DocumentPreference" '
            f'PageWidth="{pw}" PageHeight="{ph}" FacingPages="false" '
            f'PagesPerDocument="1" PageOrientation="Portrait"/>\n'
            f'  <Language Self="Language/$ID/English: USA" Name="$ID/English: USA" '
            f'SingleQuotes="\u2018\u2019" DoubleQuotes="\u201c\u201d" '
            f'PrimaryLanguageName="$ID/English" SublanguageName="$ID/USA" '
            f'Id="269" HyphenationVendor="Hunspell" SpellingVendor="Hunspell"/>\n'
            f'  <NumberingList Self="NumberingList/$ID/[Default]" Name="$ID/[Default]" '
            f'ContinueNumbersAcrossStories="false" ContinueNumbersAcrossDocuments="false"/>\n'
            f'  <NamedGrid Self="NamedGrid/$ID/[Page Grid]" Name="$ID/[Page Grid]"/>\n'
            f'</Document>\n'
        )
        write_xml(os.path.join(self.build_dir, 'designmap.xml'), content)

    def _stories(self):
        # Build story content - all text in one ParagraphStyleRange
        # Each text stream becomes a paragraph with multiple lines
        para_content = ''
        first_stream = True
        for runs in self.parser.text_content:
            if not first_stream:
                para_content += '\n        <Br/>\n'
            first_stream = False
            first_run = True
            for run in runs:
                text = run['text'].strip()
                if not text:
                    continue
                safe_text = escape_xml(text)
                if not first_run:
                    para_content += '\n        <Br/>\n'
                first_run = False
                para_content += f'        <Content>{safe_text}</Content>\n'

        if not para_content:
            para_content = '        <Content> </Content>\n'

        story_inner = (
            f'  <Story Self="{self.story_id}" AppliedTOCStyle="n" UserText="true" '
            f'IsEndnoteStory="false" TrackChanges="false" StoryTitle="$ID/" AppliedNamedGrid="n">\n'
            f'    <StoryPreference OpticalMarginAlignment="false" OpticalMarginSize="12" '
            f'FrameType="TextFrameType" StoryOrientation="Horizontal" '
            f'StoryDirection="LeftToRightDirection"/>\n'
            f'    <InCopyExportOption IncludeGraphicProxies="true" IncludeAllResources="false"/>\n'
            f'    <ParagraphStyleRange AppliedParagraphStyle="ParagraphStyle/$ID/NormalParagraphStyle">\n'
            f'      <CharacterStyleRange AppliedCharacterStyle="CharacterStyle/$ID/[No character style]" PointSize="12">\n'
            f'{para_content}'
            f'      </CharacterStyleRange>\n'
            f'    </ParagraphStyleRange>\n'
            f'  </Story>\n'
        )
        content = self.pkg_wrap('Story', story_inner)
        write_xml(os.path.join(self.build_dir, f'Stories/Story_{self.story_id}.xml'), content)

    def _spread(self):
        pw = self.parser.page_info['width_pt']
        ph = self.parser.page_info['height_pt']
        
        # Build text frames
        # Position text frame with 36pt margins (0.5 inch)
        y = 36.0
        margin_left = 36.0
        text_area_width = pw - 2 * margin_left
        num_text_streams = len(self.parser.text_content)
        
        frames = ''
        # Single large text frame that fills most of the page (with margins)
        frames += (
            f'      <TextFrame Self="tf0" ParentStory="{self.story_id}" '
            f'PreviousTextFrame="n" NextTextFrame="n" ContentType="TextType" '
            f'ItemTransform="1 0 0 1 {margin_left} 36" '  # Position at (margin_left, 36)
            f'GeometricBounds="0 0 {ph - 72} {text_area_width}"/>\n'  # [y1, x1, y2, x2] - from top-left: 0,0 to (ph-72, text_area_width)
        )
        
        # Build image rectangles
        for img in self.parser.images:
            # Ensure coordinates are within page boundaries
            x = max(0, img['x'])
            yy = max(0, img['y'])
            # Limit image size to remaining space within margins
            iw = min(img['width'], pw - x - margin_left)
            ih = min(img['height'], ph - yy - margin_left)
            # Convert to InDesign's geometric bounds format: [y1, x1, y2, x2]
            yy_r = round(max(0, yy), 2)
            x_r = round(x, 2)
            iw_r = round(min(iw, pw - x_r), 2)
            ih_r = round(min(ih, ph - yy_r), 2)
            
            if 'link_name' in img and img['link_name']:
                frames += (
                    f'      <Rectangle Self="r{img["index"]}" '
                    f'Name="{img["name"].replace(".jpeg", "")}" '
                    f'GeometricBounds="{yy_r} {x_r} {yy_r+ih_r} {x_r+iw_r}" '  # [y1, x1, y2, x2]
                    f'ContentType="GraphicType" '
                    f'ItemTransform="1 0 0 1 {x_r} {yy_r}">\n'  # Position at (x_r, yy_r)
                    f'        <Image Self="i{img["index"]}" '
                    f'ItemLink="link:{img["link_name"]}"/>\n'
                    f'      </Rectangle>\n'
                )

        spread_inner = (
            f'  <Spread Self="{self.spread_id}" FlattenerOverride="Default" '
            f'AllowPageShuffle="true" ItemTransform="1 0 0 1 0 0" '
            f'ShowMasterItems="true" PageCount="1" BindingDirection="LeftToRight">\n'
            f'    <SpreadPreference PageTransitionType="NotSet" '
            f'PageTransitionDuration="3" PageTransitionDirection="NotSet"/>\n'
            f'    <Page Self="{self.page_id}" AppliedAlternateLayout="n" LayoutRule="Off" '
            f'SnapshotBlendingMode="IgnoreLayoutSnapshots" OptionalPage="false" '
            f'GeometricBounds="0 0 {ph} {pw}" ItemTransform="1 0 0 1 0 0" '  # Identity transform
            f'Name="1" AppliedTrapPreset="TrapPreset/$ID/kDefaultTrapStyleName" '
            f'OverrideList="" AppliedMaster="{self.master_page_id}" '
            f'MasterPageTransform="1 0 0 1 0 0" TabOrder="">\n'
            f'      <MarginPreference ColumnCount="1" ColumnGutter="12" '
            f'Top="36" Bottom="36" Left="36" Right="36" '  # 0.5 inch margins
            f'ColumnDirection="Horizontal" ColumnsPositions="0 {pw}"/>\n'
            f'{frames}'
            f'    </Page>\n'
            f'  </Spread>\n'
        )
        content = self.pkg_wrap('Spread', spread_inner)
        write_xml(os.path.join(self.build_dir, f'Spreads/Spread_{self.spread_id}.xml'), content)

    def _master_spread(self):
        pw = self.parser.page_info['width_pt']
        ph = self.parser.page_info['height_pt']
        inner = (
            f'  <MasterSpread Self="{self.master_spread_id}" '
            f'ItemTransform="1 0 0 1 0 0" OverriddenPageItemProps="" '
            f'Name="A-Master" NamePrefix="A" BaseName="Master" '
            f'ShowMasterItems="true" PageCount="1" PrimaryTextFrame="n">\n'
            f'    <Page Self="{self.master_page_id}" AppliedAlternateLayout="n" '
            f'LayoutRule="Off" SnapshotBlendingMode="IgnoreLayoutSnapshots" '
            f'OptionalPage="false" GeometricBounds="0 0 {ph} {pw}" '
            f'ItemTransform="1 0 0 1 0 0" Name="A" '
            f'AppliedTrapPreset="TrapPreset/$ID/kDefaultTrapStyleName" '
            f'OverrideList="" AppliedMaster="n" '
            f'MasterPageTransform="1 0 0 1 0 0" TabOrder="">\n'
            f'      <MarginPreference ColumnCount="1" ColumnGutter="12" '
            f'Top="0" Bottom="0" Left="0" Right="0" '
            f'ColumnDirection="Horizontal" ColumnsPositions="0 {pw}"/>\n'
            f'    </Page>\n'
            f'  </MasterSpread>\n'
        )
        content = self.pkg_wrap('MasterSpread', inner)
        write_xml(os.path.join(self.build_dir, f'MasterSpreads/MasterSpread_{self.master_spread_id}.xml'), content)

    def _resources(self):
        # Styles.xml - wraps in idPkg:Styles
        styles = (
            f'  <RootParagraphStyleGroup Self="{self.rpg_id}">\n'
            f'    <ParagraphStyle Self="ParagraphStyle/$ID/[No paragraph style]" '
            f'Name="$ID/[No paragraph style]"/>\n'
            f'    <ParagraphStyle Self="ParagraphStyle/$ID/NormalParagraphStyle" '
            f'Name="NormalParagraphStyle" '
            f'BasedOn="ParagraphStyle/$ID/[No paragraph style]"/>\n'
            f'  </RootParagraphStyleGroup>\n'
            f'  <RootCharacterStyleGroup Self="{self.rcg_id}">\n'
            f'    <CharacterStyle Self="CharacterStyle/$ID/[No character style]" '
            f'Name="$ID/[No character style]"/>\n'
            f'  </RootCharacterStyleGroup>\n'
        )
        write_xml(os.path.join(self.build_dir, 'Resources/Styles.xml'), self.pkg_wrap('Styles', styles))

        # Preferences.xml
        pw = self.parser.page_info['width_pt']
        ph = self.parser.page_info['height_pt']
        prefs = (
            f'  <DocumentPreference Self="{self.doc_id}/DocumentPreference" '
            f'PageWidth="{pw}" PageHeight="{ph}" FacingPages="false" '
            f'PagesPerDocument="1" PageOrientation="Portrait"/>\n'
            f'  <DictionaryPreference Self="{self.doc_id}/DictionaryPreference"/>\n'
        )
        write_xml(os.path.join(self.build_dir, 'Resources/Preferences.xml'), self.pkg_wrap('Preferences', prefs))

        # Fonts.xml (empty but required)
        fonts = '  <!-- No embedded fonts -->\n'
        write_xml(os.path.join(self.build_dir, 'Resources/Fonts.xml'), self.pkg_wrap('Fonts', fonts))

        # Graphic.xml - color definitions
        self._graphic()

    def _graphic(self):
        color_id = 0
        colors_xml = ''
        for c in self.parser.colors:
            self_id = f'Color/u{color_id:x}'
            color_id += 1
            space = c['space']
            values = ' '.join(str(v) for v in c['values'])
            name = escape_xml(c['name'])
            colors_xml += (
                f'  <Color Self="{self_id}" Model="Process" Space="{space}" '
                f'ColorValue="{values}" ColorOverride="Normal" '
                f'AlternateSpace="NoAlternateColor" AlternateColorValue="" '
                f'Name="{name}" ColorEditable="true" ColorRemovable="true" '
                f'Visible="true" SwatchCreatorID="7937" SwatchColorGroupReference="n"/>\n'
            )
        standard_colors = (
            '  <Color Self="Color/Black" Model="Process" Space="CMYK" ColorValue="0 0 0 100" '
            'ColorOverride="Specialblack" AlternateSpace="NoAlternateColor" AlternateColorValue="" '
            'Name="Black" ColorEditable="false" ColorRemovable="false" Visible="true" '
            'SwatchCreatorID="7937" SwatchColorGroupReference="n"/>\n'
            '  <Color Self="Color/Paper" Model="Process" Space="CMYK" ColorValue="0 0 0 0" '
            'ColorOverride="Specialpaper" AlternateSpace="NoAlternateColor" AlternateColorValue="" '
            'Name="Paper" ColorEditable="true" ColorRemovable="false" Visible="true" '
            'SwatchCreatorID="7937" SwatchColorGroupReference="n"/>\n'
            '  <Color Self="Color/Registration" Model="Registration" Space="CMYK" '
            'ColorValue="100 100 100 100" ColorOverride="Specialregistration" '
            'AlternateSpace="NoAlternateColor" AlternateColorValue="" '
            'Name="Registration" ColorEditable="false" ColorRemovable="false" Visible="true" '
            'SwatchCreatorID="7937" SwatchColorGroupReference="n"/>\n'
        )
        inks = (
            '  <Ink Self="Ink/$ID/Process Cyan" Name="$ID/Process Cyan" Angle="75" '
            'ConvertToProcess="false" Frequency="70" NeutralDensity="0.61" '
            'PrintInk="true" TrapOrder="1" InkType="Normal"/>\n'
            '  <Ink Self="Ink/$ID/Process Magenta" Name="$ID/Process Magenta" Angle="15" '
            'ConvertToProcess="false" Frequency="70" NeutralDensity="0.76" '
            'PrintInk="true" TrapOrder="2" InkType="Normal"/>\n'
            '  <Ink Self="Ink/$ID/Process Yellow" Name="$ID/Process Yellow" Angle="0" '
            'ConvertToProcess="false" Frequency="70" NeutralDensity="0.16" '
            'PrintInk="true" TrapOrder="3" InkType="Normal"/>\n'
            '  <Ink Self="Ink/$ID/Process Black" Name="$ID/Process Black" Angle="45" '
            'ConvertToProcess="false" Frequency="70" NeutralDensity="1.7" '
            'PrintInk="true" TrapOrder="4" InkType="Normal"/>\n'
        )
        swatch = (
            '  <Swatch Self="Swatch/None" Name="None" ColorEditable="false" '
            'ColorRemovable="false" Visible="true" SwatchCreatorID="7937" '
            'SwatchColorGroupReference="n"/>\n'
        )
        stroke_styles = ''
        for style in ['Solid', 'Dashed', 'Dotted', 'Thick', 'ThickThin', 'ThinThick',
                       'Triple', 'Left Slant Hash', 'Right Slant Hash', 'Straight Hash']:
            stroke_styles += (
                f'  <StrokeStyle Self="StrokeStyle/$ID/{style}" Name="$ID/{style}"/>\n'
            )
        graphic_inner = standard_colors + colors_xml + inks + swatch + stroke_styles
        write_xml(os.path.join(self.build_dir, 'Resources/Graphic.xml'),
                  self.pkg_wrap('Graphic', graphic_inner))

    def _package(self):
        with zipfile.ZipFile(self.output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            # mimetype first, stored
            zf.writestr('mimetype', 'application/vnd.adobe.indesign-idml-package',
                       compress_type=zipfile.ZIP_STORED)
            for dirpath, _, filenames in os.walk(self.build_dir):
                for fn in filenames:
                    if fn == 'mimetype' or fn == '.DS_Store':
                        continue
                    fp = os.path.join(dirpath, fn)
                    zf.write(fp, os.path.relpath(fp, self.build_dir))


# ==============================================================================
# Main
# ==============================================================================

def main():
    if len(sys.argv) < 2:
        print("Usage: python idml_generator.py <input.cdr> [output.idml]")
        sys.exit(1)
    cdr = sys.argv[1]
    if not os.path.exists(cdr):
        print(f"Not found: {cdr}")
        sys.exit(1)
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.splitext(cdr)[0] + '.idml'
    print(f"CDR: {cdr}\nIDML: {out}")
    print("\n[1/6] Parsing CDR...")
    p = CDRParser(cdr)
    p.parse()
    print(f"  Images: {len(p.images)}  Text streams: {len(p.text_content)}")
    IDMLGenerator(p, out).generate()
    p.close()

if __name__ == '__main__':
    main()