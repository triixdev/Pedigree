"""Per-user memory.

Every user gets their own graph named user_<id>, so one person's reviews
can never show up in another person's results. When you save a decision
we also store a snapshot of the lineage as it looked at that moment.
Later we compare a fresh snapshot with the saved one to say what changed.
"""
import json
import re
import time

from . import graph as H

_UID = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
VERDICTS = {"approved", "rejected", "needs_review"}


def user_graph(db, uid):
    # the id becomes part of a graph name so keep it to plain characters
    if not isinstance(uid, str) or not _UID.match(uid):
        raise ValueError("invalid user id")
    g = db.select_graph(f"user_{uid}")
    try:
        g.query("CREATE INDEX FOR (r:Reviewed) ON (r.id)")
    except Exception:
        pass  # already exists
    return g


def record_decision(db, hub, uid, model_id, verdict, note="", depth=4):
    if verdict not in VERDICTS:
        raise ValueError(f"verdict must be one of {sorted(VERDICTS)}")
    snap = H.snapshot(hub, model_id, depth)
    to_review = len([f for f in H.flags(hub, model_id, depth) if f["severity"] == "review"])
    ug = user_graph(db, uid)
    ug.query(
        "MERGE (r:Reviewed {id:$m}) "
        "CREATE (r)-[:HAS_DECISION]->(:Decision "
        "{verdict:$v, note:$n, at:$t, fingerprint:$f, snapshot:$s, review_flags:$k, depth:$d})",
        {"m": H.check_id(model_id), "v": verdict, "n": note[:500], "t": time.time_ns(),
         "f": H.fingerprint(snap), "s": json.dumps(snap), "k": to_review, "d": int(depth)},
    )
    return {"model": model_id, "verdict": verdict, "review_flags": to_review,
            "fingerprint": H.fingerprint(snap)}


def latest_decisions(db, uid):
    ug = user_graph(db, uid)
    rows = ug.query(
        "MATCH (r:Reviewed)-[:HAS_DECISION]->(d:Decision) "
        "RETURN r.id, d.verdict, d.note, d.at, d.fingerprint, d.snapshot, d.depth ORDER BY d.at"
    ).result_set
    latest = {}  # rows are oldest first so a later decision overwrites an earlier one
    for mid, verdict, note, at, fp, snap, depth in rows:
        latest[mid] = {"model": mid, "verdict": verdict, "note": note, "at": at,
                       "fingerprint": fp, "snapshot": json.loads(snap), "depth": depth}
    return list(latest.values())


def recheck(db, hub, uid, refresh=None):
    """refresh(model_id) fetches fresh data first. Leave it out to compare with what is stored."""
    out = []
    for d in latest_decisions(db, uid):
        if refresh:
            refresh(d["model"])
        new = H.snapshot(hub, d["model"], d["depth"])
        changed = H.fingerprint(new) != d["fingerprint"]
        review_now = None
        if changed:
            review_now = len([f for f in H.flags(hub, d["model"], d["depth"]) if f["severity"] == "review"])
        out.append({"model": d["model"], "your_verdict": d["verdict"], "changed": changed,
                    "changes": H.diff(d["snapshot"], new) if changed else [],
                    "review_flags_now": review_now})
    return out