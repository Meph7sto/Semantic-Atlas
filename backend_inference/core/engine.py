import torch
from transformers import AutoConfig, AutoTokenizer, AutoModelForCausalLM, AutoModelForSeq2SeqLM

class DeepSeekEngine:
    """
    DeepSeek 模型引擎类
    负责加载模型、Tokenizer 以及执行文本生成任务
    """
    def __init__(self, model_path: str):
        self.model_path = model_path
        self.model = None
        self.tokenizer = None
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

    def load_model(self):
        """
        加载 Tokenizer 和模型
        """
        print(f"Loading model from {self.model_path}...")
        # 加载 Tokenizer
        self.tokenizer = AutoTokenizer.from_pretrained(
            self.model_path, 
            trust_remote_code=True, 
            use_fast=True
        )
        
        dtype = self._pick_dtype()

        # 先读取配置，判断模型是 encoder-decoder 还是 decoder-only（如 Llama/Qwen/DeepSeek）
        cfg = AutoConfig.from_pretrained(self.model_path, trust_remote_code=True)
        is_encoder_decoder = bool(getattr(cfg, "is_encoder_decoder", False))

        def _from_pretrained(model_cls):
            # 兼容不同 transformers/remote_code 对 torch_dtype/dtype 的参数差异
            try:
                return model_cls.from_pretrained(
                    self.model_path,
                    torch_dtype=dtype,
                    device_map=self.device_map,
                    trust_remote_code=True,
                )
            except TypeError:
                return model_cls.from_pretrained(
                    self.model_path,
                    dtype=dtype,
                    device_map=self.device_map,
                    trust_remote_code=True,
                )

        if is_encoder_decoder:
            self.model = _from_pretrained(AutoModelForSeq2SeqLM)
        else:
            # Llama/Qwen/DeepSeek 等都在这里
            self.model = _from_pretrained(AutoModelForCausalLM)

        # 确保 tokenizer 有 pad_token，如果为 None 则使用 eos_token
        if self.tokenizer.pad_token_id is None and self.tokenizer.eos_token_id is not None:
            self.tokenizer.pad_token = self.tokenizer.eos_token
        print("Model loaded successfully.")

    def generate(
        self,
        prompt: str,
        system_prompt: str,
        max_new_tokens: int = 128,
        temperature: float = 0.1,
        top_p: float = 0.8,
        do_sample: bool = True,
        min_new_tokens: int = 16,
    ) -> str:
        if not self.model or not self.tokenizer:
            raise RuntimeError("Model is not loaded. Please call load_model() first.")

        # 与 ai-requirement-tracer 对齐：优先使用 plain prompt（避免 chat_template 不兼容导致空输出）
        text = f"{system_prompt}\n\n{prompt}\n"
        inputs = self.tokenizer(text, return_tensors="pt")

        # device_map=auto 时，把输入放到 cuda:0 更稳（避免设备不一致/直接 EOS）
        if torch.cuda.is_available():
            inputs = {k: v.to("cuda:0") for k, v in inputs.items()}

        # 执行推理生成
        with torch.inference_mode():
            out = self.model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                min_new_tokens=min(min_new_tokens, max_new_tokens),
                do_sample=do_sample,
                temperature=temperature,
                top_p=top_p,
                pad_token_id=self.tokenizer.pad_token_id,
                eos_token_id=self.tokenizer.eos_token_id,
                use_cache=True,
            )

        # 解码生成的 token，跳过特殊 token
        inp_len = inputs["input_ids"].shape[-1]
        gen_ids = out[0][inp_len:]
        text = self.tokenizer.decode(gen_ids, skip_special_tokens=True).strip()
        # 兜底：极端情况下 gen_ids 为空/全是特殊符号，则解码整段，至少便于调试
        if not text:
            text = self.tokenizer.decode(out[0], skip_special_tokens=True).strip()
        return text
