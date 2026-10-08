# PageMaker/CorelDRAW Converter - Usage Examples

## Basic Usage

Convert all supported files in current directory to PDF:
```bash
python converter.py
```

Convert all files in a specific directory:
```bash
python converter.py /path/to/files -o /path/to/output
```

Convert a single file:
```bash
python converter.py sample2.cdr
python converter.py 94INVITE.PM5
python converter.py 96INVITE.PRV
```

## Verbose Output

See detailed progress information:
```bash
python converter.py sample2.cdr --verbose
```

## IDML Generation

Convert CDR to Adobe InDesign IDML format:
```bash
python idml_generator.py sample2.cdr sample2.idml
```

The generated IDML package can be opened in Adobe InDesign CS6 or newer.

## File Naming Convention

Output files preserve the original extension with added format extension:
- `sample2.cdr` → `sample2.cdr.pdf`
- `94INVITE.PM5` → `94INVITE.PM5.pdf`
- `96INVITE.PRV` → `96INVITE.PRV.jpg`

## Requirements

- Python 3.x
- Required Python packages (see requirements.txt):
  - olefile
  - reportlab
  - Pillow
  - pikepdf
- Inkscape (required for CDR to PDF conversion)
  - macOS: `brew install --cask inkscape --cask`
  - Linux: `sudo apt install inkscape`
  - Windows: Download from https://inkscape.org

## Supported Formats

**Input:**
- PageMaker P65 (.p65, .pm6, .pmd)
- PageMaker PM5 (.pm5, .pmd)
- CorelDRAW CDR (.cdr) - version 14+
- Extensis PagePreview PRV (.prv)

**Output:**
- PDF (.pdf) for P65/PM5/CDR
- JPEG (.jpg) for PRV
- IDML (.idml) for CDR (via idml_generator.py)

## Notes

1. PageMaker to PDF conversion extracts text only - layout information is not preserved
2. CDR to PDF conversion uses Inkscape for vector graphics and extracts embedded bitmaps for overlay
3. PRV to JPEG extracts the preview bitmap (typically low-resolution)
4. CDR to IDML conversion creates an InDesign-compatible package with extracted text and images

For detailed format specifications, see SPEC.md