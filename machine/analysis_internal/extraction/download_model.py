# -*- coding: utf-8 -*-
"""Qwen2-VL-2B-Instruct(Apache-2.0) 다운로드 -> data/models/ (저장소 제외). 용량 약 4.5GB."""
from pathlib import Path
from huggingface_hub import snapshot_download
dst = Path(__file__).resolve().parents[2] / 'data' / 'models' / 'Qwen2-VL-2B-Instruct'
p = snapshot_download('Qwen/Qwen2-VL-2B-Instruct', local_dir=str(dst))
print('done', p)
