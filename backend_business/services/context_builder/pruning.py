from collections import defaultdict
from typing import List, Tuple

from .constants import RELATION_PRIORITY
from .models import Edge


def prune_edges(
    edges: List[Edge], tau: float, top_k: int, max_edges: int
) -> List[Edge]:
    edges = [edge for edge in edges if edge.strength >= tau]

    if not edges:
        return []

    node_edges = defaultdict(list)
    for edge in edges:
        node_edges[edge.source_span_id].append(edge)
        node_edges[edge.target_span_id].append(edge)

    def top_k_score(edge: Edge) -> Tuple:
        distance = abs(edge.target_order - edge.source_order)
        return (edge.strength, -distance)

    kept_edges = set()
    for node_edge_list in node_edges.values():
        sorted_edges = sorted(node_edge_list, key=top_k_score, reverse=True)
        for edge in sorted_edges[:top_k]:
            kept_edges.add(
                (edge.source_span_id, edge.target_span_id, edge.relation_type)
            )

    edges = [
        edge
        for edge in edges
        if (edge.source_span_id, edge.target_span_id, edge.relation_type) in kept_edges
    ]

    if len(edges) > max_edges:

        def truncate_score(edge: Edge) -> Tuple:
            priority = RELATION_PRIORITY.get(edge.relation_type, 0)
            distance = abs(edge.target_order - edge.source_order)
            return (priority, edge.strength, -distance)

        edges = sorted(edges, key=truncate_score, reverse=True)[:max_edges]

    return edges
