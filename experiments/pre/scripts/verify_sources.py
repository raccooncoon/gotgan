#!/usr/bin/env python3
"""지식 파일의 근거를 검사한다.

file 근거: 인용문이 대상 저장소의 기록된 커밋, 경로, 줄 범위 안에 실제로 있는지 본다.
그 밖의 근거(observation, human): 검사할 수 없음으로 센다.
본문의 각주 라벨이 sources의 id와 맞는지, 본문의 모든 문단에 근거 각주가 있는지도 본다.

사용: verify_sources.py <lab/knowledge> <대상 저장소 경로>
실패가 하나라도 있으면 종료 코드 1.
"""
import re
import subprocess
import sys

from _okf import as_list, concepts


def squash(text):
    return re.sub(r"\s+", " ", str(text)).strip()


def file_lines(repo, commit, path):
    out = subprocess.run(
        ["git", "-C", repo, "show", f"{commit}:{path}"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return out.stdout.splitlines() if out.returncode == 0 else None


def check_file_source(repo, src):
    need = ["x-gotgan-path", "x-gotgan-commit", "x-gotgan-lines", "x-gotgan-quote"]
    missing = [k for k in need if not src.get(k)]
    if missing:
        return f"필드 없음: {', '.join(missing)}"
    m = re.fullmatch(r"(\d+)(?:-(\d+))?", str(src["x-gotgan-lines"]).strip())
    if not m:
        return f"줄 범위 형식 오류: {src['x-gotgan-lines']}"
    start, end = int(m.group(1)), int(m.group(2) or m.group(1))
    lines = file_lines(repo, src["x-gotgan-commit"], src["x-gotgan-path"])
    if lines is None:
        return "그 커밋에 그 파일이 없음"
    if start < 1 or end > len(lines) or start > end:
        return f"줄 범위가 파일 밖 (파일은 {len(lines)}줄)"
    if squash(src["x-gotgan-quote"]) not in squash("\n".join(lines[start - 1:end])):
        return "인용문이 그 줄 범위에 없음"
    return None


def uncited_blocks(body):
    """근거 각주가 없는 문단 수. 제목, 각주 정의, 코드 블록, 표 구분선은 세지 않는다."""
    body = re.sub(r"```.*?```", "", body, flags=re.S)
    count = 0
    for block in re.split(r"\n\s*\n", body):
        lines = [l for l in block.strip().splitlines()
                 if l.strip() and not re.match(r"\s*(#|\[\^[^\]]+\]:|\|?\s*:?-{3,})", l)]
        if lines and not re.search(r"\[\^[^\]]+\](?!:)", "\n".join(lines)):
            count += 1
    return count


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    knowledge, repo = sys.argv[1], sys.argv[2]
    checked = failed = uncheckable = files = 0
    for path, meta, body in concepts(knowledge):
        files += 1
        if meta is None:
            failed += 1
            print(f"실패  {path}: 머리말을 YAML로 읽을 수 없음")
            continue
        sources = [s for s in as_list(meta.get("sources")) if isinstance(s, dict)]
        problems = []
        if not sources:
            problems.append("근거가 없음")
        ids = {str(s["id"]) for s in sources if s.get("id")}
        cited = set(re.findall(r"\[\^([^\]]+)\](?!:)", body))
        for label in sorted(cited - ids):
            problems.append(f"각주 [^{label}]에 해당하는 근거가 없음")
        bare = uncited_blocks(body)
        if bare:
            problems.append(f"근거 각주가 없는 문단 {bare}개")
        for src in sources:
            name = src.get("id", "?")
            if src.get("x-gotgan-kind", "file") != "file":
                uncheckable += 1
                continue
            checked += 1
            error = check_file_source(repo, src)
            if error:
                problems.append(f"근거 {name}: {error}")
        failed += len(problems)
        for p in problems:
            print(f"실패  {path}: {p}")
    print(f"지식 {files}건, 검사한 인용문 {checked}건, 검사 불가 근거 {uncheckable}건, 실패 {failed}건")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
