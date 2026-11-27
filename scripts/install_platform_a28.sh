#!/bin/sh
# Linux GNU utilities, trusted local archive and independently obtained SHA256.
set -eu
umask 077
[ "$#" -eq 3 ] || { echo 'Usage: install_platform_a28.sh ARCHIVE SHA256 NEW_ABSOLUTE_PREFIX' >&2; exit 2; }
archive=$1
expected=$2
prefix=$3
die() { echo "$*" >&2; exit 1; }
case "$expected" in *[!0123456789abcdef]*|'') die 'Invalid SHA256';; esac
[ "${#expected}" -eq 64 ] || die 'Expected 64 hex digits'
case "$prefix" in /*) ;; *) die 'Absolute new prefix required';; esac
case "$prefix" in */|*/.|*/..) die 'Invalid prefix';; esac
[ -f "$archive" ] && [ ! -L "$archive" ] || die 'Regular archive required'
[ ! -e "$prefix" ] && [ ! -L "$prefix" ] || die 'Prefix exists'
parent=$(dirname -- "$prefix")
[ -d "$parent" ] && [ ! -L "$parent" ] || die 'Existing real parent required'
hash() { sha256sum "$1" | cut -d ' ' -f 1; }
# Snapshot archive in private staging, then verify the exact bytes consumed.
stage=$(mktemp -d "$parent/.sedrava-platform.XXXXXXXX")
cleanup() { rm -rf -- "$stage"; }
trap cleanup 0
trap 'exit 1' 1 2 3 15
cp -- "$archive" "$stage/archive"
[ "$(hash "$stage/archive")" = "$expected" ] || die 'Archive SHA256 mismatch'
mkdir "$stage/install" "$stage/install/bin"
cat > "$stage/expected" <<'EOF'
sedrava-platform/LICENSE.sedrava
sedrava-platform/LICENSE.sedravasql
sedrava-platform/NATIVE_MIGRATIONS_A24.ru.md
sedrava-platform/PROJECT_CLI_A25.ru.md
sedrava-platform/README.txt
sedrava-platform/SERVER_SESSIONS_A23D.ru.md
sedrava-platform/SHA256SUMS.txt
sedrava-platform/bin/sedrava
sedrava-platform/bin/sedravasql-native-preview
sedrava-platform/manifest.json
EOF
tar -tzf "$stage/archive" > "$stage/members"
cmp -s "$stage/expected" "$stage/members" || die 'Unexpected archive members'
# No archive-controlled paths are extracted. Require regular member types.
tar -tvzf "$stage/archive" > "$stage/types"
awk 'substr($0,1,1)!="-" {exit 1} END {if(NR!=10)exit 1}' "$stage/types" || die 'Nonregular archive member'
while IFS= read -r member; do
    relative=${member#sedrava-platform/}
    tar -xOzf "$stage/archive" "$member" > "$stage/install/$relative"
done < "$stage/expected"
# Require exact checksum file, no caller-controlled paths in sha256sum -c.
: > "$stage/actual"
for name in LICENSE.sedrava LICENSE.sedravasql NATIVE_MIGRATIONS_A24.ru.md PROJECT_CLI_A25.ru.md README.txt SERVER_SESSIONS_A23D.ru.md bin/sedrava bin/sedravasql-native-preview manifest.json; do
    printf '%s  %s\n' "$(hash "$stage/install/$name")" "$name" >> "$stage/actual"
done
cmp -s "$stage/actual" "$stage/install/SHA256SUMS.txt" || die 'Member checksums mismatch'
chmod 755 "$stage/install/bin/sedrava" "$stage/install/bin/sedravasql-native-preview"
# GNU mv -T -n: no replace; detect a skipped move. Trusted parent, no hostile replacement.
mv -T -n -- "$stage/install" "$prefix"
[ ! -e "$stage/install" ] || die 'Prefix appeared; refusing overwrite'
printf 'Installed Sedrava Platform: %s\n' "$prefix"
