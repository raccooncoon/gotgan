"""지식 파일과 신고 파일의 머리말(YAML)을 읽는 공용 함수."""
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML이 필요합니다: pip install pyyaml")

RESERVED = {"index.md", "log.md"}


def read(path):
    """(머리말 dict, 본문 str)을 돌려준다. 머리말이 없으면 ({}, 전체), YAML로 읽지 못하면 (None, 전체)."""
    text = Path(path).read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---", 4)
    if end < 0:
        return {}, text
    try:
        meta = yaml.safe_load(text[4:end]) or {}
    except yaml.YAMLError:
        return None, text
    return (meta if isinstance(meta, dict) else {}), text[end + 4:]


def as_list(value):
    if value in (None, "", []):
        return []
    return value if isinstance(value, list) else [value]


def concepts(root):
    """knowledge/ 아래에서 type이 있는 지식 파일을 고른다. 머리말이 깨진 파일은 meta가 None으로 나온다."""
    for path in sorted(Path(root).rglob("*.md")):
        if path.name in RESERVED:
            continue
        meta, body = read(path)
        if meta is None or meta.get("type"):
            yield path, meta, body
