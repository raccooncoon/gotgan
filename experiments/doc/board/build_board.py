#!/usr/bin/env python3
"""review.json으로 현황판 HTML 한 파일을 만든다. 외부 자원 없이 열린다.

사용: build_board.py <review.json> <board.html>
형식은 ../REVIEW.md 3절. 참조가 끊긴 항목은 경고로 알리고 계속한다.
"""
import json
import sys
from pathlib import Path

STATES = ["현행", "대체됨", "상충", "중복", "기록", "판단 불가"]


def warnings(data):
    docs = {d["id"] for d in data.get("docs", [])}
    topics = {t["id"] for t in data.get("topics", [])}
    for d in data.get("docs", []):
        if d.get("state") not in STATES:
            yield f"문서 {d['id']}: 알 수 없는 상태 {d.get('state')!r}"
        if d.get("superseded_by") and d["superseded_by"] not in docs:
            yield f"문서 {d['id']}: superseded_by {d['superseded_by']} 없음"
        for t in d.get("topics", []):
            if t not in topics:
                yield f"문서 {d['id']}: 주제 {t} 없음"
    for t in data.get("topics", []):
        if t.get("canonical") and t["canonical"] not in docs:
            yield f"주제 {t['id']}: 정본 {t['canonical']} 없음"
    for i in data.get("issues", []):
        for d in i.get("docs", []):
            if d not in docs:
                yield f"문제 {i['id']}: 문서 {d} 없음"
        if not i.get("evidence"):
            yield f"문제 {i['id']}: 근거 없음"


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    found = list(warnings(data))
    for w in found:
        print("경고:", w, file=sys.stderr)
    template = (Path(__file__).parent / "template.html").read_text(encoding="utf-8")
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    Path(sys.argv[2]).write_text(template.replace("/*DATA*/null", payload), encoding="utf-8")
    print(f"문서 {len(data.get('docs', []))}건, 주제 {len(data.get('topics', []))}개, "
          f"문제 {len(data.get('issues', []))}건, 경고 {len(found)}건 → {sys.argv[2]}")


if __name__ == "__main__":
    main()
