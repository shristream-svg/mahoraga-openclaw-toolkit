"""Deterministic file/CSV/PDF CLI subset. No profile, chat, memory or provider access."""
import csv
import shutil
import argparse
import hashlib
import json
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
import pypdf

def json_err(msg: str) -> None:
    print(json.dumps({'error': msg}), file=sys.stderr)
    sys.exit(1)

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()

def cmd_copy_verified(args):
    src = Path(args.SOURCE)
    dst = Path(args.DEST)
    if not src.is_file():
        json_err(f'source not found: {src}')
    if dst.exists():
        json_err(f'destination already exists: {dst}')
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        json_err(str(e))
    try:
        with dst.open('xb') as target, src.open('rb') as source:
            shutil.copyfileobj(source, target)
        if sha256(src) != sha256(dst):
            json_err('copy hash mismatch')
    except OSError as e:
        json_err(str(e))
    print(json.dumps({'action': 'copy', 'source': str(src), 'dest': str(dst), 'sha256': sha256(dst)}))

def cmd_csv_total(args):
    inp = Path(args.INPUT)
    col = args.COLUMN
    out = Path(args.OUTPUT)
    if out.exists():
        json_err(f'output already exists: {out}')
    if not inp.is_file():
        json_err(f'input not found: {inp}')
    total = Decimal('0')
    rows = 0
    with inp.open(newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        if col not in (reader.fieldnames or []):
            json_err(f'column {col!r} not found')
        for row in reader:
            value = Decimal(row[col])
            if not value.is_finite():
                json_err('non-finite amount')
            total += value
            rows += 1
    result = {'action': 'csv_total', 'column': col, 'total': int(total) if total == total.to_integral_value() else float(total), 'totalExact': str(total), 'rows': rows}
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open('x', encoding='utf-8') as f:
        json.dump(result, f, allow_nan=False)
    if json.loads(out.read_text(encoding='utf-8')) != result:
        json_err('JSON readback mismatch')
    print(json.dumps(result, allow_nan=False))

def cmd_pdf_info(args):
    inp = Path(args.INPUT)
    if not inp.is_file():
        json_err(f'input not found: {inp}')
    try:
        reader = pypdf.PdfReader(str(inp))
        page_count = len(reader.pages)
        total_chars = 0
        for page in reader.pages:
            total_chars += len(page.extract_text() or '')
        print(json.dumps({'action': 'pdf_info', 'page_count': page_count, 'text_char_count': total_chars}))
    except Exception as e:
        json_err(str(e))

def cmd_pdf_merge(args):
    out = Path(args.OUTPUT)
    if out.exists():
        json_err(f'output already exists: {out}')
    writer = pypdf.PdfWriter()
    for path_str in args.INPUTS:
        p = Path(path_str)
        if not p.is_file():
            json_err(f'input not found: {p}')
        try:
            reader = pypdf.PdfReader(str(p))
            writer.append(str(p))
        except Exception as e:
            json_err(str(e))
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, 'xb') as f:
            writer.write(f)
    except OSError as e:
        json_err(str(e))
    try:
        reread = pypdf.PdfReader(str(out))
        if len(reread.pages) != len(writer.pages):
            json_err('page count mismatch after write')
    except Exception as e:
        json_err(str(e))
    print(json.dumps({'action': 'pdf_merge', 'output': str(out), 'page_count': len(writer.pages)}))

def cmd_pdf_text(args):
    inp = Path(args.INPUT)
    out = Path(args.OUTPUT)
    if out.exists():
        json_err(f'output already exists: {out}')
    if not inp.is_file():
        json_err(f'input not found: {inp}')
    try:
        reader = pypdf.PdfReader(str(inp))
        texts = []
        for page in reader.pages:
            t = page.extract_text()
            if t:
                texts.append(t)
        content = '\n'.join(texts)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open('x', encoding='utf-8') as f:
            f.write(content)
        print(json.dumps({'action': 'pdf_text', 'output': str(out), 'chars': len(content)}))
    except Exception as e:
        json_err(str(e))

def main():
    parser = argparse.ArgumentParser(description='CLI toolkit')
    sub = parser.add_subparsers(dest='command')
    p1 = sub.add_parser('copy-verified')
    p1.add_argument('SOURCE')
    p1.add_argument('DEST')
    p1.set_defaults(func=cmd_copy_verified)
    p2 = sub.add_parser('csv-total')
    p2.add_argument('INPUT')
    p2.add_argument('COLUMN')
    p2.add_argument('OUTPUT')
    p2.set_defaults(func=cmd_csv_total)
    p3 = sub.add_parser('pdf-info')
    p3.add_argument('INPUT')
    p3.set_defaults(func=cmd_pdf_info)
    p4 = sub.add_parser('pdf-merge')
    p4.add_argument('OUTPUT')
    p4.add_argument('INPUTS', nargs='+')
    p4.set_defaults(func=cmd_pdf_merge)
    p5 = sub.add_parser('pdf-text')
    p5.add_argument('INPUT')
    p5.add_argument('OUTPUT')
    p5.set_defaults(func=cmd_pdf_text)
    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)
    try:
        args.func(args)
    except SystemExit:
        raise
    except Exception as e:
        json_err(str(e))
if __name__ == '__main__':
    main()
