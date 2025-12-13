import torch
from transformers import AutoTokenizer, AutoModelForCausalLM, AutoModelForSeq2SeqLM

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

    def generate(self, prompt: str, system_prompt: str, max_new_tokens: int = 128) -> str:
        """
        根据给定的 prompt 和 system_prompt 生成响应

        Args:
            prompt (str): 用户输入的提示词
            system_prompt (str): 系统提示词，用于设定模型行为
            max_new_tokens (int): 生成的最大 token 数

        Returns:
            str: 模型生成的文本响应
        """
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
