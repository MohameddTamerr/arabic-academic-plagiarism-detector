"""Trusted local TorchScript research packaging and fresh-process benchmarking."""
import argparse
import json
import socket
import statistics
import threading
import time
from pathlib import Path
import psutil
import torch
from plagiarism_detector.ai_detection.sequence_research import SequenceResearchAdapter, file_sha256, verify_package


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['prepare', 'run'])
    p.add_argument('--model-dir', type=Path, required=True)
    p.add_argument('--hashes', type=Path, required=True)
    p.add_argument('--artifact', type=Path, required=True)
    p.add_argument('--mode', choices=['fp32', 'int8'], required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--smoke', type=Path, default=Path('scratch/stage8f/smoke.json'))
    a = p.parse_args()
    if a.output.exists() or (a.action == 'prepare' and a.artifact.exists()):
        p.error('refusing to overwrite output')
    def blocked(*args, **kwargs):
        raise RuntimeError('network disabled')
    socket.socket.connect = socket.socket.connect_ex = blocked
    torch.set_num_threads(2)
    torch.backends.quantized.engine = 'onednn'
    hashes = json.loads(a.hashes.read_text(encoding='utf-8'))
    metadata = a.artifact.with_suffix('.manifest.json')
    if a.action == 'prepare':
        adapter = SequenceResearchAdapter(a.model_dir, file_hashes=hashes, label_mapping={0:'HUMAN',1:'AI_GENERATED'}, mapping_evidence='publisher card')
        adapter.load()
        adapter.model.config._attn_implementation = 'eager'
        if a.mode == 'int8':
            adapter.model = torch.ao.quantization.quantize_dynamic(adapter.model, {torch.nn.Linear}, dtype=torch.qint8, inplace=True)
        class Wrapper(torch.nn.Module):
            def __init__(self, model):
                super().__init__(); self.model = model
            def forward(self, ids, mask, types):
                return self.model(input_ids=ids, attention_mask=mask, token_type_ids=types).logits
        wrapper = Wrapper(adapter.model).eval()
        inputs = adapter.tokenizer(['هذا نص عربي'], return_tensors='pt')
        args = tuple(inputs[k] for k in ('input_ids','attention_mask','token_type_ids'))
        with torch.inference_mode():
            traced = torch.jit.trace(wrapper, args, check_trace=False)
            differences = []
            for text in ('نص', 'هذا نص عربي للاختبار', ' '.join(['نص']*100)):
                enc = adapter.tokenizer([text], return_tensors='pt')
                values = tuple(enc[k] for k in ('input_ids','attention_mask','token_type_ids'))
                differences.append(float((wrapper(*values)-traced(*values)).abs().max()))
        if max(differences) > 1e-4:
            raise RuntimeError('trace differs from eager model')
        torch.jit.save(traced, str(a.artifact))
        result = {'sha256':file_sha256(a.artifact), 'mode':a.mode, 'source_sha256':hashes['model.safetensors'], 'bytes':a.artifact.stat().st_size, 'trace_logit_differences':differences}
        metadata.write_text(json.dumps(result, indent=2), encoding='utf-8')
    else:
        meta = verify_package(a.artifact, hashes['model.safetensors'], a.mode)
        from transformers import AutoTokenizer
        # Verify original local assets before loading the tokenizer.
        guard = SequenceResearchAdapter(a.model_dir, file_hashes=hashes, label_mapping={0:'HUMAN',1:'AI_GENERATED'}, mapping_evidence='publisher card')
        del guard
        process = psutil.Process(); peak = [process.memory_info().rss]; stop = threading.Event()
        def sample():
            while not stop.wait(.02): peak[0] = max(peak[0], process.memory_info().rss)
        monitor = threading.Thread(target=sample, daemon=True); monitor.start()
        cpu0 = sum(process.cpu_times()[:2]); start = time.perf_counter()
        try:
            tokenizer = AutoTokenizer.from_pretrained(str(a.model_dir), local_files_only=True, trust_remote_code=False)
            model = torch.jit.load(str(a.artifact), map_location='cpu').eval()
            load = time.perf_counter()-start
            rows = json.loads(a.smoke.read_text(encoding='utf-8'))
            def infer(texts):
                output=[]; tokens=0
                for i in range(0,len(texts),2):
                    enc=tokenizer(texts[i:i+2], padding=True, truncation=True,max_length=512,return_tensors='pt')
                    tokens += int(enc['attention_mask'].sum())
                    with torch.inference_mode(): output.extend(torch.softmax(model(*(enc[k] for k in ('input_ids','attention_mask','token_type_ids'))),-1)[:,1].tolist())
                return output,tokens
            scores,_=infer([r['text'] for r in rows])
            seed=next(r['text'].split() for r in rows if r.get('kind')=='ai_generated')
            words=(seed*126)[:1000]; texts=[' '.join(words[i:i+100]) for i in range(0,1000,100)]
            times=[]
            for _ in range(3):
                t=time.perf_counter(); _,tokens=infer(texts); times.append(time.perf_counter()-t)
            elapsed=time.perf_counter()-start
            result={'mode':a.mode,'load_seconds_excluding_hash':load,'warm_seconds':times,'median_seconds':statistics.median(times),'words':1000,'tokens_including_special':tokens,'smoke_ai_scores':scores,'peak_sampled_rss':max(peak[0],process.memory_info().rss),'steady_rss':process.memory_info().rss,'cpu_seconds':sum(process.cpu_times()[:2])-cpu0,'elapsed_seconds':elapsed,'artifact_bytes':a.artifact.stat().st_size}
        finally:
            stop.set(); monitor.join()
    a.output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__': main()
