"""Shared .sdr source boundaries and indentation lines for app/site modes."""
MAX_SOURCE_CHARS = 100_000
MAX_BLOCK_DEPTH = 32


def source_lines(source, limit=MAX_SOURCE_CHARS):
    if len(source) > limit:
        raise ValueError('Source exceeds size limit')
    for number, raw in enumerate(source.split('\n'), 1):
        for offset, char in enumerate(raw):
            if 0xD800 <= ord(char) <= 0xDFFF:
                raise ValueError(f'Line {number}: column {offset + 1}: Source contains an unpaired surrogate')
        if '\t' in raw[:len(raw) - len(raw.lstrip())]:
            raise ValueError(f'Line {number}: tabs are not allowed in indentation')
    return [(len(raw) - len(raw.lstrip(' ')), raw.strip(), i)
            for i, raw in enumerate(source.split('\n'), 1)
            if raw.strip() and not raw.lstrip().startswith('#')]


def document_kind(source):
    lines = source_lines(source)
    if lines and lines[0][1].split()[0] in ('site', 'webapp', 'host'):
        return lines[0][1].split()[0]
    return 'app'
