"""Mechanical derivatives of the approved logo. Requires Pillow; never edits master."""
import argparse
import hashlib
from pathlib import Path
from PIL import Image

MASTER_SHA256 = 'da9c46be34b8a14d5fb262d3ae1bb18c4ff4b50badd8541837d2d8128d1e1fbb'


def build(directory):
    master = directory / 'sedrava-logo-primary.png'
    if hashlib.sha256(master.read_bytes()).hexdigest() != MASTER_SHA256:
        raise SystemExit('Master checksum differs from approved source; refusing to regenerate.')
    with Image.open(master) as image:
        for size in (32, 48, 180, 192, 512):
            logo = image.copy()
            logo.thumbnail((size, size), Image.Resampling.LANCZOS)
            canvas = Image.new('RGBA', (size, size))
            canvas.alpha_composite(logo, ((size-logo.width)//2, (size-logo.height)//2))
            canvas.save(directory / f'sedrava-logo-{size}.png')
        with Image.open(directory / 'sedrava-logo-512.png') as icon:
            icon.save(directory / 'favicon.ico', sizes=[(16,16), (32,32), (48,48)])
        logo = image.copy()
        logo.thumbnail((540, 540), Image.Resampling.LANCZOS)
        canvas = Image.new('RGBA', (1200, 630), '#151122')
        canvas.alpha_composite(logo, ((1200-logo.width)//2, (630-logo.height)//2))
        canvas.convert('RGB').save(directory / 'sedrava-og.png')
    files = sorted(p for p in directory.iterdir() if p.suffix in ('.png', '.ico'))
    (directory / 'SHA256SUMS').write_text(''.join(
        f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n' for p in files))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path, help='Directory containing approved master PNG')
    build(parser.parse_args().directory)
