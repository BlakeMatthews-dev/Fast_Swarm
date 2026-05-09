#!/bin/bash
# Run AI evaluation with vLLM in WSL

cd /mnt/c/Users/Admin/Documents/Fast_Swarm
export PATH="/home/bamn86/miniconda3/bin:$PATH"

# Start vLLM in background
echo "Starting vLLM with Qwen/Qwen2.5-0.5B-Instruct..."
/home/bamn86/miniconda3/bin/vllm serve Qwen/Qwen2.5-0.5B-Instruct --dtype float16 --max-model-len 4096 --gpu-memory-utilization 0.85 &
VLLM_PID=$!

# Wait for it to be ready
echo "Waiting for vLLM to load..."
for i in {1..90}; do
    if curl -s http://localhost:8000/v1/models 2>/dev/null | grep -q Qwen; then
        echo "vLLM ready after ${i}*2 seconds!"
        break
    fi
    sleep 2
done

# Run evaluation
echo ""
echo "=========================================="
echo "Running AI MFE Evaluation"
echo "=========================================="
python scripts/evaluate_ai_mfe_capture.py --max-periods 0 --max-candles 100

# Cleanup
echo ""
echo "Shutting down vLLM..."
kill $VLLM_PID 2>/dev/null
wait $VLLM_PID 2>/dev/null

echo "Done!"
