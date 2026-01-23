from typing import Dict, List, Optional, Tuple
from uuid import uuid4

from .models import Span


def estimate_tokens(text: str) -> int:
    return len(text) // 4 + 1


def pack_bundles(
    spans: List[Span],
    components: Dict[str, List[str]],
    token_limit: int,
    context_run_id: str,
    session_id: str,
) -> Tuple[List[Dict], List[Dict]]:
    span_map = {span.span_id: span for span in spans}

    def component_earliest_time(component_id: str) -> int:
        members = components[component_id]
        times = [span_map[sid].start_ms or 0 for sid in members if sid in span_map]
        return min(times) if times else 0

    sorted_component_ids = sorted(components.keys(), key=component_earliest_time)

    bundles: List[Dict] = []
    bundle_items: List[Dict] = []
    current_bundle_spans: List[Span] = []
    current_tokens = 0

    def finalize_bundle(bundle_spans: List[Span], meta: Optional[Dict] = None):
        if not bundle_spans:
            return

        bundle_id = str(uuid4())
        order_index = len(bundles) + 1

        sorted_spans = sorted(
            bundle_spans, key=lambda span: (span.start_ms or 0, span.order_index)
        )

        bundles.append(
            {
                "bundle_id": bundle_id,
                "context_run_id": context_run_id,
                "session_id": session_id,
                "order_index": order_index,
                "status": "READY",
                "meta": meta or {},
                "spans": sorted_spans,
            }
        )

        for i, span in enumerate(sorted_spans):
            bundle_items.append(
                {
                    "bundle_id": bundle_id,
                    "span_id": span.span_id,
                    "span_ref": f"S{i + 1}",
                    "order_index": i + 1,
                }
            )

    for comp_id in sorted_component_ids:
        member_ids = components[comp_id]
        comp_spans = [span_map[sid] for sid in member_ids if sid in span_map]

        comp_spans = sorted(
            comp_spans, key=lambda span: (span.start_ms or 0, span.order_index)
        )
        comp_tokens = sum(estimate_tokens(span.text) for span in comp_spans)

        if comp_tokens > token_limit:
            if current_bundle_spans:
                finalize_bundle(current_bundle_spans)
                current_bundle_spans = []
                current_tokens = 0

            sub_spans: List[Span] = []
            sub_tokens = 0
            for span in comp_spans:
                span_tokens = estimate_tokens(span.text)
                if sub_tokens + span_tokens > token_limit and sub_spans:
                    finalize_bundle(sub_spans, {"continuation_of": comp_id})
                    sub_spans = []
                    sub_tokens = 0
                sub_spans.append(span)
                sub_tokens += span_tokens

            if sub_spans:
                finalize_bundle(sub_spans, {"continuation_of": comp_id})

        elif current_tokens + comp_tokens > token_limit:
            finalize_bundle(current_bundle_spans)
            current_bundle_spans = comp_spans[:]
            current_tokens = comp_tokens

        else:
            current_bundle_spans.extend(comp_spans)
            current_tokens += comp_tokens

    if current_bundle_spans:
        finalize_bundle(current_bundle_spans)

    return bundles, bundle_items
