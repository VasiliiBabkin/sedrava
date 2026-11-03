"""Build legacy app examples; static sites have a separate target and artifact."""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sedrava_frontend import parse_document
from sedrava_site import Site
from sedrava_webapp import WebApp
from web_codegen import generate


def application_examples(root=ROOT):
    """Validate every example, then select applications with UI for app artifacts."""
    for path in sorted((root / 'examples').glob('*.sdr')):
        source = path.read_text(encoding='utf-8')
        document = parse_document(source)
        if not isinstance(document, (Site, WebApp)) and document.widgets:
            yield path, source


def main():
    output = ROOT / 'build/web'
    output.mkdir(parents=True, exist_ok=True)
    for path, source in application_examples():
        (output / (path.stem + '.html')).write_text(generate(source), encoding='utf-8')


if __name__ == '__main__':
    main()
