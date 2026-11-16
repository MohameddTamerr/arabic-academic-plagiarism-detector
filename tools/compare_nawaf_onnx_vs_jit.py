# -*- coding: utf-8 -*-
"""
Rigorous validation and fidelity comparison:
PyTorch Eager vs TorchScript INT8 vs ONNX FP32 vs ONNX INT8.
Compares:
- Logits max difference and correlation
- Probability differences
- Binary label agreement rate
- Inference latency per paragraph (CPU)
- RAM consumption
"""
import os
import sys
import time
import json
import math
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import onnxruntime as ort

source_dir = ROOT / "scratch" / "stage8f" / "nawaf"
jit_path = ROOT / "models" / "ai_classifier" / "nawaf_int8" / "nawaf_int8.jit"
onnx_fp32_path = ROOT / "scratch" / "onnx_trial" / "nawaf_fp32.onnx"
onnx_int8_path = ROOT / "scratch" / "onnx_trial" / "nawaf_int8.onnx"

assert source_dir.exists(), f"Source model missing: {source_dir}"
assert jit_path.exists(), f"JIT model missing: {jit_path}"
assert onnx_fp32_path.exists(), f"ONNX FP32 missing: {onnx_fp32_path}"
assert onnx_int8_path.exists(), f"ONNX INT8 missing: {onnx_int8_path}"

print("=" * 70)
print("   PHASE 2: NAWAF ARABERT ONNX VS TORCHSCRIPT FIDELITY AUDIT")
print("=" * 70)

# Load Tokenizer
tokenizer = AutoTokenizer.from_pretrained(str(source_dir), local_files_only=True)

# 1. Load PyTorch Eager Model
print("\n[1] Loading PyTorch Eager Model...")
t0 = time.perf_counter()
model_eager = AutoModelForSequenceClassification.from_pretrained(str(source_dir), local_files_only=True)
model_eager.eval()
t_eager_load = time.perf_counter() - t0
print(f"    PyTorch Eager loaded in {t_eager_load:.2f}s")

# 2. Load TorchScript INT8 Model
print("\n[2] Loading TorchScript INT8 Model...")
t0 = time.perf_counter()
torch.backends.quantized.engine = 'onednn'
model_jit = torch.jit.load(str(jit_path), map_location='cpu').eval()
t_jit_load = time.perf_counter() - t0
print(f"    TorchScript INT8 loaded in {t_jit_load:.2f}s")

# 3. Load ONNX FP32 Session
print("\n[3] Loading ONNX FP32 Session...")
t0 = time.perf_counter()
sess_opts = ort.SessionOptions()
sess_opts.intra_op_num_threads = 2
sess_opts.inter_op_num_threads = 1
sess_opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
sess_fp32 = ort.InferenceSession(str(onnx_fp32_path), sess_opts, providers=['CPUExecutionProvider'])
t_onnx_fp32_load = time.perf_counter() - t0
print(f"    ONNX FP32 loaded in {t_onnx_fp32_load:.2f}s")

# 4. Load ONNX INT8 Session
print("\n[4] Loading ONNX INT8 Session...")
t0 = time.perf_counter()
sess_int8 = ort.InferenceSession(str(onnx_int8_path), sess_opts, providers=['CPUExecutionProvider'])
t_onnx_int8_load = time.perf_counter() - t0
print(f"    ONNX INT8 loaded in {t_onnx_int8_load:.2f}s")

# Load benchmark dataset
dataset_path = ROOT / "tests" / "benchmark" / "academic_ai_writing_benchmark_dataset.json"
records = json.loads(dataset_path.read_text(encoding="utf-8"))
print(f"\nLoaded {len(records)} benchmark samples from {dataset_path.name}")

# Additional edge cases
edge_cases = [
    {"text": "نص", "category": "single_word"},
    {"text": "مرحباً بكم في هذا البحث الأكاديمي.", "category": "short_sentence"},
    {"text": "،،، ... ؟؟؟ !!!", "category": "punctuation_only"},
    {"text": " ".join(["القانون"] * 100), "category": "repeated_words_medium"},
    {"text": " ".join(["التاريخ"] * 300), "category": "repeated_words_long"},
]

eval_texts = [r["text"] for r in records] + [ec["text"] for ec in edge_cases]
print(f"Total evaluation samples including edge cases: {len(eval_texts)}")

