"""One .sdr entry point; explicit document modes share syntax and diagnostics."""
from sedrava_syntax import document_kind


def parse_document(source):
    if document_kind(source) == 'site':
        from sedrava_site import parse_site
        return parse_site(source)
    if document_kind(source) == 'webapp':
        from sedrava_webapp import parse_webapp
        return parse_webapp(source)
    from sedrava_core import parse
    return parse(source)
