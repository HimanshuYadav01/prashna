"""Annex A Source Precedence Policy as a pure function over chunk metadata.

Steps: 1 applicability (dates + scope) -> 2 explicit supersession (levels 1-2)
-> 3 authority -> 4 recency -> 5 unresolved => conflict_flagged.
Level 5 is informational only and never overrides.
"""
from dataclasses import dataclass, field


@dataclass
class Decision:
    kept: list
    dropped: list
    log: list = field(default_factory=list)
    conflict: bool = False
    upcoming: list = field(default_factory=list)


def _applicable(meta, as_of_date, programme):
    ef, et = meta.get("effective_from") or "0000-01-01", meta.get("effective_to") or ""
    if ef > as_of_date:
        return False, "not_yet_effective"
    if et and et < as_of_date:
        return False, "expired"
    scope = meta.get("scope_programmes", "ALL") or "ALL"
    if scope != "ALL" and programme and programme not in scope:
        return False, "out_of_scope"
    return True, ""


def resolve(chunks, as_of_date, programme=None):
    """chunks: list of {text, meta{doc_id, section, authority_level, effective_from,
    effective_to, supersedes, scope_programmes, version, title, page}}"""
    d = Decision(kept=[], dropped=[])

    # Step 1 — applicability
    live = []
    for ch in chunks:
        ok, why = _applicable(ch["meta"], as_of_date, programme)
        if ok:
            live.append(ch)
        else:
            d.dropped.append(ch)
            d.log.append(f"{ch['meta']['doc_id']} excluded: {why} (step 1)")
            if why == "not_yet_effective":
                d.upcoming.append(ch)

    # Step 2 — explicit supersession by level 1-2 docs
    superseded = set()
    for ch in live:
        m = ch["meta"]
        if int(m.get("authority_level", 5)) <= 2 and m.get("supersedes"):
            for target in str(m["supersedes"]).split(";"):
                target = target.strip()
                if target:
                    superseded.add(target)
                    d.log.append(f"{m['doc_id']} supersedes {target} (step 2)")
    kept2 = []
    for ch in live:
        m = ch["meta"]
        key_doc, key_clause = m["doc_id"], f"{m['doc_id']}#{m.get('section','')}"
        if key_doc in superseded or key_clause in superseded:
            d.dropped.append(ch)
        else:
            kept2.append(ch)

    # Step 3 — authority: drop level-5 if anything official exists; note lower-level conflicts
    officials = [c for c in kept2 if int(c["meta"].get("authority_level", 5)) <= 4]
    if officials:
        for ch in kept2:
            if int(ch["meta"].get("authority_level", 5)) >= 5:
                d.dropped.append(ch)
                d.log.append(f"{ch['meta']['doc_id']} is level 5, informational only (step 3)")
        kept2 = officials
    best = min(int(c["meta"].get("authority_level", 5)) for c in kept2) if kept2 else 5
    top = [c for c in kept2 if int(c["meta"].get("authority_level", 5)) == best]
    for ch in kept2:
        if ch not in top:
            d.log.append(
                f"{ch['meta']['doc_id']} (level {ch['meta'].get('authority_level')}) "
                f"outranked by level {best} (step 3)")

    d.kept = kept2  # keep lower-authority context chunks too; `top` decides facts
    d.top = top

    # Step 4/5 apply when top-level docs genuinely disagree on the same section topic;
    # the caller flags conflict when distinct top docs give contradictory values.
    return d
