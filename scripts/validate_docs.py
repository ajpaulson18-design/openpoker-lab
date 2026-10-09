"""Check required knowledge entry points and local inline Markdown file links.

No third-party parser is needed. Fenced examples and external/fragment-only links
are excluded. This is a structural check, not semantic or remote-URL validation.
"""
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = (
    'AGENTS.md', 'docs/START_HERE.md', 'docs/product/VISION.md',
    'docs/engineering/CURRENT_STATE.md', 'docs/architecture/SYSTEM_OVERVIEW.md',
    'docs/decisions/DECISION_LOG.md', 'docs/history/PROJECT_HISTORY.md',
    'docs/context/SOURCE_INDEX.md', 'docs/context/KNOWLEDGE_GAPS.md',
    'docs/context/RECOVERED_CHAT_KNOWLEDGE.md', 'docs/agents/TASK_PROTOCOL.md',
    'docs/research/LICENSING.md',
)
LINK = re.compile(r'!?\[[^\]\n]*\]\(\s*(<[^>]+>|[^\s)]+)(?:\s+"[^"]*")?\s*\)')


def validate(root=ROOT):
    errors = [f'missing required document: {p}' for p in REQUIRED if not (root / p).is_file()]
    files = sorted(p for p in root.rglob('*.md') if '.git' not in p.parts)
    count = 0
    for source in files:
        fence = None
        for line_number, line in enumerate(source.read_text(encoding='utf-8').splitlines(), 1):
            marker = re.match(r'^\s*(`{3,}|~{3,})', line)
            if marker:
                value = marker.group(1)
                if fence is None:
                    fence = value
                elif value[0] == fence[0] and len(value) >= len(fence):
                    fence = None
                continue
            if fence:
                continue
            for match in LINK.finditer(line):
                target = match.group(1).strip('<>')
                parts = urlsplit(target)
                if parts.scheme or parts.netloc or not parts.path:
                    continue
                count += 1
                path = root / unquote(parts.path.lstrip('/')) if parts.path.startswith('/') else source.parent / unquote(parts.path)
                if not path.exists():
                    errors.append(f'{source.relative_to(root)}:{line_number}: missing local target {target}')
    return files, count, errors


def main():
    files, count, errors = validate()
    if errors:
        print('\n'.join(errors), file=sys.stderr)
        return 1
    print(f'Documentation check passed: {len(files)} Markdown files, {count} local links, {len(REQUIRED)} required entry points.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