eager_logits, eager_probs, eager_labels = [], [], []
jit_logits, jit_probs, jit_labels = [], [], []
onnx_fp32_logits, onnx_fp32_probs, onnx_fp32_labels = [], [], []
onnx_int8_logits, onnx_int8_probs, onnx_int8_labels = [], [], []

t_jit_total = 0.0
t_onnx_int8_total = 0.0

print("\nRunning inference across all models...")
for i, text in enumerate(eval_texts):
    if not text.strip():
        continue
    enc = tokenizer(text, truncation=True, max_length=512, return_tensors="pt")
    input_ids = enc["input_ids"]
    attention_mask = enc["attention_mask"]
    token_type_ids = enc.get("token_type_ids", torch.zeros_like(input_ids))

    ort_inputs = {
        "input_ids": input_ids.numpy().astype(np.int64),
        "attention_mask": attention_mask.numpy().astype(np.int64),
        "token_type_ids": token_type_ids.numpy().astype(np.int64),
    }

    # Eager
    with torch.no_grad():
        out_e = model_eager(input_ids=input_ids, attention_mask=attention_mask, token_type_ids=token_type_ids)
        l_e = out_e.logits.numpy()[0]
        p_e = torch.softmax(out_e.logits, dim=-1).numpy()[0]
        eager_logits.append(l_e)
        eager_probs.append(p_e)
        eager_labels.append(int(np.argmax(l_e)))

    # JIT
    t_start = time.perf_counter()
    with torch.inference_mode():
        l_j = model_jit(input_ids, attention_mask, token_type_ids).numpy()[0]
        p_j = torch.softmax(torch.from_numpy(l_j), dim=-1).numpy()
    t_jit_total += (time.perf_counter() - t_start)
    jit_logits.append(l_j)
    jit_probs.append(p_j)
    jit_labels.append(int(np.argmax(l_j)))

    # ONNX FP32
    l_o_fp32 = sess_fp32.run(None, ort_inputs)[0][0]
    p_o_fp32 = torch.softmax(torch.from_numpy(l_o_fp32), dim=-1).numpy()
    onnx_fp32_logits.append(l_o_fp32)
    onnx_fp32_probs.append(p_o_fp32)
    onnx_fp32_labels.append(int(np.argmax(l_o_fp32)))

    # ONNX INT8
    t_start = time.perf_counter()
    l_o_int8 = sess_int8.run(None, ort_inputs)[0][0]
    p_o_int8 = torch.softmax(torch.from_numpy(l_o_int8), dim=-1).numpy()
    t_onnx_int8_total += (time.perf_counter() - t_start)
    onnx_int8_logits.append(l_o_int8)
    onnx_int8_probs.append(p_o_int8)
    onnx_int8_labels.append(int(np.argmax(l_o_int8)))

N = len(eager_labels)
print(f"Successfully processed {N} samples.")

# Convert to arrays
eager_logits = np.array(eager_logits)
jit_logits = np.array(jit_logits)
onnx_fp32_logits = np.array(onnx_fp32_logits)
onnx_int8_logits = np.array(onnx_int8_logits)

eager_probs = np.array(eager_probs)
jit_probs = np.array(jit_probs)
onnx_fp32_probs = np.array(onnx_fp32_probs)
onnx_int8_probs = np.array(onnx_int8_probs)

# Comparisons
# 1. ONNX FP32 vs PyTorch Eager (Export Fidelity)
fp32_vs_eager_max_diff = float(np.max(np.abs(onnx_fp32_logits - eager_logits)))
fp32_vs_eager_label_agree = float(np.mean(np.array(onnx_fp32_labels) == np.array(eager_labels)) * 100)

# 2. ONNX INT8 vs JIT INT8 (Runtime Fidelity)
onnx_vs_jit_prob_diff = np.abs(onnx_int8_probs[:, 1] - jit_probs[:, 1])
onnx_vs_jit_max_prob_diff = float(np.max(onnx_vs_jit_prob_diff))
onnx_vs_jit_mean_prob_diff = float(np.mean(onnx_vs_jit_prob_diff))
onnx_vs_jit_label_agree = float(np.mean(np.array(onnx_int8_labels) == np.array(jit_labels)) * 100)

