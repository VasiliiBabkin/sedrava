#!/bin/sh
# Offline installer for a user-supplied, SHA256-pinned Linux/macOS preview.
# Never calls Python, pip, Rust or a network endpoint.
set -eu
umask 077
[ "$#" -eq 3 ] || {
  echo 'Usage: install_native_preview.sh ARCHIVE.tar.gz SHA256 ABSOLUTE_PREFIX' >&2
  exit 2
}
archive=$1
expected=$2
prefix=$3
case "$expected" in
  *[!0123456789abcdef]*|'') echo 'Expected lowercase SHA-256 hex' >&2; exit 2;;
esac
[ "$(printf '%s' "$expected" | wc -c | tr -d ' ')" = 64 ] || {
  echo 'Expected 64-digit SHA-256' >&2; exit 2;
}
case "$prefix" in
  /*) ;;
  *) echo 'Prefix must be an absolute directory' >&2; exit 2;;
esac
[ -f "$archive" ] && [ ! -L "$archive" ] || {
  echo 'Archive must be a non-symlink regular file' >&2; exit 2;
}
hash() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | cut -d ' ' -f 1
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$1" | cut -d ' ' -f 1
  else
    echo 'SHA-256 utility unavailable' >&2
    return 1
  fi
}
[ "$(hash "$archive")" = "$expected" ] || {
  echo 'Archive SHA256 mismatch: installation refused' >&2; exit 1;
}
[ ! -L "$prefix" ] && [ ! -L "$prefix/bin" ] || {
  echo 'Symlink install prefix forbidden' >&2; exit 1;
}
mkdir -p "$prefix/bin"
destination="$prefix/bin/sedrava"
[ ! -e "$destination" ] && [ ! -L "$destination" ] || {
  echo 'Target exists; refusing overwrite' >&2; exit 1;
}
temporary=$(mktemp -d "$prefix/.sedrava-install.XXXXXXXX") || exit 1
cleanup() { rm -rf -- "$temporary"; }
trap cleanup 0
trap 'exit 1' 1 2 3 15
# Extract only exact expected members as bytes; no traversal/symlink expansion.
cat > "$temporary/expected" <<'EOF'
sedrava/LICENSE
sedrava/README.txt
sedrava/SHA256SUMS.txt
sedrava/manifest.json
sedrava/sedrava
EOF
tar -tzf "$archive" > "$temporary/members"
cmp -s "$temporary/expected" "$temporary/members" || {
  echo 'Unexpected archive layout: installation refused' >&2; exit 1;
}
tar -xOzf "$archive" sedrava/SHA256SUMS.txt > "$temporary/sums"
binary_expected=$(awk '$2=="sedrava/sedrava" {print $1; n++}
  END {if (n!=1) exit 1}' "$temporary/sums")
case "$binary_expected" in
  *[!0123456789abcdef]*|'') echo 'Invalid binary checksum' >&2; exit 1;;
esac
[ "$(printf '%s' "$binary_expected" | wc -c | tr -d ' ')" = 64 ] || exit 1
tar -xOzf "$archive" sedrava/sedrava > "$temporary/sedrava"
[ "$(hash "$temporary/sedrava")" = "$binary_expected" ] || {
  echo 'Native executable hash mismatch' >&2; exit 1;
}
chmod 755 "$temporary/sedrava"
# Atomic hardlink publication on same filesystem; no replace even in a race.
ln "$temporary/sedrava" "$destination" || {
  echo 'Cannot publish native executable without overwrite' >&2; exit 1;
}
printf 'Installed Sedrava: %s\n' "$destination"
