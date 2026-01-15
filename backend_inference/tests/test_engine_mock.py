import unittest
from unittest.mock import MagicMock, patch
import torch
import sys
import os

# Ensure import works
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from backend_inference.core.engine import DeepSeekEngine

class TestDeepSeekEngine(unittest.TestCase):
    @patch('backend_inference.core.engine.torch.cuda.is_available', return_value=True)
    @patch('backend_inference.core.engine.AutoTokenizer')
    @patch('backend_inference.core.engine.AutoModelForCausalLM')
    def test_generate_cuda_transfer(self, mock_model_cls, mock_tokenizer_cls, mock_cuda):
        # Setup mocks
        mock_tokenizer = MagicMock()
        mock_tokenizer_cls.from_pretrained.return_value = mock_tokenizer

        mock_model = MagicMock()
        mock_model_cls.from_pretrained.return_value = mock_model

        # Create engine and load model
        engine = DeepSeekEngine("dummy_path")
        # Mock _pick_dtype to avoid cuda call inside it (though we mocked is_available=True)
        # engine._pick_dtype would call torch.cuda.get_device_capability which we didn't mock.
        # Let's mock _pick_dtype or get_device_capability
        with patch('backend_inference.core.engine.torch.cuda.get_device_capability', return_value=(8, 0)):
             engine.load_model()

        # Mock inputs
        mock_inputs = MagicMock()
        # Mock dictionary behavior for **inputs unpacking
        mock_inputs.keys.return_value = ["input_ids"]
        mock_inputs.__getitem__.side_effect = lambda k: MagicMock(shape=[1, 10]) if k == "input_ids" else MagicMock()

        # Mock .to() to return self
        mock_inputs.to.return_value = mock_inputs

        mock_tokenizer.apply_chat_template.return_value = mock_inputs

        # Mock model.generate
        # It returns a tensor of ids
        mock_model.generate.return_value = torch.tensor([[1]*20])

        # Mock decode
        mock_tokenizer.decode.return_value = "response"

        # Run generate
        engine.generate("prompt", "system")

        # Assert inputs.to("cuda") was called
        mock_inputs.to.assert_called_with("cuda")
        print("\nVerified: inputs.to('cuda') was called.")

if __name__ == '__main__':
    unittest.main()
