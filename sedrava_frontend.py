"""One .sdr entry point; explicit document modes share syntax and diagnostics."""
from sedrava_syntax import document_kind


def parse_document(source, source_path=None):
    from sedrava_modules import expand
    if document_kind(source) in ("site", "webapp"):
        source, _, origins = expand(source, source_path, with_origins=True)
        from sedrava_source_map import source_error
        try:
            if document_kind(source) == 'site':
                from sedrava_site import parse_site
                return parse_site(source)
            from sedrava_webapp import parse_webapp
            return parse_webapp(source)
        except ValueError as exc:
            raise source_error(exc, origins) from exc
    from sedrava_core import parse
    return parse(source)
