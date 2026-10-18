from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..config import get_settings
from ..db import GraphStore, ro
from ..graph.aliases import generate_candidates
from ..graph.clusters import recompute_clusters
from ..schema import ensure_schema
from .common import NodeRow, load_rows
from .gem import parse_gem
from .gleif import parse_gleif_rr
from .opensanctions import LICENCE as OS_LICENCE, parse_opensanctions


def build_real(graph_name: str, paths: dict[str, str | Path], snapshot: str) -> dict:
    """Build a local person-free facts graph from pinned source files only."""
    settings = get_settings(); store = GraphStore(settings); graph = store._db.select_graph(graph_name)
    ensure_schema(graph)
    nodes, designations, dropped_os = parse_opensanctions(paths["os"])
    programs = {edge.target: edge.properties["authority"] for edge in designations}
    nodes.extend(NodeRow(pid, "Program", authority, {"authority": authority, "src": "opensanctions:program", "src_record": authority}) for pid, authority in programs.items())
    load_rows(graph, nodes, designations, snapshot, OS_LICENCE)
    leis = {node.properties.get("lei") for node in nodes if node.properties.get("lei")}
    gleif = parse_gleif_rr(paths["gleif"], leis)
    # RR is a control/consolidation feed. Parent LEIs absent from the sanctions
    # file are intentionally not invented: an edge requires both attributed nodes.
    loaded_gleif = load_rows(graph, [], gleif, snapshot, "CC0 1.0 (GLEIF)")
    gem_nodes, gem_edges, dropped_gem = ([], [], 0)
    gem_path = paths.get("gem")
    if gem_path and Path(gem_path).exists():
        gem_nodes, gem_edges, dropped_gem = parse_gem(gem_path)
        load_rows(graph, gem_nodes, gem_edges, snapshot, "CC BY 4.0 (GEM)")
    counts = {"opensanctions_nodes": len(nodes), "designations": len(designations), "gleif_edges": len(gleif),
              "gem_nodes": len(gem_nodes), "gem_edges": len(gem_edges), "dropped_persons": dropped_os + dropped_gem,
              'gleif_edges_loaded': loaded_gleif['edges'],
              'gleif_edges_missing_endpoints': loaded_gleif['skipped_missing_endpoints'],
              'scope_note': 'Exact LEI intersection with the loaded corporate sanctions slice; missing GLEIF endpoint metadata is excluded.',
              "gem_status": "loaded" if gem_path and Path(gem_path).exists() else "not loaded: public FtM export returned HTTP 404 during source research on 2026-10-15"}
    # Candidates are advisory only and must never change the legal graph.
    counts['candidates'] = generate_candidates(graph)
    counts['clusters'] = recompute_clusters(graph)
    counts['person_nodes'] = ro(graph, 'MATCH (p:Person) RETURN count(p) AS n')[0]['n']
    if counts['person_nodes']:
        raise ValueError('Real-data graph contains Person nodes')
    return counts


def main():
    parser = argparse.ArgumentParser(description="Load a local person-free real-data facts graph")
    parser.add_argument("--os", required=True); parser.add_argument("--gleif", required=True)
    parser.add_argument("--gem"); parser.add_argument("--snapshot", required=True); parser.add_argument("--graph")
    args = parser.parse_args(); graph = args.graph or f"st_facts_real_{args.snapshot}"
    print(json.dumps(build_real(graph, vars(args), args.snapshot), indent=2))


if __name__ == "__main__": main()