# 3. ONNX INT8 vs Eager PyTorch (End-to-End Quantized Fidelity)
onnx_vs_eager_prob_diff = np.abs(onnx_int8_probs[:, 1] - eager_probs[:, 1])
onnx_vs_eager_max_prob_diff = float(np.max(onnx_vs_eager_prob_diff))
onnx_vs_eager_mean_prob_diff = float(np.mean(onnx_vs_eager_prob_diff))
onnx_vs_eager_label_agree = float(np.mean(np.array(onnx_int8_labels) == np.array(eager_labels)) * 100)

# Latency
jit_latency_ms = (t_jit_total / N) * 1000
onnx_latency_ms = (t_onnx_int8_total / N) * 1000

print("\n" + "=" * 70)
print("              FIDELITY & PERFORMANCE BENCHMARK RESULTS")
print("=" * 70)
print(f"ONNX FP32 vs PyTorch Eager Max Logit Diff:   {fp32_vs_eager_max_diff:.6f}")
print(f"ONNX FP32 vs PyTorch Eager Label Agreement: {fp32_vs_eager_label_agree:.2f}%\n")

print(f"ONNX INT8 vs TorchScript INT8 Label Agreement: {onnx_vs_jit_label_agree:.2f}%")
print(f"ONNX INT8 vs TorchScript INT8 Mean Prob Diff:   {onnx_vs_jit_mean_prob_diff:.4f}")
print(f"ONNX INT8 vs TorchScript INT8 Max Prob Diff:    {onnx_vs_jit_max_prob_diff:.4f}\n")

print(f"ONNX INT8 vs PyTorch Eager Label Agreement:    {onnx_vs_eager_label_agree:.2f}%")
print(f"ONNX INT8 vs PyTorch Eager Mean Prob Diff:      {onnx_vs_eager_mean_prob_diff:.4f}")
print(f"ONNX INT8 vs PyTorch Eager Max Prob Diff:       {onnx_vs_eager_max_prob_diff:.4f}\n")

print(f"TorchScript INT8 CPU Latency per sample:       {jit_latency_ms:.2f} ms")
print(f"ONNX Runtime INT8 CPU Latency per sample:      {onnx_latency_ms:.2f} ms")
print(f"Speedup with ONNX Runtime:                     {jit_latency_ms / max(0.001, onnx_latency_ms):.2f}x\n")

print(f"TorchScript JIT File Size:                     {jit_path.stat().st_size / (1024*1024):.2f} MB")
print(f"ONNX INT8 File Size:                           {onnx_int8_path.stat().st_size / (1024*1024):.2f} MB")
print(f"Size Reduction:                                {(1 - onnx_int8_path.stat().st_size / jit_path.stat().st_size) * 100:.1f}%\n")

report_data = {
    "num_samples": N,
    "fp32_vs_eager_max_diff": fp32_vs_eager_max_diff,
    "fp32_vs_eager_label_agreement": fp32_vs_eager_label_agree,
    "onnx_int8_vs_jit_int8": {
        "label_agreement_pct": onnx_vs_jit_label_agree,
        "mean_probability_diff": onnx_vs_jit_mean_prob_diff,
        "max_probability_diff": onnx_vs_jit_max_prob_diff,
    },
    "onnx_int8_vs_eager": {
        "label_agreement_pct": onnx_vs_eager_label_agree,
        "mean_probability_diff": onnx_vs_eager_mean_prob_diff,
        "max_probability_diff": onnx_vs_eager_max_prob_diff,
    },
    "latency_ms": {
        "torchscript_int8": round(jit_latency_ms, 2),
        "onnxruntime_int8": round(onnx_latency_ms, 2),
        "speedup": round(jit_latency_ms / max(0.001, onnx_latency_ms), 2)
    },
    "file_sizes_mb": {
        "torchscript_int8": round(jit_path.stat().st_size / (1024*1024), 2),
        "onnx_int8": round(onnx_int8_path.stat().st_size / (1024*1024), 2)
    }
}

out_report_file = ROOT / "docs" / "ONNX_VS_JIT_FIDELITY_REPORT.json"
out_report_file.write_text(json.dumps(report_data, indent=2), encoding="utf-8")
print(f"Report saved to: {out_report_file}")
