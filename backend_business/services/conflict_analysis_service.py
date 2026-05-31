import asyncio
import json
import re
from dataclasses import dataclass
from typing import Any

import aiohttp

from backend_business.api.routers.schemas.conflict_schemas import (
    ConflictRequirementSnapshot,
)
from backend_business.services.ai_proxy import AIProxy

_TIME_WORDS = ("秒", "分钟", "小时", "天", "工作日", "ms")
_NEGATION_WORDS = ("禁止", "不得", "不能", "不可", "不允许")
_ALLOW_WORDS = ("允许", "可以", "支持", "能够")
_MANDATORY_WORDS = ("必须", "应当", "需要", "需")
_ORDER_WORDS = ("之前", "之后", "先", "后", "立即")
_NUMBER_PATTERN = re.compile(r"\d+(?:\.\d+)?")
_TOKEN_PATTERN = re.compile(r"[\u4e00-\u9fffA-Za-z0-9_]+")


@dataclass(frozen=True)
class CandidatePair:
    requirement_a: ConflictRequirementSnapshot
    requirement_b: ConflictRequirementSnapshot
    bucket_key: str
    score: int
    candidate_reason: str


class ConflictAnalysisService:
    def __init__(self, ai_proxy: AIProxy):
        self._ai_proxy = ai_proxy

    async def analyze(
        self,
        requirements: list[ConflictRequirementSnapshot],
        *,
        model: str,
        use_thinking_mode: bool,
        conflict_concurrency: int,
        max_candidates_per_bucket: int,
    ) -> dict[str, Any]:
        buckets = self._build_buckets(requirements)
        candidates = self._build_candidates(buckets, max_candidates_per_bucket)
        applied_concurrency = max(1, min(int(conflict_concurrency or 1), 8, len(candidates) or 1))

        if not candidates:
            return {
                "summary": {
                    "scope_count": len(requirements),
                    "bucket_count": len(buckets),
                    "candidate_count": 0,
                    "pairs_evaluated": 0,
                    "completed_pairs": 0,
                    "failed_pairs": 0,
                    "conflict_count": 0,
                    "suspected_count": 0,
                    "requested_concurrency": int(conflict_concurrency or 1),
                    "applied_concurrency": 0,
                },
                "conflicts": [],
            }

        semaphore = asyncio.Semaphore(applied_concurrency)
        timeout = self._ai_proxy._resolve_tools_aiohttp_timeout()
        connector = aiohttp.TCPConnector(limit=max(6, applied_concurrency * 2))
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            tasks = [
                asyncio.create_task(
                    self._evaluate_candidate(
                        idx,
                        candidate,
                        session=session,
                        semaphore=semaphore,
                        model=model,
                        use_thinking_mode=use_thinking_mode,
                    )
                )
                for idx, candidate in enumerate(candidates)
            ]

            ordered_results: list[dict[str, Any] | None] = [None] * len(candidates)
            completed_pairs = 0
            failed_pairs = 0
            for task in asyncio.as_completed(tasks):
                idx, result = await task
                ordered_results[idx] = result
                completed_pairs += 1
                if result.get("status") == "error":
                    failed_pairs += 1

        conflicts = []
        suspected_count = 0
        conflict_count = 0
        for result in ordered_results:
            if not result or result.get("status") == "error":
                continue
            verdict = result.get("verdict", "clear")
            if verdict == "confirmed":
                conflicts.append(result)
                conflict_count += 1
            elif verdict == "suspected":
                conflicts.append(result)
                suspected_count += 1

        return {
            "summary": {
                "scope_count": len(requirements),
                "bucket_count": len(buckets),
                "candidate_count": len(candidates),
                "pairs_evaluated": len(candidates),
                "completed_pairs": completed_pairs,
                "failed_pairs": failed_pairs,
                "conflict_count": conflict_count,
                "suspected_count": suspected_count,
                "requested_concurrency": int(conflict_concurrency or 1),
                "applied_concurrency": applied_concurrency,
            },
            "conflicts": conflicts,
        }

    def _build_buckets(
        self,
        requirements: list[ConflictRequirementSnapshot],
    ) -> dict[str, list[ConflictRequirementSnapshot]]:
        buckets: dict[str, list[ConflictRequirementSnapshot]] = {}
        for req in requirements:
            keys = []
            normalized_level = str(req.level or "L1").strip().upper() or "L1"
            if normalized_level == "L4" and req.source_top_id:
                keys.append(f"l4-top:{req.source_top_id}")
            if req.parent_id:
                keys.append(f"parent:{req.parent_id}")
            if req.component:
                keys.append(f"component:{req.component.strip()}")
            if req.module:
                keys.append(f"module:{req.module.strip()}")
            if not keys:
                keys.append(f"level:{normalized_level}")
            for key in keys:
                buckets.setdefault(key, []).append(req)
        return {key: values for key, values in buckets.items() if len(values) >= 2}

    def _build_candidates(
        self,
        buckets: dict[str, list[ConflictRequirementSnapshot]],
        max_candidates_per_bucket: int,
    ) -> list[CandidatePair]:
        candidates_by_key: dict[tuple[str, str], CandidatePair] = {}
        for bucket_key, items in buckets.items():
            scored_pairs: list[CandidatePair] = []
            for idx, req_a in enumerate(items):
                for req_b in items[idx + 1 :]:
                    if str(req_a.level or "").strip().upper() != str(req_b.level or "").strip().upper():
                        continue
                    score, reason = self._score_pair(req_a, req_b)
                    if score <= 0:
                        continue
                    pair_key = tuple(sorted((req_a.requirement_id, req_b.requirement_id)))
                    candidate = CandidatePair(
                        requirement_a=req_a,
                        requirement_b=req_b,
                        bucket_key=bucket_key,
                        score=score,
                        candidate_reason=reason,
                    )
                    existing = candidates_by_key.get(pair_key)
                    if existing is None or candidate.score > existing.score:
                        candidates_by_key[pair_key] = candidate
                    scored_pairs.append(candidate)
            if scored_pairs:
                scored_pairs.sort(key=lambda item: (-item.score, item.requirement_a.requirement_id, item.requirement_b.requirement_id))
                for candidate in scored_pairs[:max_candidates_per_bucket]:
                    pair_key = tuple(sorted((candidate.requirement_a.requirement_id, candidate.requirement_b.requirement_id)))
                    existing = candidates_by_key.get(pair_key)
                    if existing is None or candidate.score > existing.score:
                        candidates_by_key[pair_key] = candidate
        ordered = sorted(
            candidates_by_key.values(),
            key=lambda item: (-item.score, item.bucket_key, item.requirement_a.requirement_id, item.requirement_b.requirement_id),
        )
        return ordered

    def _score_pair(
        self,
        req_a: ConflictRequirementSnapshot,
        req_b: ConflictRequirementSnapshot,
    ) -> tuple[int, str]:
        text_a = req_a.text.strip()
        text_b = req_b.text.strip()
        tokens_a = self._extract_tokens(text_a)
        tokens_b = self._extract_tokens(text_b)
        overlap = tokens_a & tokens_b
        score = 0
        reasons: list[str] = []

        if overlap:
            score += min(4, len(overlap))
            reasons.append("实体/动作重叠")
        if self._contains_numbers(text_a) and self._contains_numbers(text_b):
            score += 3
            reasons.append("均含数值约束")
        if self._contains_any(text_a, _TIME_WORDS) and self._contains_any(text_b, _TIME_WORDS):
            score += 3
            reasons.append("均含时间约束")
        if self._contains_any(text_a, _ORDER_WORDS) and self._contains_any(text_b, _ORDER_WORDS):
            score += 3
            reasons.append("均含时序约束")
        if self._has_polarity_tension(text_a, text_b):
            score += 5
            reasons.append("存在极性张力")
        if req_a.level == req_b.level:
            score += 2
            reasons.append("同层级需求")
        if req_a.parent_id and req_a.parent_id == req_b.parent_id:
            score += 3
            reasons.append("同父需求")
        if req_a.source_top_id and req_a.source_top_id == req_b.source_top_id:
            score += 3
            reasons.append("同顶层来源")

        return score, "、".join(reasons[:3]) or "同范围候选"

    async def _evaluate_candidate(
        self,
        idx: int,
        candidate: CandidatePair,
        *,
        session: aiohttp.ClientSession,
        semaphore: asyncio.Semaphore,
        model: str,
        use_thinking_mode: bool,
    ) -> tuple[int, dict[str, Any]]:
        async with semaphore:
            try:
                result = await self._judge_pair(
                    candidate,
                    session=session,
                    model=model,
                    use_thinking_mode=use_thinking_mode,
                )
                return idx, result
            except Exception as exc:
                return idx, {
                    "status": "error",
                    "requirement_id_a": candidate.requirement_a.requirement_id,
                    "requirement_id_b": candidate.requirement_b.requirement_id,
                    "error": str(exc),
                    "candidate_reason": candidate.candidate_reason,
                }

    async def _judge_pair(
        self,
        candidate: CandidatePair,
        *,
        session: aiohttp.ClientSession,
        model: str,
        use_thinking_mode: bool,
    ) -> dict[str, Any]:
        system_prompt = (
            "你是严格的需求冲突裁决器。"
            "只判断两条同级需求是否存在不能同时满足的冲突。"
            "不要把上下位细化、补充、拆分误判为冲突。"
            "输出必须是 JSON，字段固定为"
            " verdict, conflict_type, description, evidence_a, evidence_b, confidence。"
            "verdict 只能是 confirmed、suspected、clear。"
            "conflict_type 只能是 object_property、logic_timing、terminology、fr_nfr、other。"
        )
        prompt = (
            f"候选原因：{candidate.candidate_reason}\n"
            f"需求A(ID={candidate.requirement_a.requirement_id}, Level={candidate.requirement_a.level})：{candidate.requirement_a.text}\n"
            f"需求B(ID={candidate.requirement_b.requirement_id}, Level={candidate.requirement_b.level})：{candidate.requirement_b.text}\n"
            "请输出 JSON。"
        )
        content = await self._ai_proxy.context_builder_completion_async(
            prompt=prompt,
            system_prompt=system_prompt,
            max_new_tokens=1200,
            model=model,
            thinking_enabled=use_thinking_mode,
            session=session,
        )
        parsed = self._parse_json_payload(content)
        verdict = str(parsed.get("verdict") or "").strip().lower() or "clear"
        if verdict not in {"confirmed", "suspected", "clear"}:
            verdict = "confirmed" if parsed.get("is_conflict") else "clear"
        conflict_type = str(parsed.get("conflict_type") or "").strip().lower() or "other"
        if conflict_type not in {"object_property", "logic_timing", "terminology", "fr_nfr", "other"}:
            conflict_type = "other"
        description = str(parsed.get("description") or "").strip() or str(parsed.get("reason") or "").strip()
        evidence_a = str(parsed.get("evidence_a") or "").strip() or candidate.requirement_a.text[:120]
        evidence_b = str(parsed.get("evidence_b") or "").strip() or candidate.requirement_b.text[:120]
        confidence = parsed.get("confidence")
        try:
            confidence_value = max(0.0, min(1.0, float(confidence)))
        except (TypeError, ValueError):
            confidence_value = 0.8 if verdict == "confirmed" else 0.55 if verdict == "suspected" else 0.2
        return {
            "status": "ok",
            "requirement_id_a": candidate.requirement_a.requirement_id,
            "requirement_id_b": candidate.requirement_b.requirement_id,
            "requirement_a_text": candidate.requirement_a.text,
            "requirement_b_text": candidate.requirement_b.text,
            "verdict": verdict,
            "conflict_type": conflict_type,
            "description": description or "未提供说明",
            "evidence_a": evidence_a,
            "evidence_b": evidence_b,
            "confidence": confidence_value,
            "candidate_reason": candidate.candidate_reason,
            "bucket_key": candidate.bucket_key,
            "is_conflict": verdict in {"confirmed", "suspected"},
            "raw_response": content,
        }

    @staticmethod
    def _extract_tokens(text: str) -> set[str]:
        return {
            token.lower()
            for token in _TOKEN_PATTERN.findall(text or "")
            if len(token.strip()) >= 2
        }

    @staticmethod
    def _contains_numbers(text: str) -> bool:
        return bool(_NUMBER_PATTERN.search(text or ""))

    @staticmethod
    def _contains_any(text: str, words: tuple[str, ...]) -> bool:
        return any(word in (text or "") for word in words)

    def _has_polarity_tension(self, text_a: str, text_b: str) -> bool:
        a_negative = self._contains_any(text_a, _NEGATION_WORDS)
        b_negative = self._contains_any(text_b, _NEGATION_WORDS)
        a_allow = self._contains_any(text_a, _ALLOW_WORDS)
        b_allow = self._contains_any(text_b, _ALLOW_WORDS)
        a_mandatory = self._contains_any(text_a, _MANDATORY_WORDS)
        b_mandatory = self._contains_any(text_b, _MANDATORY_WORDS)
        return (
            (a_negative and (b_allow or b_mandatory))
            or (b_negative and (a_allow or a_mandatory))
        )

    @staticmethod
    def _parse_json_payload(text: str) -> dict[str, Any]:
        raw = str(text or "").strip()
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            match = re.search(r"\{[\s\S]*\}", raw)
            if match:
                try:
                    return json.loads(match.group(0))
                except json.JSONDecodeError:
                    return {}
        return {}
