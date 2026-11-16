# Stage 8F — real pretrained Arabic detector, research only

## Decision

Actual CPU inference succeeded with the [sabaridsnfuji Arabic AI text detector](https://huggingface.co/sabaridsnfuji/arabic-ai-text-detector), using pinned pretrained weights and a research-only adapter. This is a functional demonstration, **not a validated detector**. The Flask application and plagiarism engine were not changed; the existing disabled/unavailable status remains. No scores are exposed in production.

## Model, provenance and local assets

Primary revision: `0009be99cbe558eab59350308dd58082f58ff14d`. The model card declares Apache-2.0 and identifies a fine-tuned AraBERT-v2 BERT sequence classifier; this declaration does not settle base-model and upstream training-data rights or suitability for institutional use. The card and downloaded `model_info.json` say label 0 = human and 1 = AI; `config.json` itself has generic label names. The Safetensors checkpoint was verified against the publisher's LFS SHA-256 and contains `classifier.weight` shape `[2, 768]` and bias `[2]`; strict local loading reported no missing or mismatched classifier weights. This supports correct structural loading, not independent proof of training provenance, accuracy or redistribution clearance.

The development-only directory is `scratch/stage8f/sabaridsnfuji` (ignored by Git), not a production bundle. Required assets total **543,144,470 bytes** (about 518 MiB). The following SHA-256 values were calculated locally; the weight hash matches the publisher LFS metadata:

| File | SHA-256 |
| --- | --- |
| `model.safetensors` | `427fc06a9459475cc6100b7d2b5e2222f4d9be585b6a541c430c0d739fa6bba6` |
| `config.json` | `e38234898e315698665d3d39d67b5ce0740dcde5084b324c3721d182c858355c` |
| `tokenizer.json` | `76771aca772743e6b1a0be699a9ce68e86f9e5773af75f5946d0b3a462c23c0f` |
| `tokenizer_config.json` | `dd546b90ed289c395240e364564a56ce08c3ec82fe14d09a52b015607a9d3441` |
| `special_tokens_map.json` | `5d5b662e421ea9fac075174bb0688ee0d9431699900b90662acd44b2a350503a` |
| `vocab.txt` | `b0851d226a689d7c9880fcb9cb441ccec451138f5658f98937e92687a8892032` |

The [alternative Nawaf AraBERT card](https://huggingface.co/nawaf11570/arabic-ai-arabert) also declares Apache-2.0, identifies label 0 = human and 1 = AI, and describes training on scraped news/comments paired with Gemini rephrasings. Original-source rights and generalization to academic or polished-human writing remain unresolved. Revision `c6378eec16e00ff496765a08edeed27e0f030aab` was downloaded to `scratch/stage8f/nawaf`; its checkpoint SHA-256 `09b9c696070c49b0ee6364228d26f3d81aa5481a0bb1754f1710d541200f94a8` matches the publisher LFS metadata, and its classifier weight and bias shapes are `[2, 768]` and `[2]`. Required assets total 543,344,329 bytes (about 518 MiB). Local asset hashes are recorded in `scratch/stage8f/hashes_nawaf.json`:

| Alternative asset | SHA-256 |
| --- | --- |
| `config.json` | `8673b005fb36a0a33df664373ceb93f18f1984ae6bc404033f8eca021cde0c41` |
| `model.safetensors` | `09b9c696070c49b0ee6364228d26f3d81aa5481a0bb1754f1710d541200f94a8` |
| `tokenizer.json` | `9045a90e772c30f03a784dc784ee394ecfb20f0795f1c742970b18c69469b3bd` |
| `tokenizer_config.json` | `a97efd94a3bcee29d8b45e960be9265a6c143aae83994593587aa62d033856d2` |
| `special_tokens_map.json` | `5d5b662e421ea9fac075174bb0688ee0d9431699900b90662acd44b2a350503a` |
| `vocab.txt` | `57f15013d81a48c99ee349f0c55e617123d2ea4f2e6fc99e9380a4bc8b830e37` |

No model selection is justified from the tiny smoke inputs.

## Implementation

`plagiarism_detector/ai_detection/sequence_research.py` separately loads standard `AutoModelForSequenceClassification` and `AutoTokenizer`, using local files only, CPU, Safetensors, trusted per-file SHA-256, explicit documented label mapping and strict missing/mismatched-weight checks. It retains paragraph text, page/paragraph IDs, caller-supplied offsets, word count, model hash and truncation status. Empty paragraphs are `not_analyzed`; other paragraphs receive only **uncalibrated experimental scores**, no production classification or aggregate percentage. All inference stays research-only and unvalidated; failure returns no partial scores. No rule treats a short text as reliably classified. The file hashes prove identity against the caller's recorded hashes, not scientific validity or legal rights.

`tools/benchmark_sequence_research.py` loads this adapter locally. In its current form it blocks outbound socket connections, runs explicitly identified functional samples and times a separate synthetic 1,000-word workload. `scratch/stage8f/smoke.json` contains the research-only samples and provenance. One UN variant also normalized an initial hamza, so that comparison is **not** an isolated diacritics experiment; a separate variant removes the tanween only. No public or personal thesis was used.

## Actual primary-model smoke outputs

These are model softmax outputs, not authorship probabilities, calibrated estimates, accuracy, or proof. The human text is an eight-word excerpt from the 1948 [UN Universal Declaration](https://europe.ohchr.org/universal-declaration-human-rights); the other two inputs were generated by the assistant during this session. The derived UN version is not a second independent human sample.

| Input | Provenance | Primary AI score | Alternative AI score |
| --- | --- | ---: | ---: |
| UN excerpt, 8 words | Human-origin historical document | 0.184668 | 0.987258 |
| Same excerpt, diacritics removed and hamza normalized | Derived from above | 0.524512 | 0.905081 |
| Same excerpt, tanween removed only | Derived from above | 0.423019 | 0.985441 |
| Short Arabic passage, 8 words | Assistant-generated in this session | 0.920773 | 0.993096 |
| Academic-style passage, 68 words | Assistant-generated in this session | 0.999906 | 0.970837 |

No accuracy or FPR can be estimated from these observations. These short or synthetic examples are not representative of independently labeled academic writing.

## CPU and memory measurements

Development machine: Windows 11 Home, HP Victus, i5-12500H, 12 cores / 16 logical processors, approximately 31.7 GiB RAM; Python 3.13.2, PyTorch 2.9.1+cu128 and Transformers 5.3.0, model and tensors explicitly on CPU. These are single runs with a 50 ms process RSS sampler, not target-hardware or entire-application measurements. Model loading includes file hashing and model/transformers initialization after the benchmark script's initial imports. CPU percentage is process CPU time divided by wall time, so 100% corresponds to one fully used core.

| Batch size 2; independent runs | 1 CPU thread | 2 CPU threads |
| --- | ---: | ---: |
| Model loading, including hash | 47.64 s | 45.07 s |
| Warm smoke inputs | 2.82 s | 1.45 s |
| Synthetic 1,000 words, ten 100-word repeated paragraphs | 16.81 s | 8.25 s |
| Synthetic paragraphs/s | 0.595 | 1.212 |
| Process peak sampled RSS | 1,163,755,520 B | 1,169,018,880 B |
| Process CPU across load and runs, one-core equivalent | 95.9% | 113.1% |

The two-thread run blocked network connections and yielded smoke outputs within approximately 0.000001 of the one-thread outputs. It was faster in this single synthetic workload; repeat experiments and an independent labeled dataset are required before choosing thread count or claiming unchanged accuracy. The synthetic paragraphs were not truncated. Total application RAM, deployment RAM, real 10/50/100-page documents, and the actual 4 GB i3 target were not measured. No ONNX/INT8 conversion was introduced: its accuracy and performance effects remain unmeasured.

The alternative was also loaded and run on CPU with network connections blocked using the same five smoke inputs and 1,000-word synthetic workload. With 2 threads and batch size 2, its one run measured 45.32 s loading (including hash), 0.87 s for smoke inputs, 4.56 s per 1,000 synthetic words, 2.19 synthetic paragraphs/s, 1,157,230,592 B sampled process peak RSS, and 105.2% process CPU across loading and runs. A separate primary rerun with the same five inputs measured 45.64 s load, 1.13 s smoke, 8.08 s per 1,000 synthetic words and 1,171,066,880 B sampled peak RSS. These single runs are not controlled statistical comparisons; tokenizers, system state and workload shape may affect timings. The alternative's high AI score on the short human-origin sample is one observation, not an independently measured false-positive rate. Neither model is selected for production.

## Tests, limitations and next steps

Focused command `python -m pytest -q --disable-warnings tests/test_sequence_research.py tests/test_ai_analysis_integration.py tests/test_review_history_similarity.py tests/test_span_aligner.py`: **20 passed, 0 failed, 0 skipped**, 140 warnings in 49.03 s. The full current-source command `python -m pytest -q --disable-warnings` returned **893 passed, 1 failed, 0 skipped**, 3,343 warnings in 452.15 s. The sole failure is the previously documented strict comparison of current development `config.py` to a historical source manifest; it was not weakened, and old release evidence was not modified. Warnings include the pre-existing NumPy/SciPy incompatibility. The full run includes synthetic tests and is not independent detector validation.

The actual primary checkpoint was loaded on CPU and inferred locally; its output was not subjected to independent academic accuracy evaluation. Baseline artifacts and model binaries remain research-only. Obtain permissions and an independent, source-disjoint Arabic academic dataset with human, AI-polished, generated, OCR and mixed-writing cases; validate low false-positive performance and calibration; benchmark full application RAM and latency on target hardware; then separately verify offline packaging, user-facing safeguards and release integrity before considering an opt-in production integration.

Files added in this stage: `plagiarism_detector/ai_detection/sequence_research.py`, `tools/benchmark_sequence_research.py`, `tests/test_sequence_research.py`, and this report. Development-only model assets, file-hash inventories, sample text and benchmark JSON are in ignored `scratch/stage8f/`. No plagiarism algorithm, production route, reviewer workflow, historical report, application configuration or release manifest was modified.
