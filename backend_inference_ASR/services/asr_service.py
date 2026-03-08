from __future__ import annotations

import copy
import gc
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
        self._processor = None
        self._model = None
        self._load_error: str | None = None
        self._runtime_device = "unloaded"

    @staticmethod
    def _resolve_torch_dtype(for_cpu: bool):
        try:
            import torch
        except Exception:
            return None

        if for_cpu:
            return torch.float32

        requested = (
            str(getattr(settings, "ASR_DTYPE", "auto") or "auto").strip().lower()
        )
        if requested == "float16":
            return torch.float16
        if requested == "bfloat16":
            return torch.bfloat16
        if requested == "float32":
            return torch.float32

        if torch.cuda.is_available():
            major, _ = torch.cuda.get_device_capability(0)
            return torch.bfloat16 if major >= 8 else torch.float16
        return torch.float32

    @classmethod
    def _build_model_load_kwargs(cls, for_cpu: bool) -> dict[str, Any]:
        model_kwargs: dict[str, Any] = {
            "low_cpu_mem_usage": True,
            "trust_remote_code": True,
        }
        torch_dtype = cls._resolve_torch_dtype(for_cpu=for_cpu)
        if torch_dtype is not None:
            model_kwargs["torch_dtype"] = torch_dtype
        return model_kwargs

    @property
    def model_id(self) -> str:
        return settings.VIBEVOICE_ASR_MODEL

    @property
    def is_loaded(self) -> bool:
        return self._processor is not None and self._model is not None

    @staticmethod
    def _is_truthy_env(name: str) -> bool:
        return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def _is_cuda_oom_error(exc: Exception) -> bool:
        message = str(exc)
        return "CUDA out of memory" in message or "torch.OutOfMemoryError" in message

    @staticmethod
    def _is_indices_dtype_error(exc: Exception) -> bool:
        message = str(exc)
        return (
            "Expected tensor for argument #1 'indices'" in message and "Type" in message
        )

    @staticmethod
    def _clear_cuda_memory() -> None:
        gc.collect()
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                try:
                    torch.cuda.ipc_collect()
                except Exception:
                    pass
        except Exception:
            pass

    def _unload_pipeline(self) -> None:
        model = self._model
        processor = self._processor
        self._model = None
        self._processor = None
        self._runtime_device = "unloaded"
        if model is not None:
            try:
                del model
            except Exception:
                pass
        if processor is not None:
            try:
                del processor
            except Exception:
                pass
        self._clear_cuda_memory()

    def _normalize_generation_config(self) -> None:
        if self._model is None:
            return

        generation_config = getattr(self._model, "generation_config", None)
        if generation_config is None:
            return

        if (
            getattr(generation_config, "max_new_tokens", None) is not None
            and getattr(generation_config, "max_length", None) is not None
        ):
            generation_config.max_length = None

    def _finalize_model(self) -> None:
        if self._model is None:
            return

        self._model.eval()
        self._normalize_generation_config()

    @staticmethod
    def _is_offline_mode() -> bool:
        return os.getenv("HF_HUB_OFFLINE", "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    @staticmethod
    def _ensure_preprocessor_config_if_missing(model_path: str) -> None:
        preprocessor_path = os.path.join(model_path, "preprocessor_config.json")
        if os.path.exists(preprocessor_path):
            return

        try:
            from transformers.models.vibevoice_acoustic_tokenizer.feature_extraction_vibevoice_acoustic_tokenizer import (
                VibeVoiceAcousticTokenizerFeatureExtractor,
            )
        except Exception as exc:
            raise RuntimeError(
                "missing preprocessor_config.json and failed to import "
                "VibeVoiceAcousticTokenizerFeatureExtractor"
            ) from exc

        VibeVoiceAcousticTokenizerFeatureExtractor().save_pretrained(model_path)
        logger.info("generated missing preprocessor_config.json at %s", model_path)

    def _resolve_model_load_target(self) -> str:
        local_files_only = self._is_offline_mode()
        model_target = self.model_id

        if os.path.isdir(model_target):
            self._ensure_preprocessor_config_if_missing(model_target)
            return model_target

        if "/" in model_target:
            try:
                from huggingface_hub import snapshot_download

                snapshot_path = snapshot_download(
                    repo_id=model_target,
                    local_files_only=local_files_only,
                )
                self._ensure_preprocessor_config_if_missing(snapshot_path)
                return snapshot_path
            except Exception as exc:
                if local_files_only:
                    raise RuntimeError(
                        f"offline mode enabled but local snapshot not found for {model_target}"
                    ) from exc
                return model_target

        return model_target

    def _load_if_needed(self, force_cpu: bool = False) -> None:
        if self.is_loaded:
            return

        try:
            import torch
            from transformers import AutoProcessor, VibeVoiceAsrForConditionalGeneration
        except Exception as exc:
            self._load_error = f"transformers unavailable: {exc}"
            raise RuntimeError(self._load_error)

        processor = None
        model = None

        try:
            model_target = self._resolve_model_load_target()
            logger.info("loading VibeVoice ASR model: %s", self.model_id)

            processor = AutoProcessor.from_pretrained(
                model_target,
                trust_remote_code=True,
            )

            prefer_cpu = force_cpu or self._is_truthy_env("ASR_FORCE_CPU")
            cuda_available = (
                bool(torch.cuda.is_available()) if not prefer_cpu else False
            )

            if cuda_available:
                try:
                    model = VibeVoiceAsrForConditionalGeneration.from_pretrained(
                        model_target,
                        **self._build_model_load_kwargs(for_cpu=False),
                    )
                    model = model.to("cuda:0")
                    self._processor = processor
                    self._model = model
                    self._runtime_device = "cuda:0"
                    self._finalize_model()
                    self._load_error = None
                    return
                except Exception as exc:
                    if model is not None:
                        try:
                            del model
                        except Exception:
                            pass
                    model = None
                    if not self._is_cuda_oom_error(exc):
                        raise
                    logger.warning(
                        "ASR model load on CUDA failed with OOM, falling back to CPU. error=%s",
                        str(exc)[:300],
                    )
                    self._clear_cuda_memory()

            model = VibeVoiceAsrForConditionalGeneration.from_pretrained(
                model_target,
                **self._build_model_load_kwargs(for_cpu=True),
            )
            model = model.to("cpu")
            self._processor = processor
            self._model = model
            self._runtime_device = "cpu"
            self._finalize_model()
            self._load_error = None
        except Exception as exc:
            self._unload_pipeline()
            self._load_error = f"failed to load model {self.model_id}: {exc}"
            raise RuntimeError(self._load_error)

    def _build_generate_kwargs(self, force_greedy: bool = False) -> dict[str, Any]:
        """Build kwargs for model.generate().

        By default returns an empty dict so the model uses its own
        generation_config (matching example.py behaviour).  Custom overrides
        are only applied when ASR_MAX_NEW_TOKENS or ASR_NUM_BEAMS are
        explicitly set to non-default values.
        """
        if self._model is None:
            return {}

        max_new_tokens = int(
            settings.ASR_MAX_NEW_TOKENS
        )  # default 0 = use model default
        num_beams = max(1, int(settings.ASR_NUM_BEAMS))  # default 1

        # Nothing to override → use model's built-in generation_config as-is
        if max_new_tokens <= 0 and num_beams == 1 and not force_greedy:
            return {}

        generation_config = getattr(self._model, "generation_config", None)
        if generation_config is None:
            return {}

        generation_config = copy.deepcopy(generation_config)

        if force_greedy:
            generation_config.num_beams = 1
            generation_config.do_sample = False

        if num_beams > 1 and not force_greedy:
            generation_config.num_beams = num_beams

        if max_new_tokens > 0:
            generation_config.max_new_tokens = max_new_tokens
            generation_config.max_length = None

        return {"generation_config": generation_config}

    def _model_device(self):
        if self._model is None:
            return "cpu"
        try:
            return next(self._model.parameters()).device
        except Exception:
            return getattr(self._model, "device", "cpu")

    def _model_dtype(self):
        if self._model is None:
            return self._resolve_torch_dtype(for_cpu=True)
        return getattr(self._model, "dtype", None) or self._resolve_torch_dtype(
            for_cpu=self._runtime_device == "cpu"
        )

    def _prepare_inputs(self, audio_path: str):
        if self._processor is None or self._model is None:
            raise RuntimeError("ASR processor/model unavailable")

        inputs = self._processor.apply_transcription_request(audio=audio_path)
        if hasattr(inputs, "to"):
            try:
                return inputs.to(self._model_device(), self._model_dtype())
            except TypeError:
                return inputs.to(self._model_device())
        return inputs

    @staticmethod
    def _input_prompt_length(inputs: Any) -> int:
        try:
            input_ids = (
                inputs.get("input_ids")
                if hasattr(inputs, "get")
                else inputs["input_ids"]
            )
            return int(input_ids.shape[1])
        except Exception:
            return 0

    def _decode_raw(self, generated_ids: Any) -> str:
        """Call processor.decode(generated_ids)[0] and return the raw string."""
        if self._processor is None:
            return ""
        decoded = self._processor.decode(generated_ids)
        if isinstance(decoded, (list, tuple)):
            return str(decoded[0]) if decoded else ""
        return str(decoded)

    def _transcribe_once(
        self, audio_path: str, force_greedy: bool = False
    ) -> dict[str, Any]:
        if self._model is None or self._processor is None:
            raise RuntimeError("ASR processor/model unavailable")

        try:
            import torch
        except Exception as exc:
            raise RuntimeError(f"torch unavailable: {exc}") from exc

        inputs = None
        output_ids = None
        generated_ids = None

        try:
            with torch.inference_mode():
                inputs = self._prepare_inputs(audio_path)
                prompt_length = self._input_prompt_length(inputs)
                output_ids = self._model.generate(
                    **inputs,
                    **self._build_generate_kwargs(force_greedy=force_greedy),
                )
                if (
                    prompt_length > 0
                    and getattr(output_ids, "ndim", 0) == 2
                    and output_ids.shape[1] >= prompt_length
                ):
                    generated_ids = output_ids[:, prompt_length:]
                else:
                    generated_ids = output_ids

            raw_out = self._decode_raw(generated_ids.detach().to("cpu"))
            return {"raw_out": raw_out}
        finally:
            for value in (inputs, output_ids, generated_ids):
                try:
                    del value
                except Exception:
                    pass

    def _run_asr(
        self, audio_path: str, allow_cpu_fallback: bool = True
    ) -> dict[str, Any]:
        try:
            return self._transcribe_once(audio_path)
        except Exception as exc:
            message = str(exc)
            if self._is_cuda_oom_error(exc) and allow_cpu_fallback:
                logger.warning(
                    "ASR inference hit CUDA OOM, reloading on CPU and retrying once. error=%s",
                    message[:300],
                )
                self._unload_pipeline()
                self._load_if_needed(force_cpu=True)
                if not self.is_loaded:
                    raise RuntimeError(
                        "ASR processor/model reload failed after CUDA OOM"
                    )
                return self._transcribe_once(audio_path)
            if self._is_cuda_oom_error(exc):
                raise
            if "_beam_search" in message or "expanded size of the tensor" in message:
                logger.warning(
                    "ASR beam-search failed, retrying with greedy decoding. error=%s",
                    message[:300],
                )
                return self._transcribe_once(audio_path, force_greedy=True)
            if self._is_indices_dtype_error(exc):
                logger.warning(
                    "ASR indices dtype mismatch detected, reloading on CPU(float32) and retrying once. error=%s",
                    message[:300],
                )
                self._unload_pipeline()
                self._load_if_needed(force_cpu=True)
                if not self.is_loaded:
                    raise RuntimeError(
                        "ASR processor/model reload failed after dtype mismatch"
                    )
                return self._transcribe_once(audio_path)
            raise
        finally:
            if (
                self._runtime_device.startswith("cuda")
                and settings.ASR_EMPTY_CACHE_AFTER_INFERENCE
            ):
                self._clear_cuda_memory()

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
            "runtime_device": self._runtime_device,
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
            subprocess.run(
                cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
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
        if not self.is_loaded:
            raise RuntimeError("ASR processor/model unavailable")

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
            result = self._run_asr(audio_path)
            raw_out = str(result.get("raw_out") or "")
            latency = round(time.time() - start, 3)
            return {
                "raw_out": raw_out,
                "metadata": {
                    "model": self.model_id,
                    "runtime_device": self._runtime_device,
                    "source_filename": filename,
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
            if settings.ASR_UNLOAD_AFTER_REQUEST:
                self._unload_pipeline()


asr_service = VibeVoiceASRService()
