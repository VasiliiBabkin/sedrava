# History / История

Sedrava's current implementation is Rust. Python was the earlier implementation; its release artifacts and source remain available for historical reproducibility. The Python package is no longer an actively developed or recommended distribution. New projects use the Rust CLI.

- [Historical Python release v0.11.0](https://github.com/VasiliiBabkin/sedrava/tree/v0.11.0).
- [Last mixed source tree v0.12.0-alpha.1](https://github.com/VasiliiBabkin/sedrava/tree/v0.12.0-alpha.1), commit 0999a27dadf552019150d59cf9d59a76ec67293f.
- Old PyPI artifacts are retained, not removed or updated.

For explicitly historical differential checks only, extract the exact mixed-tree reference outside the current checkout:

~~~sh
reference=$(mktemp -d)
git archive v0.12.0-alpha.1 | tar -xf - -C "$reference"
export SEDRAVA_LEGACY_ROOT="$reference"
~~~

These test scripts are developer tools, not an alternate implementation shipped to users. Historical release notes and test evidence live in their original Git tags.
