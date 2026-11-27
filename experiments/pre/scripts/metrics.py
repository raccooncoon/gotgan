#!/usr/bin/env python3
"""실험 폴더에서 현황판용 수치를 모아 report/metrics.json을 만든다.

사용: metrics.py <lab 경로>
"""
import json
import sys
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path

from _okf import as_list, concepts, read


def instant(value):
    """RFC 3339 날짜나 날짜-시각을 UTC 시각으로 바꾼다. 읽지 못하면 None."""
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, date):
        dt = datetime(value.year, value.month, value.day)
    else:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def trust_tier(meta):
    """OKF v0.3 5.3절: 내용이 바뀐 뒤의 확인만 센다."""
    generated = meta.get("generated") if isinstance(meta.get("generated"), dict) else {}
    since = instant(generated.get("at")) if generated.get("at") else None
    actors = []
    for event in as_list(meta.get("verified")):
        if not (isinstance(event, dict) and event.get("by") and event.get("at")):
            continue
        at = instant(event["at"])
        if at and (since is None or at >= since):
            actors.append(str(event["by"]))
    if any(a.startswith("human:") for a in actors):
        return "human-reviewed"
    return "machine-confirmed" if actors else "unverified"


def knowledge_stats(lab, unreadable):
    tiers, types, areas, statuses, evidence = Counter(), Counter(), Counter(), Counter(), Counter()
    total = 0
    for path, meta, _ in concepts(lab / "knowledge"):
        if meta is None:
            unreadable.append(str(path))
            continue
        total += 1
        tiers[trust_tier(meta)] += 1
        types[str(meta["type"])] += 1
        areas[str(meta.get("x-gotgan-area", "미분류"))] += 1
        statuses[str(meta.get("status") or "stable")] += 1
        kinds = {str(s.get("x-gotgan-kind", "file")) for s in as_list(meta.get("sources")) if isinstance(s, dict)}
        evidence["file-only" if kinds == {"file"} else "none" if not kinds else "includes-unchecked"] += 1
    return {"total": total, "by_tier": dict(tiers), "by_type": dict(types),
            "by_area": dict(areas), "by_status": dict(statuses),
            "by_evidence": dict(evidence)}


def flag_stats(lab, unreadable):
    """신고를 머리말의 round 값별로 센다."""
    rounds = {}
    kinds = Counter()
    open_now = 0
    for path in sorted((lab / "flags").glob("*.md")):
        meta, _ = read(path)
        if meta is None:
            unreadable.append(str(path))
            continue
        if not meta:
            continue
        rnd = str(meta.get("round") or "미상")
        row = rounds.setdefault(rnd, {"opened": 0, "closed": 0, "repeat": 0})
        row["opened"] += 1
        kinds[str(meta.get("kind", "미상"))] += 1
        if meta.get("status") == "closed":
            row["closed"] += 1
        else:
            open_now += 1
        if meta.get("repeat_of"):
            row["repeat"] += 1
    return {"by_round": rounds, "by_kind": dict(kinds), "open": open_now}


def score_stats(lab):
    split = {}
    for path in sorted((lab / "tasks").glob("*.md")):
        meta, _ = read(path)
        if meta.get("id"):
            split[str(meta["id"])] = str(meta.get("split", "미상"))
    rounds = {}
    for path in sorted((lab / "scores").glob("*.json")):
        rows = json.loads(path.read_text(encoding="utf-8"))
        out = {}
        for row in rows:
            part = out.setdefault(split.get(str(row["task"]), "미상"), {"checks": 0, "violations": 0})
            part["checks"] += 1
            part["violations"] += 0 if row["pass"] else 1
        rounds[path.stem] = out
    return rounds


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    lab = Path(sys.argv[1])
    scores = score_stats(lab)
    unreadable = []
    review = lab / "report" / "review_minutes.txt"
    review2 = lab / "report" / "review_minutes_s2.txt"
    result = {
        "target_commit": (lab / "TARGET").read_text(encoding="utf-8").strip() if (lab / "TARGET").exists() else None,
        "knowledge": knowledge_stats(lab, unreadable),
        "flags": flag_stats(lab, unreadable),
        "scores": scores,
        "review_minutes": float(review.read_text().strip()) if review.exists() else None,
        "review_minutes_s2": float(review2.read_text().strip()) if review2.exists() else None,
        "unreadable_files": unreadable,
    }
    for path in unreadable:
        print(f"경고: 머리말을 읽을 수 없어 집계에서 뺐습니다: {path}", file=sys.stderr)
    out = lab / "report" / "metrics.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
