"""Deterministic offline lockfile for explicitly vendored local Sedrava packages.

No registry, dynamic plugins or remote dependency execution. This is a
bounded project verification facility, not a general package installer.
"""
from hashlib import sha256
from pathlib import Path
import json
import os
import re
import tempfile

_MANIFEST = 'sedrava.toml'
_LOCK = 'sedrava.lock'
_NAME = re.compile(r'[a-z][a-z0-9]*(?:[.-][a-z0-9]+)*\Z')
_VERSION = re.compile(r'(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\Z')
MAX_PACKAGES = 32
MAX_FILES = 256
MAX_BYTES = 8 * 1024 * 1024


def _toml():
    try:
        import tomllib
    except ImportError:  # Python 3.10
        try:
            import tomli as tomllib
        except ImportError as exc:
            raise ValueError('Python 3.10 package locking requires tomli; install sedrava[packages]') from exc
    return tomllib


def _checked_path(root, relative):
    if not isinstance(relative, str) or not relative or '\\' in relative or ':' in relative:
        raise ValueError('Invalid local package path')
    path = Path(relative)
    if path.is_absolute() or any(p in ('', '.', '..') for p in path.parts):
        raise ValueError('Local package path must not escape the project')
    if not path.parts or path.parts[0] != 'vendor' or len(path.parts) < 2:
        raise ValueError('Local packages must live inside vendor/')
    cur = root
    for part in path.parts:
        cur = cur / part
        if cur.is_symlink():
            raise ValueError('Package paths cannot contain symbolic links')
    candidate = (root / path).resolve()
    if not candidate.is_relative_to(root) or not candidate.is_dir():
        raise ValueError('Package directory is missing or outside project')
    return candidate


def _read_manifest(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 32768:
        raise ValueError('Package manifest missing, linked or too large')
    try:
        data = _toml().loads(path.read_text(encoding='utf-8'))
    except (UnicodeError, ValueError) as exc:
        raise ValueError(f'Invalid TOML manifest: {path}') from exc
    if set(data) != {'package'} and set(data) != {'package', 'dependencies'}:
        raise ValueError('Unknown manifest sections')
    pkg = data.get('package')
    if not isinstance(pkg, dict) or set(pkg) != {'name', 'version'}:
        raise ValueError('Expected [package] name and version')
    name, version = pkg['name'], pkg['version']
    if not isinstance(name, str) or not _NAME.fullmatch(name):
        raise ValueError('Invalid package name')
    if not isinstance(version, str) or not _VERSION.fullmatch(version):
        raise ValueError('Package version must be an exact three-part version')
    deps = data.get('dependencies', {})
    if not isinstance(deps, dict) or len(deps) > MAX_PACKAGES:
        raise ValueError('Invalid dependency map')
    for dep, spec in deps.items():
        if not isinstance(dep, str) or not _NAME.fullmatch(dep):
            raise ValueError('Invalid dependency name')
        if not isinstance(spec, dict) or set(spec) != {'path', 'version'}:
            raise ValueError('Dependency must declare exact path and version')
        if not isinstance(spec['version'], str) or not _VERSION.fullmatch(spec['version']):
            raise ValueError('Dependency version must be exact')
    return name, version, deps


def _files(folder):
    out, total = {}, 0
    for p in sorted(folder.rglob('*')):
        if p.is_symlink():
            raise ValueError('Symlinks inside packages are forbidden')
        if p.is_dir():
            continue
        if not p.is_file():
            raise ValueError('Unsupported package file type')
        rel = p.relative_to(folder).as_posix()
        if any(part.startswith('.') for part in p.relative_to(folder).parts):
            raise ValueError('Hidden files inside local package are forbidden')
        if len(out) >= MAX_FILES:
            raise ValueError('Too many files in local package')
        size = p.stat().st_size
        total += size
        if total > MAX_BYTES:
            raise ValueError('Local package exceeds resource budget')
        out[rel] = sha256(p.read_bytes()).hexdigest()
    return out


def snapshot(project):
    """Build a canonical deterministic lock representation of local packages."""
    root = Path(project).resolve()
    if not root.is_dir():
        raise ValueError('Project directory does not exist')
    manifest = root / _MANIFEST
    name, version, dependencies = _read_manifest(manifest)
    visited, active = {}, set()
    def load(dep, spec):
        path = _checked_path(root, spec['path'])
        relative = path.relative_to(root).as_posix()
        if dep in active:
            raise ValueError('Cyclic local package dependency: '+dep)
        if dep in visited:
            if visited[dep]['path'] != relative or visited[dep]['version'] != spec['version']:
                raise ValueError('Conflicting dependency version or path: '+dep)
            return
        if len(visited) >= MAX_PACKAGES:
            raise ValueError('Too many local dependencies')
        found, found_version, children = _read_manifest(path / _MANIFEST)
        if found != dep or found_version != spec['version']:
            raise ValueError('Package identity/version mismatch for '+dep)
        active.add(dep)
        files = _files(path)
        if _MANIFEST not in files:
            raise ValueError('Package source is missing its manifest')
        visited[dep] = dict(name=dep, version=found_version, path=relative,
                            files=files, dependencies=sorted(children))
        for child, child_spec in sorted(children.items()):
            load(child, child_spec)
        active.remove(dep)
    for dep, spec in sorted(dependencies.items()):
        load(dep, spec)
    if name in visited:
        raise ValueError('Root package identity conflicts with dependency')
    return dict(schema=1,
                root=dict(name=name, version=version,
                          manifest_sha256=sha256(manifest.read_bytes()).hexdigest(),
                          dependencies=sorted(dependencies)),
                packages=[visited[dep] for dep in sorted(visited)])


def _strict_json(data):
    def decode_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate key in lockfile')
            result[key] = value
        return result
    return json.loads(data, object_pairs_hook=decode_pairs,parse_float=lambda _: (_ for _ in ()).throw(ValueError('Integer lock schema required')),parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Invalid JSON constant')))


def _encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)+'\n'


def lock(project):
    """Atomic update after all packages passed validation."""
    root = Path(project).resolve()
    model = snapshot(root)
    target = root / _LOCK
    if target.is_symlink() or (target.exists() and not target.is_file()):
        raise ValueError('Lockfile must be an ordinary file')
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', prefix='.sedrava-lock-', dir=root, delete=False) as fh:
            tmp = Path(fh.name)
            encoded=_encode(model)
            if len(encoded.encode('utf-8'))>128000:raise ValueError('Lockfile resource limit')
            fh.write(encoded)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, target)
    finally:
        if tmp and tmp.exists():
            tmp.unlink()
    return target


