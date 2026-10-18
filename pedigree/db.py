import os
from falkordb import FalkorDB


def connect():
    return FalkorDB(
        host=os.environ.get("FALKORDB_HOST", "localhost"),
        port=int(os.environ.get("FALKORDB_PORT", "6379")),
        password=os.environ.get("FALKORDB_PASSWORD") or None,
        socket_timeout=10,
        socket_connect_timeout=5,
    )
