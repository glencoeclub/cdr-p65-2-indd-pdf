#!/usr/bin/env python3
"""Golden-render harness.

Converts every file in samples/, rasterizes the first page of each PDF,
and writes a manifest of content hashes. Later, `check` mode re-runs the
whole pipeline into a temp dir and diffs against the committed goldens —
so any conversion change is caught (or deliberately re-baselined).

Usage:
    python tools/golden.py render   # (re)build golden/ from current code
    python tools/golden.py check    # convert fresh, diff against golden/

Hashing strategy:
- PDFs: hash the RASTERIZED render, not the PDF bytes (reportlab embeds a
  creation timestamp, so PDF bytes differ every run).
- IDML: hash normalized zip content (entry name + bytes, sorted), ignoring
  zip timestamps.
- JPEG: hash bytes (deterministic for a fixed Pillow version).

NOTE: the goldens capture CURRENT behavior, bugs included. When a fix
deliberately changes output, re-render and commit with the fix.
"""

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "samples"
GOLDEN = ROOT / "golden"
MANIFEST = GOLDEN / "manifest.json"
DPI = 144

sys.path.insert(0, str(ROOT))


# ----------------------------------------------------------------------------
# Conversion
# ----------------------------------------------------------------------------

def convert_all(out_dir: Path) -> list:
    """Convert every sample into out_dir; return list of output file paths."""
    from pagemaker_parser import P65Parser, PM5Parser
    from p65_pdf import P65PDFGenerator
    from prv_extractor import extract_prv_preview

    out_dir.mkdir(parents=True, exist_ok=True)
    outputs = []

    for sample in sorted(SAMPLES.iterdir()):
        if sample.name.startswith('.'):
            continue
        ext = sample.suffix.lower()
        print(f"  {sample.name} ...", end=" ", flush=True)

        if ext == '.cdr':
            from cdr_pdf import convert_cdr_to_composite_pdf
            ok = convert_cdr_to_composite_pdf(
                str(sample), str(out_dir / f"{sample.name}.pdf"))
            # Also build the IDML alongside (CDR path today)
            from idml_generator import CDRParser, IDMLGenerator
            p = CDRParser(str(sample))
            p.parse()
            idml_path = out_dir / f"{sample.stem}.idml"
            IDMLGenerator(p, str(idml_path)).generate()
            p.close()
            outputs.append(out_dir / f"{sample.name}.pdf")
            outputs.append(idml_path)
        elif ext in ('.p65', '.pm6', '.pmd', '.pm5'):
            parser = PM5Parser(str(sample)) if ext in ('.pm5', '.pmd') else P65Parser(str(sample))
            if parser.parse():
                gen = P65PDFGenerator(parser)
                ok = gen.generate(str(out_dir / f"{sample.name}.pdf"))
                outputs.append(out_dir / f"{sample.name}.pdf")
            else:
                ok = False
        elif ext == '.prv':
            jpg = out_dir / f"{sample.name}.jpg"
            ok = extract_prv_preview(str(sample), str(jpg))
            outputs.append(jpg)
        else:
            print("skipped (unknown ext)")
            continue

        print("ok" if ok else "FAILED")
        if not ok:
            raise SystemExit(f"conversion failed for {sample.name}")

    return [p for p in outputs if p.exists()]


# ----------------------------------------------------------------------------
# Hashing
# ----------------------------------------------------------------------------

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def sha256_idml(path: Path) -> str:
    """Hash IDML zip content, ignoring zip metadata/timestamps."""
    h = hashlib.sha256()
    with zipfile.ZipFile(path) as zf:
        for name in sorted(zf.namelist()):
            h.update(name.encode('utf-8'))
            h.update(b'\0')
            h.update(zf.read(name))
            h.update(b'\0')
    return h.hexdigest()


def render_page1(pdf: Path, png: Path) -> None:
    """Rasterize first page of a PDF to PNG via ghostscript."""
    cmd = [
        'gs', '-dSAFER', '-dBATCH', '-dNOPAUSE', '-dFirstPage=1', '-dLastPage=1',
        '-sDEVICE=png16m', f'-r{DPI}',
        f'-sOutputFile={png}', str(pdf),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0 or not png.exists():
        raise RuntimeError(f"gs failed on {pdf}: {result.stderr[-500:]}")


def build_manifest(out_dir: Path) -> dict:
    manifest = {}
    for path in sorted(out_dir.iterdir()):
        if path.name.startswith('.') or path.is_dir():
            continue
        if path.suffix.lower() == '.pdf':
            png = out_dir / (path.name + '.page1.png')
            render_page1(path, png)
            manifest[path.name] = {
                'type': 'pdf',
                'render_sha256': sha256_file(png),
                'render': png.name,
            }
        elif path.suffix.lower() == '.idml':
            manifest[path.name] = {'type': 'idml', 'content_sha256': sha256_idml(path)}
        else:
            manifest[path.name] = {'type': path.suffix.lower().lstrip('.'), 'sha256': sha256_file(path)}
    return manifest


# ----------------------------------------------------------------------------
# Commands
# ----------------------------------------------------------------------------

def cmd_render() -> None:
    if GOLDEN.exists():
        shutil.rmtree(GOLDEN)
    GOLDEN.mkdir(parents=True)
    print("Converting samples ->", GOLDEN)
    convert_all(GOLDEN)
    print("Rasterizing + hashing ...")
    manifest = build_manifest(GOLDEN)
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True))
    print(f"\nGolden baseline written: {MANIFEST} ({len(manifest)} artifacts)")


def cmd_check() -> None:
    if not MANIFEST.exists():
        raise SystemExit("No golden manifest. Run: python tools/golden.py render")
    golden = json.loads(MANIFEST.read_text())

    with tempfile.TemporaryDirectory(prefix='golden_check_') as tmp:
        print("Converting samples ->", tmp)
        convert_all(Path(tmp))
        current = build_manifest(Path(tmp))

    diffs = []
    for name in sorted(set(golden) | set(current)):
        if name not in current:
            diffs.append(f"MISSING  {name}")
        elif name not in golden:
            diffs.append(f"NEW      {name}")
        elif golden[name] != current[name]:
            diffs.append(f"CHANGED  {name}")

    if diffs:
        print("\nGOLDEN CHECK FAILED — output differs from baseline:")
        for d in diffs:
            print(" ", d)
        print("\nIf the change is intended, re-baseline: python tools/golden.py render")
        raise SystemExit(1)
    print(f"\nGolden check PASSED ({len(current)} artifacts match baseline)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('command', choices=['render', 'check'])
    args = ap.parse_args()
    if args.command == 'render':
        cmd_render()
    else:
        cmd_check()


if __name__ == '__main__':
    main()