def verify(project):
    """Refuse compilation if the lock is missing/stale/tampered."""
    root = Path(project).resolve()
    target = root / _LOCK
    if target.is_symlink() or not target.is_file() or target.stat().st_size > 128000:
        raise ValueError('Missing/invalid sedrava.lock; run sedrava lock first')
    try:
        current = _strict_json(target.read_text(encoding='utf-8'))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ValueError('Invalid sedrava.lock JSON') from exc
    expected = snapshot(root)
    if type(current) is not dict or _encode(current) != _encode(expected):
        raise ValueError('Local dependency lock mismatch: run sedrava lock after reviewing changes')
    return expected


def verify_if_project(source_path):
    if source_path is None:
        return None
    root = Path(source_path).resolve().parent
    if any(p.exists() or p.is_symlink() for p in (root/_MANIFEST,root/_LOCK)):
        verify(root)
        return (root / _MANIFEST, root / _LOCK)
    return None


def verified_inputs(source_path):
    root=Path(source_path).resolve().parent if source_path is not None else None
    if root is None or not any(p.exists() or p.is_symlink() for p in (root/_MANIFEST,root/_LOCK)):return None
    model=verify(root)
    return {root/pkg['path']/name:digest for pkg in model['packages'] for name,digest in pkg['files'].items()}

def read_module(path,root,verified):
    """Compile only bytes covered by the checked lock, not a later replacement."""
    from sedrava_syntax import MAX_SOURCE_CHARS
    path=Path(path);root=Path(root)
    with path.open('rb') as stream:raw=stream.read(MAX_SOURCE_CHARS*4+1)
    if len(raw)>MAX_SOURCE_CHARS*4:raise ValueError('Module resource limit')
    relative=path.relative_to(root)
    if relative.parts and relative.parts[0]=='vendor':
        if verified is None or path not in verified:raise ValueError('Vendored import is not covered by the reviewed lockfile')
        if sha256(raw).hexdigest()!=verified[path]:raise ValueError('Vendored module changed after lock verification')
    try:return raw.decode('utf-8')
    except UnicodeDecodeError as exc:
        from sedrava_source_map import LocatedError
        prefix=raw[:exc.start].decode('utf-8');line=prefix.count('\n')+1;column=len(prefix.rsplit('\n',1)[-1])+1
        raise LocatedError('Source is not valid UTF-8',path,line,column) from exc
