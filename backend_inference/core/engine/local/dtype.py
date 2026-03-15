import torch


def pick_dtype():
    """
    根据硬件能力选择合适的数据类型
    如果 CUDA 计算能力 >= 8 (Ampere 架构及以上)，使用 bfloat16
    否则使用 float16，无 GPU 则使用 float32
    """
    if torch.cuda.is_available():
        major, _ = torch.cuda.get_device_capability(0)
        return torch.bfloat16 if major >= 8 else torch.float16
    return torch.float32
