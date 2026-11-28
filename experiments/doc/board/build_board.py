#!/usr/bin/env python3
"""실험 폴더의 검토 결과로 현황판 HTML 한 파일을 만든다. 외부 자원 없이 열린다.

현황판 안에 원문(text/)과 지식 파일(knowledge/)을 함께 넣어서,
주제 → 지식 본문 → 근거 → 원문의 그 줄까지 화면 안에서 따라갈 수 있다.

사용: build_board.py <lab> <board.html>
읽는 것: <lab>/report/review.json (형식은 ../REVIEW.md 3절), <lab>/text/, <lab>/knowledge/
필요: pip install pyyaml
참조가 끊겼거나 인용문을 원문에서 찾지 못한 항목은 경고로 알리고 계속한다.
"""
import bisect
import json
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML이 필요합니다: pip install pyyaml")

STATES = ["현행", "대체됨", "상충", "중복", "기록", "판단 불가"]
PREFIX = re.compile(r"^\[[^\]]*\] ")


def squash(text):
    return " ".join(str(text).split())


class Source:
    """원문 한 건. 인용문이 몇 번째 줄에 있는지 찾아 준다."""

    def __init__(self, lines):
        self.lines = lines
        self.variants = [self._index([squash(l) for l in lines]),
                         self._index([squash(PREFIX.sub("", l)) for l in lines])]

    @staticmethod
    def _index(parts):
        starts, pos = [], 0
        for p in parts:
            starts.append(pos)
            pos += len(p) + 1
        return " ".join(parts), starts

    def locate(self, quote):
        q = squash(quote)
        if not q:
            return None
        for text, starts in self.variants:
            at = text.find(q)
            if at >= 0:
                return bisect.bisect_right(starts, at), bisect.bisect_right(starts, at + len(q) - 1)
        return None


def read_knowledge(path):
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n") or "\n---" not in text[4:]:
        return {}, text
    end = text.find("\n---", 4)
    meta = yaml.safe_load(text[4:end]) or {}
    return (meta if isinstance(meta, dict) else {}), text[end + 4:].strip()


def line_range(value):
    m = re.fullmatch(r"\s*(\d+)(?:\s*-\s*(\d+))?\s*", str(value or ""))
    return (int(m.group(1)), int(m.group(2) or m.group(1))) if m else None


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    lab, out = Path(sys.argv[1]), Path(sys.argv[2])
    data = json.loads((lab / "report" / "review.json").read_text(encoding="utf-8"))
    warn = []
    docs = {d["id"]: d for d in data.get("docs", [])}
    topics = {t["id"] for t in data.get("topics", [])}
    by_text_path = {}
    sources = {}
    for d in docs.values():
        if d.get("state") not in STATES:
            warn.append(f"문서 {d['id']}: 알 수 없는 상태 {d.get('state')!r}")
        if d.get("superseded_by") and d["superseded_by"] not in docs:
            warn.append(f"문서 {d['id']}: superseded_by {d['superseded_by']} 없음")
        warn += [f"문서 {d['id']}: 주제 {t} 없음" for t in d.get("topics", []) if t not in topics]
        text_file = lab / "text" / (d["path"] + ".txt")
        by_text_path["text/" + d["path"] + ".txt"] = d["id"]
        if text_file.exists():
            sources[d["id"]] = Source(text_file.read_text(encoding="utf-8", errors="replace").splitlines())
            d["has_source"] = True
    for t in data.get("topics", []):
        if t.get("canonical") and t["canonical"] not in docs:
            warn.append(f"주제 {t['id']}: 정본 {t['canonical']} 없음")

    def place(doc_id, quote, where, given=None):
        """근거 하나의 줄 범위를 정한다. 주어진 줄이 없으면 인용문으로 찾는다."""
        if doc_id not in sources:
            warn.append(f"{where}: 문서 {doc_id}의 원문이 없음")
            return None
        found = given or sources[doc_id].locate(quote)
        if not found:
            warn.append(f"{where}: 인용문을 문서 {doc_id}의 원문에서 찾지 못함")
        return found

    for i in data.get("issues", []):
        warn += [f"문제 {i['id']}: 문서 {d} 없음" for d in i.get("docs", []) if d not in docs]
        if not i.get("evidence"):
            warn.append(f"문제 {i['id']}: 근거 없음")
        for e in i.get("evidence", []):
            given = (int(e["line"]), int(e.get("line_end", e["line"]))) if e.get("line") else None
            found = place(e.get("doc"), e.get("quote", ""), f"문제 {i['id']}", given)
            if found:
                e["line"], e["line_end"] = found

    for k in data.get("knowledge", []):
        path = lab / k["path"]
        if not path.exists():
            warn.append(f"지식 {k['path']}: 파일 없음")
            continue
        meta, body = read_knowledge(path)
        k["title"], k["body"], k["src"] = meta.get("title") or path.stem, body, []
        raw = meta.get("sources") or []
        for s in (raw if isinstance(raw, list) else [raw]):
            if not isinstance(s, dict):
                continue
            item = {"id": str(s.get("id", "")), "title": s.get("title") or "", "quote": s.get("x-gotgan-quote") or "",
                    "kind": s.get("x-gotgan-kind", "file"), "note": s.get("x-gotgan-note") or ""}
            doc_id = by_text_path.get(str(s.get("x-gotgan-path", "")))
            if item["kind"] == "file":
                if doc_id is None:
                    warn.append(f"지식 {k['path']}: 근거 {item['id']}의 경로가 문서 목록에 없음")
                else:
                    found = place(doc_id, item["quote"], f"지식 {k['path']} 근거 {item['id']}", line_range(s.get("x-gotgan-lines")))
                    item["doc"] = doc_id
                    if found:
                        item["line"], item["line_end"] = found
            k["src"].append(item)

    def embed(obj):
        return json.dumps(obj, ensure_ascii=False).replace("</", "<\\/")

    blocks = "\n".join(f'<script type="application/json" id="src-{doc_id}">{embed(s.lines)}</script>'
                       for doc_id, s in sources.items())
    template = (Path(__file__).parent / "template.html").read_text(encoding="utf-8")
    out.write_text(template.replace("/*DATA*/null", embed(data)).replace("<!--SOURCES-->", blocks), encoding="utf-8")
    for w in warn:
        print("경고:", w, file=sys.stderr)
    print(f"문서 {len(docs)}건(원문 포함 {len(sources)}건), 주제 {len(topics)}개, 문제 {len(data.get('issues', []))}건, "
          f"지식 {len(data.get('knowledge', []))}건, 경고 {len(warn)}건 → {out} ({out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
