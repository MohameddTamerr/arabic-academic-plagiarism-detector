"""Offline FP32/INT8 research experiment. Never used by the application."""
import argparse
import json
import socket
import statistics
import threading
import time
from pathlib import Path

import psutil
import torch
from plagiarism_detector.ai_detection.sequence_research import SequenceResearchAdapter


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--model-dir', type=Path, required=True)
    ap.add_argument('--hashes', type=Path, required=True)
    ap.add_argument('--smoke', type=Path, required=True)
    ap.add_argument('--mode', choices=['fp32', 'dynamic-int8'], required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--state-out', type=Path, help='optional research-only state dict; never load untrusted pickle')
    ap.add_argument('--threads', type=int, default=2)
    ap.add_argument('--batch-size', type=int, default=2)
    ap.add_argument('--repeats', type=int, default=3)
    ap.add_argument('--pages', type=int, nargs='*', default=[])
    args = ap.parse_args()
    if args.threads < 1 or args.repeats < 1 or any(p < 1 for p in args.pages):
        ap.error('threads, repeats and page sizes must be positive')
    if args.output.exists() or (args.state_out and args.state_out.exists()):
        ap.error('output files must not already exist')
    def no_network(*_a, **_kw):
        raise RuntimeError('network disabled')
    socket.socket.connect = socket.socket.connect_ex = no_network
    torch.set_num_threads(args.threads)
    proc = psutil.Process()
    peak = [proc.memory_info().rss]
    stop = threading.Event()
    def observer():
        while not stop.wait(.05):
            peak[0] = max(peak[0], proc.memory_info().rss)
    monitor = threading.Thread(target=observer, daemon=True)
    monitor.start()
    hashes = json.loads(args.hashes.read_text(encoding='utf-8'))
    rows = json.loads(args.smoke.read_text(encoding='utf-8'))
    t0 = time.perf_counter()
    cpu0 = sum(proc.cpu_times()[:2])
    try:
        adapter = SequenceResearchAdapter(args.model_dir, file_hashes=hashes,
            label_mapping={0:'HUMAN',1:'AI_GENERATED'}, mapping_evidence='publisher card', batch_size=args.batch_size)
        adapter.load()
        load_seconds = time.perf_counter() - t0
        conversion_seconds = 0.0
        state_bytes = None
        engine = None
        if args.mode == 'dynamic-int8':
            engine = next((e for e in ('x86', 'fbgemm', 'onednn', 'qnnpack') if e in torch.backends.quantized.supported_engines), None)
            if engine is None:
                raise RuntimeError(f'No usable quantized backend: {torch.backends.quantized.supported_engines}')
            torch.backends.quantized.engine = engine
            conversion_start = time.perf_counter()
            adapter.model = torch.ao.quantization.quantize_dynamic(adapter.model, {torch.nn.Linear}, dtype=torch.qint8, inplace=True)
            adapter.model.eval()
            conversion_seconds = time.perf_counter() - conversion_start
            if args.state_out:
                with args.state_out.open('xb') as state_file:
                    torch.save(adapter.model.state_dict(), state_file)
                state_bytes = args.state_out.stat().st_size
        smoke = adapter.analyze(rows)
        seed = next(r['text'].split() for r in rows if r.get('kind') == 'ai_generated')
        words = (seed * ((1000 // len(seed)) + 1))[:1000]
        workload = [{'text':' '.join(words[i:i+100])} for i in range(0, 1000, 100)]
        times = []
        for _ in range(args.repeats):
            started = time.perf_counter()
            outputs = adapter.analyze(workload)
            times.append(time.perf_counter() - started)
        page_results = []
        for pages in args.pages:
            # Explicit synthetic workload: 250 words per page, 2 x 125-word paragraphs.
            per_page = (seed * ((250 // len(seed)) + 1))[:250]
            paragraphs = [{'text':' '.join(per_page[i:i+125])} for _ in range(pages) for i in (0,125)]
            begin = time.perf_counter()
            page_out = adapter.analyze(paragraphs)
            page_results.append({'pages':pages, 'words':pages*250, 'paragraphs':len(paragraphs),
                'seconds':time.perf_counter()-begin, 'truncated':sum(x['truncated'] for x in page_out)})
        peak[0] = max(peak[0], proc.memory_info().rss)
        elapsed = time.perf_counter()-t0
        cpu = sum(proc.cpu_times()[:2])-cpu0
        result = {'mode':args.mode, 'model_sha256':hashes['model.safetensors'], 'threads':args.threads,
            'batch_size':args.batch_size, 'load_seconds_including_hash':load_seconds,
            'quantization_seconds':conversion_seconds, 'quantized_state_bytes':state_bytes, 'quantized_engine':engine,
            '1000_word_times_seconds':times, '1000_word_median_seconds':statistics.median(times),
            'synthetic_truncated_count':sum(r['truncated'] for r in outputs), 'page_workloads':page_results,
            'peak_sampled_process_rss_bytes':peak[0], 'process_cpu_seconds':cpu, 'elapsed_seconds':elapsed,
            'process_cpu_percent_one_core':100*cpu/elapsed,
            'smoke': [{'id':p.get('paragraph_id'), 'ai_score':r['scores']['AI_GENERATED'], 'truncated':r['truncated']}
                      for p,r in zip(rows,smoke)]}
        with args.output.open('x', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print(json.dumps(result, ensure_ascii=False))
    finally:
        stop.set(); monitor.join()


if __name__ == '__main__':
    main()
