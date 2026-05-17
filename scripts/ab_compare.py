"""Compare scores between A/B run archives.

Usage: python scripts/ab_compare.py <ab_dir>

Reads ab_dir/{label}/runs/{eng,qa}-lg-lg-SKILLS-bl-*/scorecard.md and emits a
markdown comparison table.
"""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path


def extract_score(path: Path) -> dict:
    if not path.exists():
        return {}
    text = path.read_text(errors="replace")
    out = {}
    m = re.search(r"Total Score:\s*(\d+)/75", text)
    if m: out["total"] = int(m.group(1))
    m = re.search(r"Headline Score.*?(\d+)/75", text)
    if m: out["total"] = out.get("total") or int(m.group(1))
    m = re.search(r"Decision:\s*\*?\*?([A-Za-z][A-Za-z W/-]+)", text)
    if m: out["decision"] = m.group(1).strip().rstrip("*").strip()
    m = re.search(r"core\s+(\d+)/50", text)
    if m: out["core"] = int(m.group(1))
    m = re.search(r"role\s+(\d+)/25", text)
    if m: out["role"] = int(m.group(1))
    m = re.search(r"QA-rubric\s+(\d+)/25", text)
    if m: out["qa_rubric"] = int(m.group(1))
    m = re.search(r"axes:\s*\*?\*?(\d+)/(\d+)", text)
    if m: out["axes"] = f"{m.group(1)}/{m.group(2)}"
    return out


def scan_label(runs_dir: Path) -> dict:
    """Return {bl_id: {eng: {...}, qa: {...}}}."""
    by_bl = defaultdict(lambda: {"eng": {}, "qa": {}})
    if not runs_dir.exists():
        return by_bl
    for d in sorted(runs_dir.glob("eng-lg-lg-SKILLS-bl-*")):
        bl = d.name.split("bl-")[-1]
        by_bl[bl]["eng"] = extract_score(d / "scorecard.md")
    for d in sorted(runs_dir.glob("qa-lg-lg-SKILLS-bl-*")):
        bl = d.name.split("bl-")[-1]
        by_bl[bl]["qa"] = extract_score(d / "scorecard.md")
    return by_bl


def count_retrieval_calls(runs_dir: Path) -> dict:
    """Count tool calls per role from retrieval.jsonl."""
    counts = {"po": 0, "eng": 0, "qa": 0}
    by_tool = defaultdict(int)
    if not runs_dir.exists():
        return {"by_role": counts, "by_tool": dict(by_tool)}
    for jf in runs_dir.glob("**/retrieval.jsonl"):
        role = jf.parent.parent.name.split("-")[0]  # po / eng / qa
        if role not in counts: continue
        for line in jf.read_text().splitlines():
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            counts[role] += 1
            t = rec.get("tool")
            if t: by_tool[t] += 1
    return {"by_role": counts, "by_tool": dict(by_tool)}


def main():
    ab_dir = Path(sys.argv[1])
    labels = sorted([p.name for p in ab_dir.iterdir() if p.is_dir() and (p / "runs").exists()])
    if len(labels) < 2:
        print(f"need at least 2 labels under {ab_dir}, found {labels}")
        sys.exit(1)

    data = {label: scan_label(ab_dir / label / "runs") for label in labels}
    retrieval = {label: count_retrieval_calls(ab_dir / label / "runs") for label in labels}

    all_bls = sorted(set().union(*[d.keys() for d in data.values()]))

    print(f"# A/B comparison — {ab_dir.name}\n")
    print(f"Labels: {' vs. '.join(labels)}\n")

    # Score table
    print("## Per-BL scores\n")
    header = "| BL |" + "".join(f" {l} eng | {l} qa |" for l in labels) + " Δeng | Δqa |"
    sep = "|---|" + "|".join("---" for _ in range(len(labels) * 2 + 2)) + "|"
    print(header)
    print(sep)
    eng_totals = defaultdict(list)
    qa_totals = defaultdict(list)
    for bl in all_bls:
        row = [f"| {bl} |"]
        eng_scores = []
        qa_scores = []
        for l in labels:
            e = data[l].get(bl, {}).get("eng", {})
            q = data[l].get(bl, {}).get("qa", {})
            es = e.get("total")
            qs = q.get("total")
            row.append(f" {es if es is not None else '—'} |")
            row.append(f" {qs if qs is not None else '—'} |")
            eng_scores.append(es); qa_scores.append(qs)
            if es is not None: eng_totals[l].append(es)
            if qs is not None: qa_totals[l].append(qs)
        if len(eng_scores) == 2 and None not in eng_scores:
            row.append(f" {eng_scores[1] - eng_scores[0]:+d} |")
        else:
            row.append(" — |")
        if len(qa_scores) == 2 and None not in qa_scores:
            row.append(f" {qa_scores[1] - qa_scores[0]:+d} |")
        else:
            row.append(" — |")
        print("".join(row))

    # Aggregates
    print("\n## Aggregates\n")
    print("| Label | Eng avg | Eng n | QA avg | QA n |")
    print("|---|---|---|---|---|")
    for l in labels:
        e = eng_totals[l]; q = qa_totals[l]
        em = sum(e) / len(e) if e else 0.0
        qm = sum(q) / len(q) if q else 0.0
        print(f"| {l} | {em:.1f} | {len(e)} | {qm:.1f} | {len(q)} |")

    # Retrieval usage
    print("\n## Retrieval tool usage\n")
    print("| Label | po | eng | qa | by tool |")
    print("|---|---|---|---|---|")
    for l in labels:
        r = retrieval[l]
        roles = r["by_role"]
        tools = r["by_tool"]
        tools_str = ", ".join(f"{k}={v}" for k, v in sorted(tools.items())) or "(none)"
        print(f"| {l} | {roles['po']} | {roles['eng']} | {roles['qa']} | {tools_str} |")


if __name__ == "__main__":
    main()
