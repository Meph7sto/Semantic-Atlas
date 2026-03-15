from __future__ import annotations

import os

os.environ["SKIP_DB_INIT"] = "1"

from backend_business.services.asr_orchestrator import ASROrchestrator


def test_normalize_remote_payload_from_raw_out_string():
    raw_out = (
        "<|im_start|>assistant\n"
        '[{"Start":0.0,"End":12.27,"Speaker":0,"Content":"第一句"},'
        '{"Start":12.36,"End":26.42,"Speaker":1,"Content":"第二句"}]'
        "<|im_end|>"
    )
    payload = {"raw_out": raw_out}

    text, segments, metadata, remote_request_id = (
        ASROrchestrator._normalize_remote_transcribe_payload(payload=payload)
    )

    assert remote_request_id is None
    assert "第一句" in text
    assert "第二句" in text
    assert len(segments) == 2
    assert segments[0]["start"] == 0.0
    assert segments[0]["end"] == 12.27
    assert segments[0]["speaker"] == 0
    assert segments[0]["text"] == "第一句"
    assert metadata.get("normalized_from_remote") is True
    assert "raw_out" in metadata


def test_normalize_remote_payload_prefers_structured_fields():
    payload = {
        "remote_request_id": "rid-123",
        "transcript": "结构化文本",
        "segments": [{"Start": 1, "End": 2, "Content": "结构化文本"}],
        "result_metadata": {"model": "vibevoice"},
    }

    text, segments, metadata, remote_request_id = (
        ASROrchestrator._normalize_remote_transcribe_payload(payload=payload)
    )

    assert remote_request_id == "rid-123"
    assert text == "结构化文本"
    assert len(segments) == 1
    assert segments[0]["start"] == 1.0
    assert segments[0]["end"] == 2.0
    assert segments[0]["text"] == "结构化文本"
    assert metadata["model"] == "vibevoice"


def test_normalize_remote_payload_handles_raw_json_in_text_field():
    payload = {
        "text": '<|im_start|>assistant\n[{"Start":0.0,"End":1.0,"Content":"你好"}]<|im_end|>'
    }

    text, segments, metadata, remote_request_id = (
        ASROrchestrator._normalize_remote_transcribe_payload(payload=payload)
    )

    assert remote_request_id is None
    assert text == "你好"
    assert len(segments) == 1
    assert segments[0]["start"] == 0.0
    assert segments[0]["end"] == 1.0
    assert segments[0]["text"] == "你好"
    assert metadata.get("normalized_from_remote") is True
    assert "raw_out" in metadata


def test_normalize_remote_payload_ignores_error_html_body():
    payload = {}
    raw_body_text = "<html><body>502 Bad Gateway</body></html>"

    text, segments, metadata, remote_request_id = (
        ASROrchestrator._normalize_remote_transcribe_payload(
            payload=payload,
            raw_body_text=raw_body_text,
        )
    )

    assert remote_request_id is None
    assert text == ""
    assert segments == []
    assert metadata.get("normalized_from_remote") is True
    assert metadata.get("raw_out") == raw_body_text


def test_normalize_remote_payload_accepts_output_with_endoftext_marker():
    raw_out = (
        "<|im_start|>assistant\n"
        '[{"Start":0.0,"End":1.0,"Speaker":0,"Content":"你好"}]'
        "<|im_end|>\n<|endoftext|>"
    )
    payload = {"raw_out": raw_out}

    text, segments, metadata, remote_request_id = (
        ASROrchestrator._normalize_remote_transcribe_payload(payload=payload)
    )

    assert remote_request_id is None
    assert text == "你好"
    assert len(segments) == 1
    assert segments[0]["start"] == 0.0
    assert segments[0]["end"] == 1.0
    assert segments[0]["speaker"] == 0
    assert segments[0]["text"] == "你好"
    assert metadata.get("normalized_from_remote") is True
    assert metadata.get("raw_out") == raw_out


def test_normalize_remote_payload_from_decoded_json_field():
    payload = {
        "decoded_json": [
            {"Start": 0.0, "End": 1.0, "Speaker": 0, "Content": "第一句"},
            {"Start": 1.0, "End": 2.4, "Content": "第二句"},
        ]
    }

    text, segments, metadata, remote_request_id = (
        ASROrchestrator._normalize_remote_transcribe_payload(payload=payload)
    )

    assert remote_request_id is None
    assert text == "第一句\n第二句"
    assert len(segments) == 2
    assert segments[0]["speaker"] == 0
    assert segments[1]["start"] == 1.0
    assert isinstance(metadata.get("decoded_json"), list)
