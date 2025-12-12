import torch
from transformers import AutoTokenizer, AutoModelForCausalLM, AutoModelForSeq2SeqLM

class DeepSeekEngine:
    def __init__(self, model_path: str):
        self.model_path = model_path
        self.model = None
        self.tokenizer = None
        self.device_map = "auto" if torch.cuda.is_available() else None

    def _pick_dtype(self):
        if torch.cuda.is_available():
            major, _ = torch.cuda.get_device_capability(0)
            return torch.bfloat16 if major >= 8 else torch.float16
        return torch.float32

    def load_model(self):
        print(f"Loading model from {self.model_path}...")
        self.tokenizer = AutoTokenizer.from_pretrained(
            self.model_path, 
            trust_remote_code=True, 
            use_fast=True
        )
        
        dtype = self._pick_dtype()
        try:
            self.model = AutoModelForCausalLM.from_pretrained(
                self.model_path, 
                dtype=dtype,
                device_map=self.device_map,
                trust_remote_code=True,
            )
        except Exception:
            self.model = AutoModelForSeq2SeqLM.from_pretrained(
                self.model_path, 
                dtype=dtype,
                device_map=self.device_map,
                trust_remote_code=True,
            )

        if self.tokenizer.pad_token_id is None and self.tokenizer.eos_token_id is not None:
            self.tokenizer.pad_token = self.tokenizer.eos_token
        print("Model loaded successfully.")

    def generate(self, prompt: str, system_prompt: str, max_new_tokens: int = 128) -> str:
        if not self.model or not self.tokenizer:
            raise RuntimeError("Model is not loaded. Please call load_model() first.")

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]

        try:
            inputs = self.tokenizer.apply_chat_template(
                messages,
                add_generation_prompt=True,
                tokenize=True, return_tensors="pt", return_dict=True,
            )
        except Exception:
            text = f"system:\n{system_prompt}\nuser:\n{prompt}\nassistant:\n"
            inputs = self.tokenizer(text, return_tensors="pt")

        if torch.cuda.is_available():
            inputs = {k: v.cuda() for k, v in inputs.items()}

        with torch.inference_mode():
            out = self.model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=False,
                pad_token_id=self.tokenizer.pad_token_id,
                eos_token_id=self.tokenizer.eos_token_id,
                use_cache=True,
            )

        inp_len = inputs["input_ids"].shape[-1]
        gen_ids = out[0][inp_len:]
        return self.tokenizer.decode(gen_ids, skip_special_tokens=True).strip()
