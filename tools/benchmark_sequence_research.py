"""Development-only CPU inference and resource benchmark; never downloads files."""
import argparse
import json
import socket
import threading
import time
from pathlib import Path

import psutil
import torch

from plagiarism_detector.ai_detection.sequence_research import SequenceResearchAdapter


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model-dir', type=Path, required=True)
    parser.add_argument('--hashes', type=Path, required=True)
    parser.add_argument('--smoke', type=Path, required=True, help='JSON records with text and provenance')
    parser.add_argument('--threads', type=int, default=1)
    parser.add_argument('--batch-size', type=int, default=2)
    args = parser.parse_args()
    if args.threads < 1:
        parser.error('threads must be positive')
    # Model loading and inference in this benchmark cannot open a TCP socket.
    def no_network(*args, **kwargs):
        raise RuntimeError('network disabled during research inference')
    socket.socket.connect = no_network
    socket.socket.connect_ex = no_network
    torch.set_num_threads(args.threads)
    proc = psutil.Process()
    peak = [proc.memory_info().rss]
    stop = threading.Event()
    def observe():
        while not stop.wait(0.05):
            peak[0] = max(peak[0], proc.memory_info().rss)
    observer = threading.Thread(target=observe, daemon=True)
    observer.start()
    rows = json.loads(args.smoke.read_text(encoding='utf-8'))
    hashes = json.loads(args.hashes.read_text(encoding='utf-8'))
    started = time.perf_counter()
    cpu_before = sum(proc.cpu_times()[:2])
    try:
        model = SequenceResearchAdapter(args.model_dir, file_hashes=hashes,
            label_mapping={0:'HUMAN', 1:'AI_GENERATED'},
            mapping_evidence='publisher model card; config uses generic LABEL_0/LABEL_1', batch_size=args.batch_size)
        model.load()
        cold_seconds = time.perf_counter() - started
        warm_start = time.perf_counter()
        results = model.analyze(rows)
        warm_seconds = time.perf_counter() - warm_start
        # Exactly 1000 whitespace-delimited tokens; clearly repetitive synthetic
        # workload, not a representative document or accuracy evaluation.
        seed_words = next(r['text'].split() for r in rows if r.get('kind') == 'ai_generated')
        words = (seed_words * ((1000 // len(seed_words)) + 1))[:1000]
        bench = [{'text':' '.join(words[i:i+100])} for i in range(0, 1000, 100)]
        bench_start = time.perf_counter()
        bench_result = model.analyze(bench)
        bench_seconds = time.perf_counter() - bench_start
        elapsed = time.perf_counter() - started
        cpu_seconds = sum(proc.cpu_times()[:2]) - cpu_before
        peak[0] = max(peak[0], proc.memory_info().rss)
        print(json.dumps({'model_load_seconds_including_hash': cold_seconds,
            'warm_smoke_seconds': warm_seconds, 'synthetic_1000_word_seconds': bench_seconds,
            'synthetic_paragraphs_per_second': len(bench)/bench_seconds,
            'synthetic_truncated_count': sum(r['truncated'] for r in bench_result),
            'process_peak_sampled_rss_bytes': peak[0], 'process_cpu_seconds': cpu_seconds,
            'elapsed_seconds': elapsed, 'process_cpu_percent_one_core': 100*cpu_seconds/elapsed,
            'cpu_threads': args.threads, 'batch_size': args.batch_size,
            'smoke': [{'id': p.get('paragraph_id'), 'kind': p.get('kind'),
                       'word_count': r['word_count'], 'scores': r['scores'], 'truncated': r['truncated']}
                      for p, r in zip(rows, results)]}, ensure_ascii=False, indent=2))
    finally:
        stop.set()
        observer.join()


if __name__ == '__main__':
    main()
