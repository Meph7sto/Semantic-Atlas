import asyncio
import json
from typing import List, Optional

import aiohttp
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM, AutoModelForSeq2SeqLM

from core.config import settings

class DeepSeekEngine:
    """
    DeepSeek 模型引擎类
    负责加载模型、Tokenizer 以及执行文本生成任务
    """
    def __init__(
        self,
        model_path: str,
        provider: str = "local",
        chutes_api_url: Optional[str] = None,
        chutes_api_token: Optional[str] = None,
        deepseek_api_url: Optional[str] = None,
        deepseek_api_key: Optional[str] = None,
    ):
        self.model_path = model_path
        self.model = None
        self.tokenizer = None
        self.provider = (provider or settings.MODEL_PROVIDER).lower()
        self.chutes_api_url = chutes_api_url or settings.CHUTES_API_URL
        self.chutes_api_token = chutes_api_token or settings.CHUTES_API_TOKEN
        self.deepseek_api_url = deepseek_api_url or settings.DEEPSEEK_API_URL
        self.deepseek_api_key = deepseek_api_key or settings.DEEPSEEK_API_KEY
        # 如果 CUDA 可用，自动配置 device_map，否则为 None
        self.device_map = "auto" if torch.cuda.is_available() else None

    def _pick_dtype(self):
        """
        根据硬件能力选择合适的数据类型
        如果 CUDA 计算能力 >= 8 (Ampere 架构及以上)，使用 bfloat16
        否则使用 float16，无 GPU 则使用 float32
        """
        if torch.cuda.is_available():
            major, _ = torch.cuda.get_device_capability(0)
            return torch.bfloat16 if major >= 8 else torch.float16
        return torch.float32

    # ---------------------
    # 本地模型加载与推理逻辑
    # ---------------------
    def load_model(self):
        """
        加载 Tokenizer 和模型
        """
        if self.provider != "local":
            # API 模式下无需加载本地模型
            self.model = "api"  # 简单标记可用
            print(f"Using remote provider '{self.provider}', skip local model loading.")
            return

        print(f"Loading model from {self.model_path}...")
        # 加载 Tokenizer
        self.tokenizer = AutoTokenizer.from_pretrained(
            self.model_path, 
            trust_remote_code=True, 
            use_fast=True
        )
        
        dtype = self._pick_dtype()
        try:
            # 尝试作为 CausalLM 加载 (如 GPT 类模型)
            self.model = AutoModelForCausalLM.from_pretrained(
                self.model_path, 
                dtype=dtype,
                device_map=self.device_map,
                trust_remote_code=True,
            )
        except Exception:
            # 如果失败，回退尝试作为 Seq2SeqLM 加载 (如 T5/BART 类模型)
            self.model = AutoModelForSeq2SeqLM.from_pretrained(
                self.model_path, 
                dtype=dtype,
                device_map=self.device_map,
                trust_remote_code=True,
            )

        # 确保 tokenizer 有 pad_token，如果为 None 则使用 eos_token
        if self.tokenizer.pad_token_id is None and self.tokenizer.eos_token_id is not None:
            self.tokenizer.pad_token = self.tokenizer.eos_token
        print("Model loaded successfully.")

    def _generate_locally(self, prompt: str, system_prompt: str, max_new_tokens: int) -> str:
        if not self.model or not self.tokenizer:
            raise RuntimeError("Model is not loaded. Please call load_model() first.")

        # 构造对话消息格式
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]

        try:
            # 应用聊天模板进行 tokenization
            inputs = self.tokenizer.apply_chat_template(
                messages,
                add_generation_prompt=True,
                tokenize=True, return_tensors="pt", return_dict=True,
            )
        except Exception:
            # 如果模板应用失败，使用简单的字符串拼接回退方案
            text = f"system:\n{system_prompt}\nuser:\n{prompt}\nassistant:\n"
            inputs = self.tokenizer(text, return_tensors="pt")

        # 将输入数据移动到 GPU (如果可用)
        if torch.cuda.is_available():
            inputs = {k: v.cuda() for k, v in inputs.items()}

        # 执行推理生成
        with torch.inference_mode():
            out = self.model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=False, # 使用贪婪解码，保证结果确定性
                pad_token_id=self.tokenizer.pad_token_id,
                eos_token_id=self.tokenizer.eos_token_id,
                use_cache=True,
            )

        # 解码生成的 token，跳过特殊 token
        inp_len = inputs["input_ids"].shape[-1]
        gen_ids = out[0][inp_len:]
        return self.tokenizer.decode(gen_ids, skip_special_tokens=True).strip()

    # ---------------------
    # 远程 API 调用逻辑
    # ---------------------
    def _extract_stream_content(self, data: str, buffer: List[str]) -> None:
        """
        尝试从 SSE 数据块中提取文本内容并写入 buffer。
        如果解析失败，则直接附加原始字符串，保证不丢失信息。
        """
        try:
            payload = json.loads(data)
            choices = payload.get("choices") or []
            if not choices:
                return
            delta = choices[0].get("delta") or choices[0].get("message") or {}
            content_piece = delta.get("content") or delta.get("text") or ""
            if content_piece:
                buffer.append(content_piece)
        except json.JSONDecodeError:
            # 兼容特殊行：无法解析的块直接拼接
            buffer.append(data)

    def _generate_via_chutes(self, prompt: str, system_prompt: str, max_new_tokens: int) -> str:
        """
        使用 Chutes API 进行推理，采用 requests 进行同步流式解析。
        """
        import requests
        
        if not self.chutes_api_token:
            raise RuntimeError("Chutes API token is missing. Set CHUTES_API_TOKEN/CHUTES_API_KEY.")

        headers = {
            "Authorization": f"Bearer {self.chutes_api_token}",
            "Content-Type": "application/json",
        }
        body = {
            "model": "deepseek-ai/DeepSeek-V3.1-Terminus",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "stream": True,
            "max_tokens": max_new_tokens,
            "temperature": 0.7,
        }

        chunks: List[str] = []
        
        try:
            response = requests.post(
                self.chutes_api_url,
                headers=headers,
                json=body,
                stream=True,
                timeout=120
            )
            
            if response.status_code != 200:
                raise RuntimeError(f"Chutes API error {response.status_code}: {response.text}")
            
            for line in response.iter_lines():
                if not line:
                    continue
                line_str = line.decode("utf-8").strip()
                data = line_str[6:] if line_str.startswith("data: ") else line_str
                if not data:
                    continue
                if data == "[DONE]":
                    break
                self._extract_stream_content(data, chunks)
                
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Chutes API request failed: {e}")

        return "".join(chunks).strip()

    def _generate_via_deepseek(self, prompt: str, system_prompt: str, max_new_tokens: int) -> str:
        """
        DeepSeek 官方 API 占位符。
        在接入真实 DeepSeek API 时，按需实现与 _generate_via_chutes 类似的流式解析逻辑。
        """
        raise NotImplementedError("DeepSeek API client is not implemented yet.")

    def generate(self, prompt: str, system_prompt: str, max_new_tokens: int = 128) -> str:
        """
        根据给定的 prompt 和 system_prompt 生成响应
        """
        if self.provider == "chutes":
            return self._generate_via_chutes(prompt, system_prompt, max_new_tokens)
        if self.provider == "deepseek":
            return self._generate_via_deepseek(prompt, system_prompt, max_new_tokens)
        return self._generate_locally(prompt, system_prompt, max_new_tokens)
