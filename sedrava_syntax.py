"""Shared .sdr source boundaries and indentation lines for app/site modes."""
import keyword


def is_reserved_identifier(name):
    """Lexical reserved names, checked before any namespace/local lowering."""
    return name in ("true", "false") or keyword.iskeyword(name)


MAX_SOURCE_CHARS = 100_000
MAX_BLOCK_DEPTH = 32


def physical_lines(source, keepends=False):
    """LF/CRLF source lines; Unicode NEL/LS/PS remain literal scalar values."""
    parts=source.split('\n')
    lines=[]
    for index,part in enumerate(parts):
        terminated=index<len(parts)-1
        if not terminated and not part:break
        lines.append(part+('\n' if terminated else '') if keepends else part.removesuffix('\r'))
    return lines


def source_lines(source, limit=MAX_SOURCE_CHARS):
    if len(source) > limit:
        raise ValueError('Source exceeds size limit')
    for number, raw in enumerate(physical_lines(source), 1):
        for offset, char in enumerate(raw):
            if 0xD800 <= ord(char) <= 0xDFFF:
                raise ValueError(f'Line {number}: column {offset + 1}: Source contains an unpaired surrogate')
        if '\t' in raw[:len(raw) - len(raw.lstrip())]:
            raise ValueError(f'Line {number}: tabs are not allowed in indentation')
    return [(len(raw) - len(raw.lstrip(' ')), raw.strip(), i)
            for i, raw in enumerate(physical_lines(source), 1)
            if raw.strip() and not raw.lstrip().startswith('#')]


def document_kind(source):
    lines = source_lines(source)
    if lines and lines[0][1].split()[0] in ('site', 'webapp'):
        return lines[0][1].split()[0]
    return 'app'
