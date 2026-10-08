# PageMaker P65/PM5 & CorelDRAW CDR File Format Specification

## Overview

This project handles three legacy document formats:
- **P65 files**: Adobe PageMaker 6.5 documents (OLE/CFB container with proprietary binary content)
- **PM5 files**: Adobe PageMaker 5.0 documents (flat binary with record-based structure)
- **CDR files**: CorelDRAW documents (ZIP archive with proprietary XML/binary content, v14+)
- **PRV files**: Extensis PagePreview files (4bpp indexed-color bitmaps for PageMaker documents)

The converter produces:
- **PDF**: From P65/PM5 (via text extraction), and CDR (via Inkscape + bitmap overlay composite)
- **JPG**: From PRV files (preview bitmap extraction)

Output files preserve the original extension:
- `sample2.cdr` → `output/sample2.cdr.pdf`
- `94INVITE.PM5` → `output/94INVITE.PM5.pdf`
- `96INVITE.PRV` → `output/96INVITE.PRV.jpg`

---

# Part 1: PageMaker P65 Format

## File Structure

### OLE Container
- **Format**: Microsoft Compound File Binary (CFBF/OLE)
- **Streams**:
  - `/PageMaker` - Main document data
  - `/ObjectPool` - Embedded images and objects (may be empty)

### PageMaker Stream Structure

#### Header (first ~200 bytes)
| Offset | Size | Description |
|--------|------|-------------|
| 0x00 | 6 | Unknown/reserved |
| 0x06 | 2 | Magic: `FF 99` (PC) or `99 FF` (Mac) |
| 0x08 | 4 | Document ID |
| 0x0C | 4 | Unknown |
| 0x10 | 2 | Unknown |
| 0x12 | 4 | Page width (in points, big-endian) |
| 0x16 | 4 | Page height (in points, big-endian) |
| 0x1E | 2 | Unknown |
| 0x20 | 2 | Unknown |
| 0x3E | 4 | Unknown |
| 0x42 | 4 | Unknown |
| 0x60 | 4 | Unknown |
| 0x64 | 4 | Unknown |
| 0x70 | 4 | Unknown |
| 0x96-0x98 | 3 | "MP" marker |
| 0x9E-0xA1 | 4 | Version: `2 06` = version 6.5 (big-endian uint16) |
| 0x110 | ... | Various document properties |

#### Document Content
- Text strings are stored as plain ASCII throughout the file
- Font names embedded as ASCII strings (e.g., "Times New Roman", "Optima")
- Page markers like "PageMaker 5.0 RGB" appear at various offsets

### Strings Extraction
The document contains readable ASCII strings including:
- Document titles and headers
- Font names (Times New Roman, Optima, Curlz MT, etc.)
- Style names (Body text, Headline, Normal)
- Color names (Registration, Paper, Black, Green, Blue, etc.)
- Actual document content (schedules, text)

---

# Part 2: PageMaker PM5 Format

## File Structure

### Flat Binary Format
PM5 files are **not** OLE containers. They are flat binary files with a record-based structure.

#### Header
| Offset | Size | Description |
|--------|------|-------------|
| 0x00 | 6 | Unknown/reserved |
| 0x06 | 2 | Magic: `FF 99` (PC) or `99 FF` (Mac) |
| 0x66 | 2 | "MP" marker |

