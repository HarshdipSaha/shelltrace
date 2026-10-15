"""Shared fixtures; application modules are imported only when fixtures run."""

import os
import uuid

import pytest


@pytest.fixture(scope="session")
def store():
    from shelltrace.config import get_settings
    from shelltrace.db import GraphStore

    graph_store = GraphStore(get_settings())
    if not graph_store.ping():
        if os.getenv("ST_REQUIRE_DB") == "1":
            pytest.fail("FalkorDB not reachable and ST_REQUIRE_DB=1")
        pytest.skip("FalkorDB not reachable")
    return graph_store


@pytest.fixture(scope="session")
def golden_ws(store) -> str:
    from shelltrace.seed.synthetic import load_synthetic

    workspace = f"t_{uuid.uuid4().hex[:8]}"
    store.provision(workspace, seeder=load_synthetic, force_seed=True)
    try:
        yield workspace
    finally:
        store.drop(workspace)
