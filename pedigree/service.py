"""One place that ties the pieces together.

The command line and the web app both call these functions so the
behavior is identical. The hub graph holds public model facts that every
user shares. Each user's own decisions live in a separate graph.
"""
import os

from . import graph as H, hf, memory as M
from .db import connect

_db = None
_hub = None


def get():
    global _db, _hub
    if _db is None:
        _db = connect()
        _hub = _db.select_graph(os.environ.get("PEDIGREE_HUB", "pedigree_hub"))
        H.init(_hub)
    return _db, _hub


def ingest(model_id, depth=4, max_nodes=150):
    _, hub = get()
    return H.crawl(hub, hf.fetch_model, hf.fetch_dataset, model_id, depth, max_nodes)


def check(model_id, depth=4, refresh=False):
    _, hub = get()
    if refresh or not H.is_ingested(hub, model_id):
        ingest(model_id, depth)
    if not H.is_ingested(hub, model_id):
        raise LookupError(f"{model_id} could not be fetched (not found, gated or private)")
    return {"model": model_id, "depth": depth,
            "flags": H.flags(hub, model_id, depth),
            "lineage": H.lineage(hub, model_id, depth)}


def decide(user_id, model_id, verdict, note="", depth=4):
    db, hub = get()
    return M.record_decision(db, hub, user_id, model_id, verdict, note, depth)


def decisions(user_id):
    db, _ = get()
    return [{k: v for k, v in d.items() if k != "snapshot"} for d in M.latest_decisions(db, user_id)]


def recheck(user_id, refresh=True):
    db, hub = get()
    fetch_again = (lambda model_id: ingest(model_id)) if refresh else None
    return M.recheck(db, hub, user_id, refresh=fetch_again)