#### Key Differences from P65
- **No OLE container** - Raw binary data at file start
- **Big-endian** - Same endianness detection as P65 (0xFF99 at offset 0x06)
- **Record-based** - Data organized in typed records
- **Page dimensions** - Stored at different offsets than P65 (documented offsets don't contain standard sizes)

### String Extraction
Uses the same string-scanning approach as P65:
- Font names, style names, color names
- Document content strings
- Shared `PageMakerBaseParser` base class

---

# Part 3: Extensis PagePreview (PRV) Format

## File Structure

PRV files are created by the Extensis PagePreview utility for PageMaker.
They contain a low-resolution preview bitmap of the document.

### Header Layout
| Offset | Size | Description |
|--------|------|-------------|
| 0x00 | 24 | Magic: "Extensis PagePreview File" |
| 0x128 | ... | File metadata |
| 0x12A | 2 | Page width (points, little-endian uint16) |
| 0x12C | 2 | Page height (points, little-endian uint16) |
| 0x14C | 40 | BITMAPINFOHEADER |
| 0x180 | 64 | 16-color EGA palette (BGRx format) |
| 0x1C0 | ... | 4bpp pixel data (bottom-to-top scanlines) |

### Bitmap Format
- **Color depth**: 4 bits per pixel (16 colors)
- **Palette**: Standard EGA 16-color palette
- **Orientation**: Bottom-to-top scanlines (requires vertical flip)
- **Row alignment**: 4-byte aligned

### Path Reference
The header contains a null-terminated path to the original PM5 file:
```
F:\GOLF\TOURNIES\INVITATN\96INVITE.PM5
```

---

# Part 4: CorelDRAW CDR Format (v14+)

## File Structure

CDR files from version 14+ are **ZIP archives** containing XML metadata, binary content data, and embedded resources.

### ZIP Entry Layout
| Entry | Description |
|-------|-------------|
| `mimetype` | Contains `image/x-cdr` or `application/x-cdr` |
| `META-INF/metadata.xml` | Document metadata including bounding box, page dimensions, Creator info |
| `META-INF/textinfo.xml` | Text content with positioning, fonts, and text run formatting |
| `META-INF/content.xml` | Object hierarchy: shapes, groups, linked files, effects |
| `META-INF/links.xml` | External file references (images, embedded objects) |
| `META-INF/container.xml` | OCF container descriptor |
| `content/data/data1.dat` | Binary stream with image positions, object properties |
| `content/data/Bitmaps.dat` | Raw bitmap pixel data for embedded raster images |
| `content/data/page1.dat` | Page layout data (may be very large) |
| `content/data/masterPage.dat` | Master page template data |
| `content/dataFileList.dat` | List of data files (e.g., "Bitmaps.dat\ndata1.dat\n...") |
| `content/root.dat` | Document root object data |
| `font/fontTable.dat` | Embedded font table |
| `color/color.xml` | Color palette definitions |
| `color/docPalette.xml` | Document-specific color palette |
| `color/profiles/rgb/*.icm` | RGB ICC color profiles |
| `color/profiles/cmyk/*.icc` | CMYK ICC color profiles |
| `color/profiles/grayscale/*.icc` | Grayscale ICC color profiles |
| `styles/document.cdss` | Character and paragraph style definitions |
| `previews/thumbnail.png` | Thumbnail preview image |
| `previews/page1.png` | Page 1 preview image |
| `embed/embeddingN` | Embedded OLE objects or additional resources |

### META-INF/metadata.xml Structure
Contains document-level metadata including:
- **Document bounding box** (`rect:left`, `rect:top`, `rect:right`, `rect:bottom`)
- Page dimensions and orientation
- Creator application and version
- Color management settings

Example coordinate system:
```xml
<rect:left>-1249373</rect:left>
<rect:top>2052918</rect:top>
<rect:right>1152730</rect:right>
<rect:bottom>-2056668</rect:bottom>
```
These are in CDR's internal coordinate system. Conversion to points:
- Page width in pt = letter (612) by default; page size stored separately
- Coordinates are normalized to [0,1] range via clip rect dimensions

### META-INF/textinfo.xml Structure
Contains all text streams with character-level formatting:
```xml
<TextStream name="Text 1">
  <TextRun font="Arial" size="12" break="word">Hello </TextRun>
  <TextRun font="Arial" size="12" bold="true">World</TextRun>
</TextStream>
```
Each `<TextRun>` element may include:
- `font` - Font family name
- `size` - Font size in points
- `bold`, `italic`, `underline` - Boolean formatting flags
- `break` - Line break behavior (`none`, `word`, `char`)
- `color` - Color reference

### META-INF/content.xml Structure
Describes the document object hierarchy:
- Shapes (Rectangle, Ellipse, Polygon)
- Groups of objects
- Text objects referencing textinfo.xml streams
- Bitmap references with filenames in `fileName` attributes
- Linked images with path information
- Effects and transformations

### data1.dat - Binary Format
Proprietary binary format containing:
- **Image placement data**: Coordinates for each embedded bitmap at known offsets before image filenames
  - 4 signed 32-bit integers (little-endian) at offset 0x60 before filename in UTF-16LE encoding
  - These are the bounding box coordinates in CDR's internal coordinate system
- Object properties and hierarchy data

### Bitmaps.dat - Binary Format
Raw bitmap data with a header table structure:
- **Image table entries**: Found by searching for `UI\x00\x00` marker bytes
  - Each marker is preceded by 8 bytes: 4-byte count, 4-byte version
  - Header at marker offset: 0x70 bytes containing metadata at offsets 0x3C (width) and 0x40 (height)
- **Pixel data**: Follows immediately after the 0x70-byte header
  - 24-bit BGR pixels (3 bytes per pixel)
  - Row stride is 4-byte aligned
  - Scanlines are stored bottom-to-top (require vertical flip for display)

### Font Table (font/fontTable.dat)
Binary table of fonts used in the document:
- Font family names
- Font style variants (Regular, Bold, Italic, BoldItalic)
- Character encoding information

---

# Usage

## Installation

```bash
# Install Python dependencies
pip install -r requirements.txt

# For CDR to PDF conversion, install Inkscape:
# macOS: brew install --cask inkscape
# Linux: sudo apt install inkscape
# Windows: Download from https://inkscape.org
```

## Command Line

```bash
# Convert all files in current directory (CDR, P65, PM5, PRV) to PDF
python converter.py

# Convert specific file to PDF
python converter.py sample1.cdr
python converter.py sample1.p65
python converter.py 94INVITE.PM5

# Specify input directory and output directory
python converter.py ./input -o ./output

# Verbose output
python converter.py sample1.cdr --verbose
```

## Output

| Input Type | Output Format | Description |
|------------|---------------|-------------|
| `.cdr` | `.cdr.pdf` | Composite: Inkscape vectors + embedded bitmaps |
| `.p65` | `.p65.pdf` | Extracted text-only PDF (layout info lost) |
| `.pm5` | `.pm5.pdf` | Extracted text-only PDF (same pipeline as P65) |
| `.prv` | `.PRV.jpg` | Preview bitmap extraction (88x115 px, 16 colors) |

## Testing

```bash
# Run all tests
python -m unittest discover -p "test_*.py"

# Run individual test suites
python -m unittest test_p65_parser.py    # P65, PM5, and PRV tests
python -m unittest test_p65_pdf.py       # PDF generation tests
python -m unittest test_cdr_pdf.py       # CDR composite PDF tests
python -m unittest test_converter.py     # Converter tests
```

---

# Known Limitations

## PageMaker (P65)
1. **No public specification** - Format documented through reverse-engineering
2. **Text positioning** - Exact X/Y coordinates are in proprietary binary format
3. **Font mapping** - Proprietary font IDs need mapping to standard fonts
4. **Text flow** - Linked text chains have complex internal structure
5. **No multi-page support** - Multiple pages in a single P65 file are not handled
6. **Page dimensions unreliable** - The documented byte offsets for page width/height do not contain standard page sizes in all P65 files; falls back to Letter (612x792 pt)
7. **libpagemaker targets PM4/PM5, not PM6.5** - The libpagemaker project (https://github.com/umanwizard/libpagemaker) reverse-engineered PageMaker 4.0/5.0 files (.pmd), which use a record-based binary format with a Table of Contents. PageMaker 6.5 files (.p65) use a different binary structure within the OLE /PageMaker stream. The TOC offsets and record types from libpagemaker do not apply to P65. What does transfer: the endianness detection (0x99FF=LE, 0xFF99=BE at offset 0x06), the coordinate system (shape coords in 1/1440 inch, page dims in 1/720 inch), and general knowledge of how PMD files are structured for reference.

## CorelDRAW (CDR)
1. **Binary parsing is fragile** - Image format detection and bitmap extraction rely on version-specific byte patterns
2. **Vector graphics via Inkscape** - Vectors rendered by Inkscape CLI; quality depends on Inkscape's CDR support
3. **No table support** - Tables are not extracted as structured data
4. **No text formatting** - textinfo.xml only contains text content and break attributes; font, size, bold, italic, and color are stored in binary format and not extracted
5. **Image positions approximate** - When Bitmaps.dat fallback is used (no data1.dat coordinates), images are placed at full-page bounds rather than their actual positions
6. **CDR version compatibility** - Some newer CDR versions may not render vectors correctly in Inkscape; bitmaps are always extracted from the binary data

---

# Implementation Strategy

## Phase 1: Text Extraction (Achievable - P65)
- Extract all readable strings from `/PageMaker` stream
- Group strings by context (font names, style names, content)
- Preserve basic reading order by offset

## Phase 2: Basic Layout (Limited - Both)
- Attempt to identify page boundaries (P65: offset gaps; CDR: metadata bounding box)
- Estimate text blocks by analyzing string positions

## Phase 3: CDR Composite PDF Generation
- Use Inkscape CLI for vector rendering
- Extract embedded bitmaps from Bitmaps.dat with positions from data1.dat
- Create transparent overlay PDF with bitmaps
- Use pikepdf to merge overlay onto Inkscape base PDF

## Phase 4: PDF Generation (P65/PM5)
- Use extracted text to generate simple PDF with heuristic style classification

---

# Dependencies

- `olefile` - For parsing OLE compound files (P65)
- `reportlab` - For PDF generation (P65/PM5, bitmap overlay)
- `Pillow` - For image extraction (CDR bitmaps, PRV preview)
- `pikepdf` - For PDF compositing (CDR bitmap overlay)
- `Inkscape` - Required for CDR vector rendering

---

# References
- PRONOM: fmt/876 (PageMaker Document)
- File formats archive: http://fileformats.archiveteam.org/wiki/PageMaker
- Microsoft OLE format: MSDN Compound File Binary Format
- CorelDRAW CDR Format: Reverse-engineered; no public specification
- libpagemaker: https://github.com/umanwizard/libpagemaker - C++ library for PageMaker 4.0/5.0 files
