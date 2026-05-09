#!/bin/bash
# Just start vLLM and keep it running
MODEL="${1:-Qwen/Qwen2.5-0.5B-Instruct}"
export PATH="/home/bamn86/miniconda3/bin:$PATH"

echo "Starting vLLM with $MODEL..."
/home/bamn86/miniconda3/bin/vllm serve "$MODEL" --dtype float16 --max-model-len 4096 --gpu-memory-utilization 0.95
