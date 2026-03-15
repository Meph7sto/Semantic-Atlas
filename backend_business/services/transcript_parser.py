import hashlib
import json
import re
from typing import Any, Dict, List, Optional, Tuple


_TIMESTAMP_PATTERN = re.compile(
    r"^\s*\[(?P<start>[^-\~—–]+?)\s*[-~—–]\s*(?P<end>[^\]]+?)\]\s*(?P<rest>.*)$"
)


def _normalize_text(text: str) -> str:
    text = text.replace("：", ":")
    text = re.sub(r"\s+", " ", text.strip())
    return text


def _parse_time_to_ms(value: str) -> Optional[int]:
    value = value.strip()
    if not value:
        return None
    if re.fullmatch(r"\d+", value):
        return int(value)
    parts = value.split(":")
    if not all(part.strip().isdigit() for part in parts):
        return None
    nums = [int(part) for part in parts]
    if len(nums) == 3:
        hours, minutes, seconds = nums
    elif len(nums) == 2:
        hours = 0
        minutes, seconds = nums
    elif len(nums) == 1:
        hours = 0
        minutes = 0
        seconds = nums[0]
    else:
        return None
    return ((hours * 60 + minutes) * 60 + seconds) * 1000


def _is_likely_speaker(token: str) -> bool:
    if not token or len(token) > 20:
        return False
    return bool(re.fullmatch(r"[A-Za-z0-9_\u4e00-\u9fff]+", token))


def _split_speaker_text(rest: str) -> Tuple[Optional[str], str]:
    rest = rest.strip()
    if not rest:
        return None, ""
    for delim in (":", "："):
        if delim in rest:
            speaker, text = rest.split(delim, 1)
            speaker = speaker.strip()
            text = text.strip()
            if speaker:
                return speaker, text
            return None, text
    match = re.match(r"^(\S+)\s+(.*)$", rest)
    if match and _is_likely_speaker(match.group(1)):
        return match.group(1), match.group(2).strip()
    return None, rest


def _is_meaningful_text(text: str) -> bool:
    return bool(re.search(r"[A-Za-z0-9\u4e00-\u9fff]", text))


def _build_span_id(
    session_id: str,
    start_ms: Optional[int],
    end_ms: Optional[int],
    speaker: str,
    normalized_text: str,
) -> str:
    key = (
        f"{session_id}|"
        f"{start_ms if start_ms is not None else 'null'}|"
        f"{end_ms if end_ms is not None else 'null'}|"
        f"{speaker}|{normalized_text}"
    )
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def parse_transcript_to_spans(
    transcript_text: str,
    session_id: str,
    options: Optional[Dict[str, Any]] = None,
) -> Tuple[List[Dict[str, Any]], List[str], Dict[str, Any]]:
    options = options or {}
    estimate_missing = bool(options.get("estimate_timestamps_if_missing", True))
    default_span_ms = int(options.get("default_span_ms", 8000))
    if default_span_ms <= 0:
        default_span_ms = 8000

    lines = transcript_text.splitlines()
    spans: List[Dict[str, Any]] = []
    warnings: List[str] = []
    timestamped_count = 0
    speakers = set()
    previous_end: Optional[int] = None

    span_index = 0
    for line_no, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line:
            continue
        if not _is_meaningful_text(line):
            continue

        start_ms: Optional[int] = None
        end_ms: Optional[int] = None
        rest = line
        line_warnings: List[str] = []
        has_timestamp = False

        match = _TIMESTAMP_PATTERN.match(line)
        if match:
            rest = match.group("rest").strip()
            start_raw = match.group("start")
            end_raw = match.group("end")
            start_ms = _parse_time_to_ms(start_raw)
            end_ms = _parse_time_to_ms(end_raw)
            if start_ms is None or end_ms is None:
                line_warnings.append(f"line {line_no}: invalid timestamp")
                start_ms = None
                end_ms = None
            else:
                has_timestamp = True
                timestamped_count += 1
                if start_ms > end_ms:
                    line_warnings.append(f"line {line_no}: start_ms greater than end_ms")
                if previous_end is not None and start_ms < previous_end:
                    line_warnings.append(f"line {line_no}: overlapping timestamp with previous span")
                previous_end = end_ms

        speaker, text = _split_speaker_text(rest)
        if not text or not _is_meaningful_text(text):
            line_warnings.append(f"line {line_no}: empty content")
            if line_warnings:
                warnings.extend(line_warnings)
            continue

        if not speaker:
            speaker = "unknown"
            line_warnings.append(f"line {line_no}: missing speaker")

        if not has_timestamp:
            if estimate_missing:
                start_ms = span_index * default_span_ms
                end_ms = start_ms + default_span_ms
            else:
                start_ms = None
                end_ms = None

        normalized_text = _normalize_text(text)
        span_id = _build_span_id(session_id, start_ms, end_ms, speaker, normalized_text)

        parse_source = "timestamped" if has_timestamp else ("estimated" if estimate_missing else "plain")
        meta = {
            "line_no": line_no,
            "parse_source": parse_source,
            "warnings": line_warnings,
        }

        span = {
            "span_id": span_id,
            "session_id": session_id,
            "start_ms": start_ms,
            "end_ms": end_ms,
            "speaker": speaker,
            "text": text.strip(),
            "asr_confidence": None,
            "meta_json": json.dumps(meta, ensure_ascii=False),
        }
        spans.append(span)
        span_index += 1

        if speaker != "unknown":
            speakers.add(speaker)
        if line_warnings:
            warnings.extend(line_warnings)

    stats = {
        "has_timestamp_ratio": (timestamped_count / len(spans)) if spans else 0,
        "speaker_count": len(speakers),
    }
    return spans, warnings, stats
