"""Check local Markdown links in current alpha documentation (historical docs excluded)."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
CURRENT = ['docs/011_WEB_PLATFORM.en.md', 'docs/011_WEB_PLATFORM.ru.md', 'docs/011_IMPLEMENTATION_STATUS.md', 'README.md', 'CHANGELOG.md', 'examples/README.md'] + [
    'docs/' + name + '.md' for name in ('WEB_UI_011.en', 'WEB_UI_011.ru', 'WEB_UI_011_SLICE_A', 'WEB_UI_011_REPORT', 'RC2_010_PREPARATION', 'RC2_010_REPORT', 'RELEASE_NOTES_0_10_0rc2.en', 'RELEASE_NOTES_0_10_0rc2.ru', 'UPGRADE_0_10_0rc2.en', 'UPGRADE_0_10_0rc2.ru', 'STABILITY_AUDIT_010', 'STABLE_RELEASE_GATES_010', 'COMPATIBILITY_010', 'RC_010_PREPARATION', 'RC_010_REPORT', 'RC_PUBLISHING', 'RELEASE_NOTES_0_10_0rc1.en', 'RELEASE_NOTES_0_10_0rc1.ru', 'UPGRADE_0_10_0rc1.en', 'UPGRADE_0_10_0rc1.ru', 'RELEASE_READINESS_010_CONTRACT', 'RELEASE_READINESS_010_REPORT', 'ANDROID_ID.en', 'ANDROID_ID.ru', 'README.en', 'README.ru', 'QUICKSTART', 'LANGUAGE_0_9', 'BUILD', 'FAQ',
    'KNOWN_LIMITATIONS', 'SECURITY', 'ALPHA_AUDIT', 'RELEASE_NOTES_0_9_0a1',
    'NAVIGATION_010_CONTRACT', 'NAVIGATION_010_REPORT', 'NAVIGATION_QUICKSTART.en', 'NAVIGATION_QUICKSTART.ru', 'PLAN_0_10_UI', 'RECORDS_COLLECTIONS_010', 'COLLECTIONS_010_REPORT', 'RECORDS_QUICKSTART.en', 'RECORDS_QUICKSTART.ru', 'LANGUAGE_0_10_TEXT', 'STRING_010_CONTRACT', 'DESCRIBE_GET_010', 'TEXT_010_REPORT')]


def main():
    errors = []
    for filename in CURRENT:
        path = ROOT / filename
        if not path.is_file():
            errors.append(f'Missing {filename}')
            continue
        for target in re.findall(r'\]\(([^)]+)\)', path.read_text(encoding='utf-8')):
            if '://' in target or target.startswith('#'):
                continue
            target = target.split('#', 1)[0]
            if not (path.parent / target).exists():
                errors.append(f'{filename}: broken link {target}')
    if errors:
        raise SystemExit('\n'.join(errors))
    print(f'PASS: {len(CURRENT)} current documentation files and local links')


if __name__ == '__main__':
    main()
