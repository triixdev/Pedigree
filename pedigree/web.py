"""Web layer.

It calls the same functions as the command line (pedigree.service), so the
page and the terminal always agree. Nothing here talks to FalkorDB directly.
Run it with: uvicorn pedigree.web:app
"""
import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import graph as H, memory as M, service as S

log = logging.getLogger("pedigree.web")

app = FastAPI(title="Pedigree", docs_url=None, redoc_url=None, openapi_url=None)

STATIC = Path(__file__).resolve().parent.parent / "static"


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    # the pages load only their own files, so lock everything else out
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store" if request.url.path.startswith("/api/") else "no-cache"
    return response


def _run(fn, *args, **kwargs):
    """Turn expected problems into clear messages and hide everything else."""
    try:
        return fn(*args, **kwargs)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception:
        log.exception("request failed")
        raise HTTPException(
            status_code=503,
            detail="The request could not be completed. Check that FalkorDB is running.",
        )


def _user(uid):
    # the id becomes part of a graph name, so only plain characters are allowed
    if not isinstance(uid, str) or not M._UID.match(uid):
        raise ValueError("invalid user id")
    return uid


def _depth(d):
    d = int(d)
    if not 1 <= d <= 6:
        raise ValueError("depth must be 1 to 6")
    return d


class UserBody(BaseModel):
    user: str = Field(max_length=40)


class DecideBody(UserBody):
    model: str = Field(max_length=200)
    verdict: str = Field(max_length=20)
    note: str = Field(default="", max_length=500)
    depth: int = 4


class RecheckBody(UserBody):
    refresh: bool = True


@app.get("/api/check")
def check(model: str, depth: int = 4, refresh: bool = False):
    return _run(lambda: S.check(H.check_id(model), _depth(depth), refresh))


@app.post("/api/decide")
def decide(body: DecideBody):
    return _run(
        lambda: S.decide(_user(body.user), H.check_id(body.model), body.verdict, body.note, _depth(body.depth))
    )


@app.post("/api/decisions")
def decisions(body: UserBody):
    return _run(lambda: S.decisions(_user(body.user)))


@app.post("/api/recheck")
def recheck(body: RecheckBody):
    return _run(lambda: S.recheck(_user(body.user), body.refresh))


@app.post("/api/forget")
def forget(body: UserBody):
    def go():
        db, _ = S.get()
        M.user_graph(db, _user(body.user)).delete()
        return {"deleted": True}

    return _run(go)


# registered last so the API routes above win
app.mount("/", StaticFiles(directory=str(STATIC), html=True), name="static")
