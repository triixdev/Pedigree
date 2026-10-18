import uuid

import pytest

from pedigree.db import connect
from pedigree import graph as H


@pytest.fixture()
def g():
    graph = connect().select_graph("test_" + uuid.uuid4().hex[:8])
    H.init(graph)
    yield graph
    graph.delete()