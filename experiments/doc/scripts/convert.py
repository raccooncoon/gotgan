#!/usr/bin/env python3
"""원본 문서를 위치 표시가 붙은 텍스트로 바꾼다.

출력의 모든 줄은 원본의 어느 자리에서 왔는지를 대괄호로 달고 있다.
  PDF   [p3]            3쪽의 글 한 줄        [p3 t1 r2]  3쪽 첫째 표의 2행
  XLSX  [매출!A3:D3]     시트 "매출"의 3행
  HWPX  [s0 p12]        첫 구역의 12번째 문단  [s0 p12 t1 r2 c3] 그 문단에 달린 첫째 표의 2행 3열
  HTML  [L120]          원본 120번째 줄에서 시작하는 글. 표의 행은 칸을 | 로 잇는다
  TXT, MD 등 텍스트      그대로 복사한다. 줄 번호가 위치다.

사용: convert.py <원본 폴더> <출력 폴더>
출력 폴더에 <원본 상대 경로>.txt 와 manifest.json 을 쓴다.
필요: pip install pdfplumber openpyxl
"""
import hashlib
import json
import sys
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree as ET

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
P, RUN, T, TBL, TR, TC, SUBLIST, CELLADDR = (HP + n for n in ("p", "run", "t", "tbl", "tr", "tc", "subList", "cellAddr"))


def one_line(text):
    return " ".join(str(text).split())


# ---- HWPX ----

def t_text(t):
    """hp:t 안의 글자. 사이에 낀 공백·탭 요소는 빈칸으로 바꾼다."""
    parts = [t.text or ""]
    for child in t:
        parts.append(" ")
        parts.append(child.tail or "")
    return "".join(parts)


def sublists_outside_tables(elem):
    """elem 아래의 hp:subList. 표 안이나 다른 subList 안으로는 내려가지 않는다."""
    for child in elem:
        if child.tag == SUBLIST:
            yield child
        elif child.tag != TBL:
            yield from sublists_outside_tables(child)


def hwpx_paragraph(p, loc, out):
    texts, tables, others = [], [], []
    for run in p.findall(RUN):
        for child in run:
            if child.tag == T:
                texts.append(t_text(child))
            elif child.tag == TBL:
                tables.append(child)
            else:
                others.append(child)
    text = one_line("".join(texts))
    if text:
        out.append(f"[{loc}] {text}")
    for ti, tbl in enumerate(tables, 1):
        for ri, tr in enumerate(tbl.findall(TR), 1):
            for ci, tc in enumerate(tr.findall(TC), 1):
                addr = tc.find(CELLADDR)
                if addr is not None and addr.get("rowAddr") is not None:
                    ri_, ci_ = int(addr.get("rowAddr")) + 1, int(addr.get("colAddr")) + 1
                else:
                    ri_, ci_ = ri, ci
                paras = [cp for sub in tc.findall(SUBLIST) for cp in sub.findall(P)]
                for pi, cp in enumerate(paras, 1):
                    suffix = f" p{pi}" if len(paras) > 1 else ""
                    hwpx_paragraph(cp, f"{loc} t{ti} r{ri_} c{ci_}{suffix}", out)
    for oi, other in enumerate(others, 1):
        paras = [cp for sub in sublists_outside_tables(other) for cp in sub.findall(P)]
        for pi, cp in enumerate(paras, 1):
            hwpx_paragraph(cp, f"{loc} o{oi} p{pi}", out)


def convert_hwpx(path):
    out, notes = [], []
    with zipfile.ZipFile(path) as z:
        sections = sorted(
            (n for n in z.namelist() if n.startswith("Contents/section") and n.endswith(".xml")),
            key=lambda n: int("".join(c for c in n if c.isdigit()) or 0),
        )
        if not sections:
            raise ValueError("본문 구역(Contents/section*.xml)이 없음")
        images = [n for n in z.namelist() if n.startswith("BinData/")]
        if images:
            notes.append(f"그림 {len(images)}개의 내용은 추출하지 않음")
        for si, name in enumerate(sections):
            root = ET.fromstring(z.read(name))
            for pi, p in enumerate(root.findall(P), 1):
                hwpx_paragraph(p, f"s{si} p{pi}", out)
    return out, notes


# ---- XLSX ----

def convert_xlsx(path):
    import openpyxl
    from openpyxl.utils import get_column_letter

    out, notes = [], []
    values = openpyxl.load_workbook(path, data_only=True)
    formulas = openpyxl.load_workbook(path, data_only=False)
    for ws in values.worksheets:
        fs = formulas[ws.title]
        uncached = 0
        for row in ws.iter_rows():
            cells = []
            for cell in row:
                formula = fs[cell.coordinate].value
                is_formula = isinstance(formula, str) and formula.startswith("=")
                if cell.value is None and not is_formula:
                    cells.append("")
                    continue
                if is_formula and cell.value is None:
                    uncached += 1
                shown = "" if cell.value is None else one_line(cell.value)
                cells.append(f"{shown} {{{formula}}}" if is_formula else shown)
            if any(cells):
                first, last = row[0].coordinate, f"{get_column_letter(len(cells))}{row[0].row}"
                out.append(f"[{ws.title}!{first}:{last}] " + " | ".join(cells))
        if uncached:
            notes.append(f"시트 '{ws.title}': 계산된 값이 저장되지 않은 수식 {uncached}개 (수식만 추출)")
        if ws.merged_cells.ranges:
            notes.append(f"시트 '{ws.title}': 병합 셀 {len(ws.merged_cells.ranges)}곳은 왼쪽 위 칸에만 값이 있음")
    return out, notes


