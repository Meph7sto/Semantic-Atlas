from __future__ import annotations

from backend_inference_ASR.services.asr_service import VibeVoiceASRService


def test_first_output_keeps_multi_item_list():
    value = [{"Start": 0, "Content": "a"}, {"Start": 1, "Content": "b"}]
    assert VibeVoiceASRService._first_output(value) == value


def test_first_output_unwraps_single_item_list():
    value = [{"Start": 0, "Content": "a"}]
    assert VibeVoiceASRService._first_output(value) == value[0]


def test_build_raw_out_from_segments_uses_target_schema():
    segments = [
        {"start": 0.0, "end": 1.2, "speaker": 0, "text": "hello"},
        {"start": 1.2, "end": 2.4, "text": "world"},
    ]
    raw_out = VibeVoiceASRService._build_raw_out_from_segments(segments)
    assert raw_out.startswith("<|im_start|>assistant\n[")
    assert '"Start":0.0' in raw_out
    assert '"End":1.2' in raw_out
    assert '"Speaker":0' in raw_out
    assert '"Content":"hello"' in raw_out
    assert raw_out.endswith("]<|im_end|>")


def test_extract_segments_from_raw_string_requires_structured_json():
    raw = '<|im_start|>assistant\nContent: "It\'s a good thing."<|im_end|>'
    assert VibeVoiceASRService._extract_segments_from_raw_string(raw) == []


def test_normalize_transcription_only_strips_markers():
    value = "<|im_start|>assistant\nIt's a good thing.<|im_end|>\n<|endoftext|>"
    assert VibeVoiceASRService._normalize_transcription_only(value) == "It's a good thing."
