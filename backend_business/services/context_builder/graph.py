from collections import defaultdict
from typing import Dict, List, Set, Tuple

from .models import Edge, Span


class UnionFind:
    def __init__(self):
        self.parent = {}
        self.rank = {}

    def find(self, value):
        if value not in self.parent:
            self.parent[value] = value
            self.rank[value] = 0
        if self.parent[value] != value:
            self.parent[value] = self.find(self.parent[value])
        return self.parent[value]

    def union(self, left, right):
        left_root, right_root = self.find(left), self.find(right)
        if left_root == right_root:
            return
        if self.rank[left_root] < self.rank[right_root]:
            left_root, right_root = right_root, left_root
        self.parent[right_root] = left_root
        if self.rank[left_root] == self.rank[right_root]:
            self.rank[left_root] += 1

    def get_components(self) -> Dict[str, List[str]]:
        components = defaultdict(list)
        for node in self.parent:
            root = self.find(node)
            components[root].append(node)
        return dict(components)


def compute_components(
    spans: List[Span],
    edges: List[Edge],
    noise_span_ids: Set[str],
) -> Tuple[Dict[str, List[str]], List[str]]:
    valid_span_ids = {
        span.span_id for span in spans if span.span_id not in noise_span_ids
    }

    uf = UnionFind()
    for span_id in valid_span_ids:
        uf.find(span_id)

    for edge in edges:
        if (
            edge.source_span_id in valid_span_ids
            and edge.target_span_id in valid_span_ids
        ):
            uf.union(edge.source_span_id, edge.target_span_id)

    raw_components = uf.get_components()

    orphan_ids: List[str] = []
    components: Dict[str, List[str]] = {}
    for root, members in raw_components.items():
        if len(members) == 1:
            orphan_ids.append(members[0])
        else:
            components[root] = members

    return components, orphan_ids


def absorb_orphans(
    spans: List[Span],
    components: Dict[str, List[str]],
    orphan_ids: List[str],
) -> Dict[str, List[str]]:
    if not orphan_ids:
        return components

    order_map = {span.span_id: span.order_index for span in spans}
    index_to_span = {span.order_index: span.span_id for span in spans}
    span_to_component = {}
    for root, members in components.items():
        for span_id in members:
            span_to_component[span_id] = root

    misc_component_id = "__MISC__"

    for orphan_id in orphan_ids:
        orphan_order = order_map.get(orphan_id, -1)
        absorbed = False

        for delta in [-1, 1]:
            neighbor_order = orphan_order + delta
            neighbor_id = index_to_span.get(neighbor_order)
            if neighbor_id and neighbor_id in span_to_component:
                target_root = span_to_component[neighbor_id]
                components[target_root].append(orphan_id)
                span_to_component[orphan_id] = target_root
                absorbed = True
                break

        if not absorbed:
            if misc_component_id not in components:
                components[misc_component_id] = []
            components[misc_component_id].append(orphan_id)
            span_to_component[orphan_id] = misc_component_id

    return components
