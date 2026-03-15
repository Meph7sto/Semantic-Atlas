from typing import Dict, Generator, List, Tuple

from .constants import RELATION_TYPES
from .models import Edge, Span


def generate_windows(
    spans: List[Span],
    window_size: int,
    step_size: int,
) -> Generator[Tuple[List[Span], Dict[str, str]], None, None]:
    n = len(spans)
    if n == 0:
        return

    start = 0
    while start < n:
        end = min(start + window_size, n)
        window_spans = spans[start:end]

        ref_map: Dict[str, str] = {}
        for i, span in enumerate(window_spans):
            ref_map[span.span_id] = f"S{i + 1}"

        yield window_spans, ref_map

        if end >= n:
            break
        start += step_size


def parse_window_edges(
    raw_links: List[Dict],
    ref_map: Dict[str, str],
    window_spans: List[Span],
) -> List[Edge]:
    reverse_map = {ref: span_id for span_id, ref in ref_map.items()}
    order_map = {s.span_id: s.order_index for s in window_spans}

    edge_map: Dict[tuple[str, str, str], Edge] = {}

    for link in raw_links:
        source_ref = link.get("source", "")
        target_ref = link.get("target", "")
        rel_type = link.get("type", "")
        strength = link.get("strength", 0)
        note = link.get("note", "")

        source_id = reverse_map.get(source_ref)
        target_id = reverse_map.get(target_ref)

        if not source_id or not target_id:
            continue

        if source_id == target_id:
            continue

        if rel_type not in RELATION_TYPES:
            continue

        strength = max(0.0, min(1.0, float(strength)))

        key = (source_id, target_id, rel_type)
        candidate = Edge(
            source_span_id=source_id,
            target_span_id=target_id,
            relation_type=rel_type,
            strength=strength,
            note=note,
            source_order=order_map.get(source_id, 0),
            target_order=order_map.get(target_id, 0),
        )
        existing = edge_map.get(key)
        if existing is None or candidate.strength >= existing.strength:
            edge_map[key] = candidate

    return list(edge_map.values())
