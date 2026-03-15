"""
AutoDL 图生文远端准备与调用服务。

职责：
- 使用 SSH 连接 AutoDL
- 自动上传并启动远端图生文 FastAPI 服务
- 通过远端本机 localhost 调用推理接口，避免额外暴露公网端口
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import shlex
import socket
import tempfile
import textwrap
from pathlib import PurePosixPath
from threading import Lock
from typing import Any, Dict

from backend_business.api.routers.schemas.vision_schemas import VisionAutoDLConfig

try:
    import paramiko
except ImportError:  # pragma: no cover - 运行时兜底
    paramiko = None


_SERVICE_FILE_NAME = "semantic_atlas_vision_service.py"
_REQUIREMENTS_FILE_NAME = "semantic_atlas_vision_requirements.txt"
_ENV_FILE_NAME = "semantic_atlas_vision.env"
_LOG_FILE_NAME = "semantic_atlas_vision_service.log"
_INSTALL_LOG_FILE_NAME = "semantic_atlas_vision_install.log"
_PID_FILE_NAME = "semantic_atlas_vision_service.pid"
_INSTALL_MARKER_FILE_NAME = "semantic_atlas_vision_install.sha256"
_RUNTIME_MARKER_FILE_NAME = "semantic_atlas_vision_runtime.sha256"
_cache_lock = Lock()
_runtime_cache: Dict[str, Dict[str, Any]] = {}


class VisionAutoDLError(Exception):
    """AutoDL 图生文远端执行异常。"""


def _build_remote_service_code() -> str:
    return textwrap.dedent(
        """
        import io
        import os
        import threading
        from typing import Optional

        import torch
        from fastapi import FastAPI, File, Form, HTTPException, UploadFile
        from PIL import Image
        from pydantic import BaseModel
        from transformers import AutoProcessor, Qwen3VLForConditionalGeneration

        MODEL_ID = os.getenv("MODEL_ID", "/root/autodl-tmp/Qwen3-VL-8B-Instruct")
        MAX_NEW_TOKENS = int(os.getenv("MAX_NEW_TOKENS", "256"))
        TEMPERATURE = float(os.getenv("TEMPERATURE", "0.2"))
        LOAD_ON_STARTUP = os.getenv("LOAD_ON_STARTUP", "1") == "1"

        app = FastAPI(title="Semantic Atlas Vision Service", version="1.0.0")
        _model = None
        _processor = None
        _model_lock = threading.Lock()


        def _load_model():
            global _model, _processor
            if _model is not None and _processor is not None:
                return
            with _model_lock:
                if _model is not None and _processor is not None:
                    return
                _model = Qwen3VLForConditionalGeneration.from_pretrained(
                    MODEL_ID,
                    torch_dtype="auto",
                    device_map="auto",
                    local_files_only=True,
                    trust_remote_code=True,
                )
                _processor = AutoProcessor.from_pretrained(
                    MODEL_ID,
                    local_files_only=True,
                    trust_remote_code=True,
                )


        def _caption_image(image: Image.Image, prompt: str, max_new_tokens: int) -> str:
            _load_model()
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "image"},
                        {"type": "text", "text": prompt},
                    ],
                }
            ]
            text = _processor.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
            )
            inputs = _processor(
                text=[text],
                images=[image],
                return_tensors="pt",
                padding=True,
            )
            inputs = inputs.to(_model.device)
            gen_kwargs = {
                "max_new_tokens": max_new_tokens,
                "do_sample": TEMPERATURE > 0,
            }
            if TEMPERATURE > 0:
                gen_kwargs["temperature"] = TEMPERATURE
                gen_kwargs["top_p"] = 0.9
            generated_ids = _model.generate(**inputs, **gen_kwargs)
            generated_ids_trimmed = [
                out_ids[len(in_ids):]
                for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
            ]
            output_text = _processor.batch_decode(
                generated_ids_trimmed,
                skip_special_tokens=True,
                clean_up_tokenization_spaces=False,
            )
            return (output_text[0] if output_text else "").strip()


        def _build_transcript(caption: str, speaker: str) -> str:
            return f"[0-8000] {speaker}: {caption}"


        class HealthResp(BaseModel):
            status: str
            model_loaded: bool
            model_id: str
            cuda_available: bool
            cuda_device_count: int


        @app.on_event("startup")
        def _startup():
            if LOAD_ON_STARTUP:
                _load_model()


        @app.get("/health", response_model=HealthResp)
        def health():
            return HealthResp(
                status="ok",
                model_loaded=(_model is not None and _processor is not None),
                model_id=MODEL_ID,
                cuda_available=torch.cuda.is_available(),
                cuda_device_count=torch.cuda.device_count()
                if torch.cuda.is_available()
                else 0,
            )


        @app.post("/caption-image")
        async def caption_image(
            file: UploadFile = File(...),
            prompt: str = Form("请详细描述图片内容，并总结关键信息。"),
            speaker: str = Form("vision_agent"),
            max_new_tokens: Optional[int] = Form(None),
        ):
            if not file.content_type or not file.content_type.startswith("image/"):
                raise HTTPException(status_code=400, detail="仅支持图片文件")

            data = await file.read()
            if not data:
                raise HTTPException(status_code=400, detail="空文件")

            try:
                image = Image.open(io.BytesIO(data)).convert("RGB")
            except Exception as exc:
                raise HTTPException(status_code=400, detail=f"图片解析失败: {exc}")

            final_max_tokens = max_new_tokens if max_new_tokens is not None else MAX_NEW_TOKENS
            try:
                caption = _caption_image(image, prompt, final_max_tokens)
            except Exception as exc:
                raise HTTPException(status_code=500, detail=f"模型推理失败: {exc}")

            transcript_text = _build_transcript(caption, speaker)
            return {
                "success": True,
                "filename": file.filename,
                "speaker": speaker,
                "prompt": prompt,
                "caption": caption,
                "transcript_text": transcript_text,
            }
        """
    ).strip() + "\n"


def _build_remote_requirements() -> str:
    return textwrap.dedent(
        """
        fastapi==0.110.0
        uvicorn[standard]==0.27.1
        python-multipart
        pillow
        requests==2.31.0
        transformers==4.57.3
        accelerate>=0.26.0
        """
    ).strip() + "\n"


def _build_remote_env(config: VisionAutoDLConfig) -> str:
    values = {
        "MODEL_ID": config.model_id,
        "MAX_NEW_TOKENS": "256",
        "TEMPERATURE": "0.2",
        "LOAD_ON_STARTUP": "1",
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
    }
    lines = [f"export {key}={shlex.quote(str(value))}" for key, value in values.items()]
    return "\n".join(lines) + "\n"


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _config_signature(config: VisionAutoDLConfig) -> str:
    payload = {
        "host": config.host,
        "port": config.port,
        "username": config.username,
        "workdir": config.workdir,
        "conda_env": config.conda_env,
        "model_id": config.model_id,
        "service_port": config.service_port,
    }
    return _hash_text(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def _require_paramiko() -> None:
    if paramiko is None:
        raise VisionAutoDLError(
            "缺少 paramiko 依赖，请先在本地环境安装 requirements.txt 中新增的依赖"
        )


def _remote_path(config: VisionAutoDLConfig, file_name: str) -> str:
    return str(PurePosixPath(config.workdir) / file_name)


def _connect(config: VisionAutoDLConfig):
    _require_paramiko()
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            hostname=config.host,
            port=config.port,
            username=config.username,
            password=config.password,
            timeout=20,
            banner_timeout=20,
            auth_timeout=20,
            look_for_keys=False,
            allow_agent=False,
        )
    except (paramiko.SSHException, socket.error) as exc:
        raise VisionAutoDLError(f"连接 AutoDL 失败: {exc}") from exc
    return client


def _exec_command(client, command: str, timeout: int = 1200) -> str:
    try:
        stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
        del stdin
        exit_status = stdout.channel.recv_exit_status()
        stdout_text = stdout.read().decode("utf-8", errors="replace")
        stderr_text = stderr.read().decode("utf-8", errors="replace")
    except socket.timeout as exc:
        raise VisionAutoDLError(f"远端命令执行超时({timeout}s): {command[:200]}") from exc
    except Exception as exc:
        raise VisionAutoDLError(f"远端命令执行异常: {exc}") from exc
    if exit_status != 0:
        stderr_tail = stderr_text.strip()[-1200:]
        stdout_tail = stdout_text.strip()[-1200:]
        if stderr_tail and stdout_tail:
            message = (
                f"远端命令执行失败(exit={exit_status})\n"
                f"[stderr]\n{stderr_tail}\n\n"
                f"[stdout]\n{stdout_tail}"
            )
        elif stderr_tail:
            message = f"远端命令执行失败(exit={exit_status})\n{stderr_tail}"
        elif stdout_tail:
            message = f"远端命令执行失败(exit={exit_status})\n{stdout_tail}"
        else:
            message = f"远端命令执行失败(exit={exit_status})，但没有输出"
        raise VisionAutoDLError(message)
    return stdout_text


def _exec_bash(client, script: str, timeout: int = 1200) -> str:
    remote_script_path = f"/tmp/semantic_atlas_vision_{hashlib.md5(script.encode('utf-8')).hexdigest()[:16]}.sh"
    local_script_fd = None
    local_script_path = None
    try:
        local_script_fd, local_script_path = tempfile.mkstemp(
            prefix="semantic_atlas_vision_",
            suffix=".sh",
            text=True,
        )
        with os.fdopen(local_script_fd, "w", encoding="utf-8", newline="\n") as handle:
            local_script_fd = None
            handle.write(script)

        _exec_command(client, f"mkdir -p /tmp && chmod 700 /tmp", timeout=60)
        sftp = client.open_sftp()
        try:
            sftp.put(local_script_path, remote_script_path)
        finally:
            sftp.close()

        command = (
            f"/bin/chmod 700 {shlex.quote(remote_script_path)} && "
            f"/bin/bash {shlex.quote(remote_script_path)}; "
            f"status=$?; "
            f"rm -f {shlex.quote(remote_script_path)}; "
            f"exit $status"
        )
        return _exec_command(client, command, timeout=timeout)
    finally:
        if local_script_fd is not None:
            try:
                os.close(local_script_fd)
            except OSError:
                pass
        if local_script_path and os.path.exists(local_script_path):
            try:
                os.remove(local_script_path)
            except OSError:
                pass


def _upload_text_file(sftp, remote_path: str, content: str) -> None:
    with sftp.open(remote_path, "w") as handle:
        handle.write(content)


def _upload_binary_file(sftp, remote_path: str, content: bytes) -> None:
    with sftp.open(remote_path, "wb") as handle:
        handle.write(content)


def _health_check_script(config: VisionAutoDLConfig) -> str:
    python_code = (
        "import urllib.request;"
        f"urllib.request.urlopen('http://127.0.0.1:{config.service_port}/health', timeout=5).read()"
    )
    return 'if command -v python >/dev/null 2>&1; then PYTHON_BIN="$(command -v python)"; elif command -v python3 >/dev/null 2>&1; then PYTHON_BIN="$(command -v python3)"; else echo "未找到 python/python3" >&2; exit 1; fi; "$PYTHON_BIN" -c ' + shlex.quote(python_code)


def _build_prepare_script(
    config: VisionAutoDLConfig,
    requirements_hash: str,
    runtime_hash: str,
) -> str:
    workdir = shlex.quote(config.workdir)
    requirements_path = shlex.quote(_remote_path(config, _REQUIREMENTS_FILE_NAME))
    env_path = shlex.quote(_remote_path(config, _ENV_FILE_NAME))
    service_path = shlex.quote(_remote_path(config, _SERVICE_FILE_NAME))
    log_path = shlex.quote(_remote_path(config, _LOG_FILE_NAME))
    install_log_path = shlex.quote(_remote_path(config, _INSTALL_LOG_FILE_NAME))
    pid_path = shlex.quote(_remote_path(config, _PID_FILE_NAME))
    install_marker_path = shlex.quote(_remote_path(config, _INSTALL_MARKER_FILE_NAME))
    runtime_marker_path = shlex.quote(_remote_path(config, _RUNTIME_MARKER_FILE_NAME))
    conda_env = shlex.quote(config.conda_env)
    health_script = _health_check_script(config)

    activation_script = textwrap.dedent(
        f"""
        if [ -f /etc/network_turbo ]; then
          source /etc/network_turbo >/dev/null 2>&1 || true
        fi
        if [ -f /root/miniconda3/etc/profile.d/conda.sh ]; then
          source /root/miniconda3/etc/profile.d/conda.sh
        elif command -v conda >/dev/null 2>&1; then
          eval "$(conda shell.bash hook)"
        fi
        if ! command -v conda >/dev/null 2>&1; then
          echo "未找到 conda 命令，请检查 AutoDL 环境" >&2
          exit 1
        fi
        conda activate {conda_env} || {{
          echo "激活 conda 环境失败: {config.conda_env}" >&2
          conda env list >&2 || true
          exit 1
        }}
        if command -v python >/dev/null 2>&1; then
          PYTHON_BIN="$(command -v python)"
        elif command -v python3 >/dev/null 2>&1; then
          PYTHON_BIN="$(command -v python3)"
        else
          echo "未找到 python/python3，请检查 AutoDL 环境" >&2
          exit 1
        fi
        """
    ).strip()

    launch_command = textwrap.dedent(
        f"""
        set -e
        cd {workdir}
        {activation_script}
        set -a
        source {env_path}
        set +a
        "$PYTHON_BIN" -m uvicorn semantic_atlas_vision_service:app --host 127.0.0.1 --port {config.service_port}
        """
    ).strip()

    return textwrap.dedent(
        f"""
        set -euo pipefail
        mkdir -p {workdir}
        cd {workdir}

        retry_cmd() {{
          local retries="$1"
          shift
          local delay=5
          local attempt=1
          while true; do
            if "$@"; then
              return 0
            fi
            if [ "$attempt" -ge "$retries" ]; then
              return 1
            fi
            sleep "$delay"
            attempt=$((attempt + 1))
          done
        }}

        export GIT_HTTP_VERSION=HTTP/1.1
        export GIT_TERMINAL_PROMPT=0
        export PIP_DEFAULT_TIMEOUT=120
        export HF_ENDPOINT=https://hf-mirror.com

        current_install_hash=""
        if [ -f {install_marker_path} ]; then
          current_install_hash="$(cat {install_marker_path} || true)"
        fi

        {activation_script}

        if [ "$current_install_hash" != {shlex.quote(requirements_hash)} ]; then
          if ! retry_cmd 3 /bin/bash -lc {shlex.quote(f'"$PYTHON_BIN" -m pip install -r {requirements_path} > {install_log_path} 2>&1')}; then
            echo "远端依赖安装失败，日志如下：" >&2
            tail -n 80 {install_log_path} >&2 || true
            exit 1
          fi
          printf '%s' {shlex.quote(requirements_hash)} > {install_marker_path}
        fi

        current_runtime_hash=""
        if [ -f {runtime_marker_path} ]; then
          current_runtime_hash="$(cat {runtime_marker_path} || true)"
        fi

        service_healthy=0
        if {health_script} >/dev/null 2>&1; then
          service_healthy=1
        fi

        if [ "$service_healthy" -eq 1 ] && [ "$current_runtime_hash" = {shlex.quote(runtime_hash)} ]; then
          exit 0
        fi

        if [ -f {pid_path} ]; then
          kill "$(cat {pid_path})" >/dev/null 2>&1 || true
          rm -f {pid_path}
        fi
        pkill -f "uvicorn semantic_atlas_vision_service:app --host 127.0.0.1 --port {config.service_port}" >/dev/null 2>&1 || true

        nohup /bin/bash -lc {shlex.quote(launch_command)} > {log_path} 2>&1 < /dev/null &
        echo $! > {pid_path}
        printf '%s' {shlex.quote(runtime_hash)} > {runtime_marker_path}

        for _ in $(seq 1 120); do
          if {health_script} >/dev/null 2>&1; then
            exit 0
          fi
          sleep 5
        done

        echo "远端图生文服务启动超时，日志如下：" >&2
        tail -n 80 {install_log_path} >&2 || true
        tail -n 80 {log_path} >&2 || true
        exit 1
        """
    ).strip()


def ensure_remote_service(config: VisionAutoDLConfig) -> None:
    service_code = _build_remote_service_code()
    requirements_text = _build_remote_requirements()
    env_text = _build_remote_env(config)
    requirements_hash = _hash_text(requirements_text)
    runtime_hash = _hash_text(env_text)
    signature = _config_signature(config)

    client = _connect(config)
    try:
        sftp = client.open_sftp()
        try:
            _exec_bash(client, f"mkdir -p {shlex.quote(config.workdir)}", timeout=60)
            _upload_text_file(sftp, _remote_path(config, _SERVICE_FILE_NAME), service_code)
            _upload_text_file(sftp, _remote_path(config, _REQUIREMENTS_FILE_NAME), requirements_text)
            _upload_text_file(sftp, _remote_path(config, _ENV_FILE_NAME), env_text)
        finally:
            sftp.close()

        script = _build_prepare_script(config, requirements_hash, runtime_hash)
        _exec_bash(client, script, timeout=config.startup_timeout_seconds)
    finally:
        client.close()

    with _cache_lock:
        _runtime_cache[signature] = {"ready": True}


def _build_remote_caption_script(
    config: VisionAutoDLConfig,
    request_payload: Dict[str, Any],
    cleanup_path: str,
) -> str:
    encoded = base64.b64encode(
        json.dumps(request_payload, ensure_ascii=False).encode("utf-8")
    ).decode("ascii")
    return textwrap.dedent(
        f"""
        if [ -f /etc/network_turbo ]; then
          source /etc/network_turbo >/dev/null 2>&1 || true
        fi
        if [ -f /root/miniconda3/etc/profile.d/conda.sh ]; then
          source /root/miniconda3/etc/profile.d/conda.sh
        elif command -v conda >/dev/null 2>&1; then
          eval "$(conda shell.bash hook)"
        fi
        if ! command -v conda >/dev/null 2>&1; then
          echo "未找到 conda 命令，请检查 AutoDL 环境" >&2
          exit 1
        fi
        conda activate {shlex.quote(config.conda_env)} || {{
          echo "激活 conda 环境失败: {config.conda_env}" >&2
          conda env list >&2 || true
          exit 1
        }}
        if command -v python >/dev/null 2>&1; then
          PYTHON_BIN="$(command -v python)"
        elif command -v python3 >/dev/null 2>&1; then
          PYTHON_BIN="$(command -v python3)"
        else
          echo "未找到 python/python3，请检查 AutoDL 环境" >&2
          exit 1
        fi
        "$PYTHON_BIN" - <<'PY'
        import base64
        import json
        import os
        import requests
        import sys

        payload = json.loads(base64.b64decode({encoded!r}).decode("utf-8"))
        try:
            with open(payload["image_path"], "rb") as handle:
                files = {{
                    "file": (
                        payload["filename"],
                        handle,
                        payload["content_type"],
                    )
                }}
                data = {{
                    "prompt": payload["prompt"],
                    "speaker": payload["speaker"],
                }}
                if payload.get("max_new_tokens") is not None:
                    data["max_new_tokens"] = str(payload["max_new_tokens"])
                resp = requests.post(
                    "http://127.0.0.1:{config.service_port}/caption-image",
                    data=data,
                    files=files,
                    timeout=payload.get("timeout_seconds", 900),
                )
                print(resp.text)
                sys.exit(0 if resp.ok else 1)
        finally:
            try:
                os.remove({cleanup_path!r})
            except OSError:
                pass
        PY
        """
    ).strip()


def run_caption(
    config: VisionAutoDLConfig,
    *,
    filename: str,
    content_type: str,
    image_bytes: bytes,
    prompt: str,
    speaker: str,
    max_new_tokens: int | None,
    timeout_seconds: int,
) -> Dict[str, Any]:
    ensure_remote_service(config)

    remote_image_name = f"semantic_atlas_upload_{hashlib.md5(image_bytes).hexdigest()[:16]}"
    suffix = PurePosixPath(filename).suffix or ".jpg"
    remote_image_path = str(PurePosixPath("/tmp") / f"{remote_image_name}{suffix}")
    request_payload = {
        "image_path": remote_image_path,
        "filename": filename,
        "content_type": content_type,
        "prompt": prompt,
        "speaker": speaker,
        "max_new_tokens": max_new_tokens,
        "timeout_seconds": timeout_seconds,
    }

    client = _connect(config)
    try:
        sftp = client.open_sftp()
        try:
            _upload_binary_file(sftp, remote_image_path, image_bytes)
        finally:
            sftp.close()

        response_text = _exec_bash(
            client,
            _build_remote_caption_script(config, request_payload, remote_image_path),
            timeout=max(timeout_seconds, 120),
        ).strip()
    finally:
        client.close()

    if not response_text:
        raise VisionAutoDLError("AutoDL 图生文服务未返回内容")

    try:
        payload = json.loads(response_text)
    except json.JSONDecodeError as exc:
        raise VisionAutoDLError(
            f"AutoDL 图生文返回非 JSON 内容: {response_text[:500]}"
        ) from exc

    if not isinstance(payload, dict):
        raise VisionAutoDLError("AutoDL 图生文返回格式非法")

    return payload
