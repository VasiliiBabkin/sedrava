"""Validate the built Sedrava archives before any registry upload."""
import email
import pathlib
import tarfile
import zipfile
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
DIST = pathlib.Path(sys.argv[1]).resolve() if len(sys.argv)>1 else ROOT / "dist"
EXPECTED_MODULES = {
    "sedrava.py", "sedrava_version.py", "sedrava_android_identity.py", "sedrava_core.py", "sedrava_navigation.py", "sedrava_navigation_web.py", "sedrava_navigation_android.py", "sedrava_cli.py", "sedrava_records.py", "sedrava_records_codegen.py", "sedrava_collections.py",
    "android_codegen.py", "android_codegen_v03.py", "web_codegen.py",
    "sedrava_syntax.py", "sedrava_frontend.py", "sedrava_site.py", "site_codegen.py",
}
EXPECTED_MODULES.update({name+'.py' for name in (
 'sedrava_webapp','sedrava_http','sedrava_http_parser','sedrava_http_codegen','sedrava_http_page','sedrava_http_embed','sedrava_http_inline','sedrava_http_display',
 'sedrava_modules','sedrava_namespaces','sedrava_source_map','sedrava_packages','sedrava_web_routes','sedrava_web_ui','sedrava_web_queries','sedrava_web_services','sedrava_web_assets','sedrava_functions','sedrava_stdlib','sedrava_queries','sedrava_diagnostics', 'sedrava_cost', 'sedrava_sequences', 'sedrava_results', 'sedrava_unicode', 'sedrava_unicode_data', 'sedrava_effects')})
LICENSE_MARKER = "Apache License"
sys.path.insert(0, str(ROOT))
from sedrava_version import VERSION
from scripts.rc_archive import read_zip, read_sdist


def check_metadata(raw):
    metadata = email.message_from_bytes(raw)
    assert metadata.get("Name", "").lower().replace("_", "-") == "sedrava", "wrong package name"
    assert metadata.get("Version") == VERSION, "wrong package version"
    assert metadata.get("License-Expression") == "Apache-2.0", "missing SPDX license metadata"


def main():
    wheel_files = list(DIST.glob("*.whl"))
    sdist_files = list(DIST.glob("*.tar.gz"))
    assert len(wheel_files) == len(sdist_files) == 1, "expected exactly one wheel and one sdist"
    read_zip(wheel_files[0].read_bytes())
    read_sdist(sdist_files[0].read_bytes())
    with zipfile.ZipFile(wheel_files[0]) as archive:
        names = archive.namelist()
        assert EXPECTED_MODULES.issubset(set(names)), "wheel missing Python modules"
        for required in ('share/sedrava/LICENSE','share/sedrava/docs/BUILD.md','share/sedrava/docs/RELEASE_READINESS_010_CONTRACT.md','share/sedrava/examples/task_manager.sdr','share/sedrava/examples/task_manager_navigation.sdr'):
            assert any(name.endswith('/'+required) for name in names), f'wheel missing {required}'
        licenses = [name for name in names if name.endswith("/LICENSE") or "/licenses/" in name and name.endswith("LICENSE")]
        assert licenses, "wheel missing LICENSE"
        assert LICENSE_MARKER in archive.read(licenses[0]).decode(), "incorrect LICENSE"
        metadata = [name for name in names if name.endswith(".dist-info/METADATA")]
        assert len(metadata) == 1
        check_metadata(archive.read(metadata[0]))
    with tarfile.open(sdist_files[0], "r:gz") as archive:
        names = archive.getnames()
        assert all(any(name.endswith("/" + module) for name in names) for module in EXPECTED_MODULES), "sdist missing modules"
        for required in ("examples/reference_09.sdr", "examples/countdown.sdr", "docs/LANGUAGE_0_9.md", "docs/QUICKSTART.md", "scripts/test_web_browser.py", "tests/test_alpha_core.py", "examples/text_profile.sdr", "docs/STRING_010_CONTRACT.md", "tests/fixtures/text_escaping.sdr", "scripts/prepare_text_android_tests.py"):
            assert any(name.endswith("/" + required) for name in names), f"sdist missing {required}"
        license_files = [name for name in names if name.endswith("/LICENSE")]
        assert license_files, "sdist missing LICENSE"
        member = archive.extractfile(license_files[0])
        assert member is not None and LICENSE_MARKER in member.read().decode(), "sdist license invalid"
    print("PASS: wheel/sdist, Apache-2.0 metadata and bundled license")


if __name__ == "__main__":
    main()