# ---- PDF ----

def convert_pdf(path):
    import pdfplumber

    out, notes, empty = [], [], []
    with pdfplumber.open(path) as pdf:
        for pi, page in enumerate(pdf.pages, 1):
            text = page.extract_text() or ""
            lines = [one_line(l) for l in text.splitlines() if l.strip()]
            if not lines:
                empty.append(pi)
            out.extend(f"[p{pi}] {l}" for l in lines)
            for ti, table in enumerate(page.extract_tables(), 1):
                for ri, row in enumerate(table, 1):
                    out.append(f"[p{pi} t{ti} r{ri}] " + " | ".join(one_line(c or "") for c in row))
    if empty:
        notes.append(f"글자를 읽지 못한 쪽: {', '.join(map(str, empty))} (스캔본이면 OCR 필요)")
    return out, notes


# ---- HTML ----

class _HtmlText(HTMLParser):
    BLOCK = {"p", "div", "li", "tr", "br", "h1", "h2", "h3", "h4", "h5", "h6", "section", "article",
             "header", "footer", "table", "ul", "ol", "pre", "blockquote", "title", "dt", "dd", "caption"}
    SKIP = {"script", "style", "template", "noscript"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.buf, self.start = [], [], None
        self.skip, self.skipped_chars = 0, 0

    def flush(self):
        text = one_line("".join(self.buf)).strip(" |")
        if text:
            self.out.append(f"[L{self.start}] {text}")
        self.buf, self.start = [], None

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        elif tag in self.BLOCK:
            self.flush()
        elif tag in ("td", "th") and self.buf:
            self.buf.append(" | ")

    def handle_endtag(self, tag):
        if tag in self.SKIP:
            self.skip = max(0, self.skip - 1)
        elif tag in self.BLOCK:
            self.flush()

    def handle_data(self, data):
        if self.skip:
            self.skipped_chars += len(data)
        elif data.strip():
            if self.start is None:
                self.start = self.getpos()[0]
            self.buf.append(data)
        elif self.buf:
            self.buf.append(" ")


def convert_html(path):
    parser = _HtmlText()
    parser.feed(path.read_text(encoding="utf-8", errors="replace"))
    parser.flush()
    body = sum(len(l) for l in parser.out)
    notes = []
    if parser.skipped_chars > 20 * max(body, 1):
        notes.append(f"본문 {body}자, 스크립트·스타일 {parser.skipped_chars}자: 내용이 스크립트로 그려지는 것으로 보임")
    return parser.out, notes


def convert_text(path):
    return path.read_text(encoding="utf-8").splitlines(), []


CONVERTERS = {".hwpx": convert_hwpx, ".xlsx": convert_xlsx, ".pdf": convert_pdf,
              ".html": convert_html, ".htm": convert_html,
              **{ext: convert_text for ext in (".txt", ".md", ".json", ".sql", ".py", ".csv")}}


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    manifest = []
    for path in sorted(p for p in src.rglob("*") if p.is_file() and not p.name.startswith(".")):
        rel = path.relative_to(src)
        entry = {"file": str(rel), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        convert = CONVERTERS.get(path.suffix.lower())
        if convert is None:
            entry.update(status="실패", reason=f"지원하지 않는 형식: {path.suffix or '확장자 없음'}")
        else:
            try:
                lines, notes = convert(path)
            except Exception as e:  # 깨졌거나 암호가 걸린 파일. 사유를 남기고 다음 파일로 간다.
                entry.update(status="실패", reason=f"{type(e).__name__}: {e}")
            else:
                if not lines:
                    entry.update(status="실패", reason="추출된 내용이 없음", notes=notes)
                else:
                    target = dst / (str(rel) + ".txt")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
                    entry.update(status="부분 추출" if notes else "성공", lines=len(lines),
                                 notes=notes, output=str(rel) + ".txt")
        manifest.append(entry)
        print(f"{entry['status']:6} {rel}" + (f"  ({entry.get('reason') or '; '.join(entry.get('notes', []))})"
                                              if entry["status"] != "성공" else ""))
    dst.mkdir(parents=True, exist_ok=True)
    (dst / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    counts = {s: sum(e["status"] == s for e in manifest) for s in ("성공", "부분 추출", "실패")}
    print(f"파일 {len(manifest)}개: 성공 {counts['성공']}, 부분 추출 {counts['부분 추출']}, 실패 {counts['실패']}")


if __name__ == "__main__":
    main()
