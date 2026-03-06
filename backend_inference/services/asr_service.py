from __future__ import annotations

import logging
import os
import subprocess
import tempfile
import time
from typing import Any

from core.config import settings

logger = logging.getLogger(__name__)


class VibeVoiceASRService:
    def __init__(self):
        self._pipe = None
        self._load_error: str | None = None

    @property
    def model_id(self) -> str:
        return settings.VIBEVOICE_ASR_MODEL

    @property
    def is_loaded(self) -> bool:
        return self._pipe is not None

    def _load_if_needed(self) -> None:
        if self._pipe is not None:
            return
        try:
            from transformers import pipeline
        except Exception as exc:
            self._load_error = f"transformers unavailable: {exc}"
            raise RuntimeError(self._load_error)

        try:
            logger.info("loading VibeVoice ASR model: %s", self.model_id)
            self._pipe = pipeline(
                task="automatic-speech-recognition",
                model=self.model_id,
                trust_remote_code=True,
            )
        except Exception as exc:
            self._load_error = f"failed to load model {self.model_id}: {exc}"
            raise RuntimeError(self._load_error)

    def warmup(self) -> None:
        self._load_if_needed()

    def health(self) -> dict[str, Any]:
        if self._load_error and not self.is_loaded:
            return {
                "available": False,
                "model": self.model_id,
                "detail": self._load_error,
                "loaded": False,
            }
        return {
            "available": True,
            "model": self.model_id,
            "detail": "ok",
            "loaded": self.is_loaded,
        }

    @staticmethod
    def _extract_audio_if_video(input_path: str, suffix: str) -> str:
        if suffix != "mp4":
            return input_path
        fd, wav_path = tempfile.mkstemp(suffix=".wav", prefix="asr_mp4_")
        os.close(fd)
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            input_path,
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            wav_path,
        ]
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except FileNotFoundError as exc:
            raise RuntimeError("ffmpeg not found, cannot transcribe mp4") from exc
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or b"").decode("utf-8", errors="ignore")
            raise RuntimeError(f"ffmpeg extraction failed: {detail[:500]}")
        return wav_path

    def transcribe(
        self,
        file_bytes: bytes,
        filename: str,
        content_type: str,
    ) -> dict[str, Any]:
        self._load_if_needed()
        if self._pipe is None:
            raise RuntimeError("ASR pipeline unavailable")

        suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
        tmp_in = tempfile.NamedTemporaryFile(delete=False, suffix=f".{suffix}")
        tmp_in.write(file_bytes)
        tmp_in.flush()
        tmp_in.close()

        audio_path = tmp_in.name
        needs_cleanup_audio = False
        start = time.time()
        try:
            audio_path = self._extract_audio_if_video(tmp_in.name, suffix)
            needs_cleanup_audio = audio_path != tmp_in.name
            result = self._pipe(audio_path)
            text = str(result.get("text") or "").strip()
            chunks = result.get("chunks") or []
            segments = []
            if isinstance(chunks, list):
                for item in chunks:
                    if not isinstance(item, dict):
                        continue
                    ts = item.get("timestamp") or ()
                    start_sec = ts[0] if isinstance(ts, (list, tuple)) and len(ts) > 0 else None
                    end_sec = ts[1] if isinstance(ts, (list, tuple)) and len(ts) > 1 else None
                    segments.append(
                        {
                            "start": start_sec,
                            "end": end_sec,
                            "text": str(item.get("text") or "").strip(),
                        }
                    )
            latency = round(time.time() - start, 3)
            return {
                "text": text,
                "segments": segments,
                "metadata": {
                    "model": self.model_id,
                    "source_filename": filename,
                    "source_content_type": content_type,
                    "latency_seconds": latency,
                },
            }
        finally:
            try:
                os.remove(tmp_in.name)
            except Exception:
                pass
            if needs_cleanup_audio:
                try:
                    os.remove(audio_path)
                except Exception:
                    pass


asr_service = VibeVoiceASRService()
