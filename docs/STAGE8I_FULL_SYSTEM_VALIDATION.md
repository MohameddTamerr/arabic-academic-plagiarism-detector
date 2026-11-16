# Stage 8I — isolated Flask workflow measurement

## Result and production decision

A research benchmark exercised the existing Flask synchronous upload route with synthetic Arabic PDFs, the real extractor, unchanged plagiarism analyzer and report persistence, followed sequentially by local Nawaf INT8 inference inside a test-only wrapper. Each document was extracted exactly once. The wrapper returned the original plagiarism report without adding experimental scores; all persisted production AI statuses remained `disabled`/unavailable. Production code, models, reviewer actions and historical release artifacts were not modified. No production candidate is approved.

## Measured workflow

An opt-in test uses the repository's isolated temporary SQLite/storage fixtures and Flask test client. Test authentication/CSRF compatibility mode and the existing antivirus test double apply. The corpus is empty, OCR and semantic inference are disabled for this experiment, and model outputs are discarded after checking dimensions. This measures an actual application route and its components under a synthetic staging configuration, not a deployed authenticated network server, real corpus search, scanned OCR or DOCX conversion. No existing private document was used. Synthetic PDFs have 100 generated Arabic words per page, deliberately sparse relative to many theses. AI receives one page-text paragraph per page, reused from extraction.

| Synthetic PDF | Extracted words | Extraction s | Plagiarism s | AI model initialization/checks s | AI inference s | Complete request s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 10 pages | 1,000 | 0.390 | 5.869 | 97.583 | 2.948 | 107.505 |
| 50 pages | 5,000 | 0.941 | 0.911 | cached | 10.346 | 12.804 |
| 100 pages | 10,000 | 1.729 | 2.282 | cached | 20.354 | 25.180 |

Token counts, including specials, were 1,020 / 5,100 / 10,200. Similarity was zero against the empty corpus; that is not a similarity accuracy measurement. Initialization includes imports, checkpoint/tokenizer integrity checks and loading. Request totals include upload validation and report persistence; factory creation and fixture generation are outside those totals. Model retention makes later requests warm, so the rows are not comparable cold-start document-size tests.

The `create_app()` factory took 0.174 s after imports and isolated-database setup. **Total cold process/application startup was not measured.** Baseline process working set after factory creation was 716,328,960 bytes; baseline sampled tree private bytes were 2,102,763,520. Framework modules are already imported by the harness, so this is not a minimal production server baseline.

## Memory and CPU

The monitor sampled the current process and children every 20 ms, summing RSS/working sets and Windows `private` bytes. Summed RSS may count shared resident pages more than once; private bytes are not equivalent to resident physical RAM. Stage peaks accumulate over all requests and may include the model retained from an earlier request; they must not be interpreted as incremental allocations attributable to one stage. Sampler and test/fixture overhead are included.

| Stage | Peak tree working set bytes | Peak tree private bytes |
| --- | ---: | ---: |
| Upload | 1,711,202,304 | 3,173,650,432 |
| Extraction | 1,745,371,136 | 3,191,730,176 |
| Plagiarism | 1,745,170,432 | 3,191,496,704 |
| Model initialization | 1,745,170,432 | 3,191,496,704 |
| AI inference | 1,745,321,984 | 3,191,640,064 |
| Report processing | 1,746,702,336 | 3,192,975,360 |
| Overall including synthetic PDF generation | 1,756,536,832 | 3,204,833,280 |

After dropping model/tokenizer references and collecting garbage, process RSS was 1,475,416,064 bytes. This does not prove all allocator/framework memory was returned to the OS. Process CPU time was 197.33 s over 150.19 s instrumented wall time (about 131.4% of one core), including fixture generation and cleanup. Child-process CPU time and paging/swap counters were not collected. No OOM was observed in this test, which is not evidence of absence on a smaller system.

Development host: i5-12500H, Windows laptop, total physical RAM 34,011,582,464 bytes; available RAM before run 9,691,418,624 bytes. Highest observed total-system used memory was 26,229,161,984 bytes, including unrelated programs; this cannot be attributed to the application. These are not 4 GB compatibility results. A prior run of the same fixture measured 97.85 / 12.03 / 19.37 s requests; both runs are preserved under ignored `scratch/stage8i/` and illustrate variability rather than a controlled statistical benchmark.

## Model comparison and independent reliability

Stage 8H measured all four variants in isolated fresh processes. Nawaf INT8 was fastest on that synthetic workload, with lower runtime RAM than FP32; this stage route-benchmarked **only Nawaf INT8**. There is no full-application four-model comparison here. FP32 versus INT8 smoke-score changes and diagnostic class disagreements remain documented in Stage 8H; five related smoke samples are not independent reliability evidence. Academic accuracy, F1, FPR/FNR, confusion matrices, calibration and subgroup results remain unmeasured for all candidates.

Rechecking [KFUPM](https://huggingface.co/datasets/KFUPM-JRCAI/arabic-generated-abstracts) and [GRACE](https://github.com/belgats/gen-ai-detection) did not establish project-specific evaluation-only permissions and independently verified labels/source separation. Institutional plagiarism documents were not treated as authorized evaluation data. Required external input is a rights-cleared academic set with human authorship provenance, generated and polished provenance, source/document identifiers, domains/generator identities and segment labels for mixed documents. Keep threshold/calibration and final test sources disjoint. No new dataset pipeline or claimed accuracy result was created.

## Offline target procedure and packaging

The separate research TorchScript packages and hashes from Stage 8H were reused locally; no model download occurs in this harness. No new executable was built, and RC3 was not replaced. The model/artifact source identity and local tokenizer hashes are checked before load. This stage does not independently prove zero outbound traffic for the whole Flask stack; local model loading and earlier socket-blocked research tests provide narrower evidence. Review model/base-model/training-data use rights before institutional activation.

To reproduce offline on a target PC, copy the reviewed source, exact compatible CPU dependencies, the pinned Nawaf tokenizer assets, hash inventory and trusted `nawaf_int8.jit`/manifest into the same relative research paths. Do not convert on the target. In an isolated research environment run:

```powershell
$env:RUN_STAGE8I='1'
python -m pytest -q --disable-warnings tests/test_stage8i_full_system.py
```

The test automatically isolates database and storage. It relies on test-only authentication compatibility and the antivirus double, so also perform a separate deployment test with actual login/CSRF, real scanner, representative authorized digital/scanned PDF and DOCX documents, populated corpus, network server, OS/pagefile counters and all worker-process memory. Record CPU, Windows/runtime versions, total/available RAM, failures and hashes. Current evidence supports neither approval nor a definitive claim that 4 GB operation is impossible; it indicates substantial memory use that needs target testing.

## Tests, changed files and next gate

The opt-in benchmark passed twice: initial run 1 passed, 21 warnings in 143.85 s; final word-count-instrumented run 1 passed, 21 warnings in 161.96 s. These are performance-fixture tests, not accuracy validation. Additional regression results are recorded below. Warnings include existing dependency/deprecation issues; production dependencies were not changed.

Targeted integration/package command `python -m pytest -q --disable-warnings tests/test_stage8h_package.py tests/test_sequence_research.py tests/test_ai_analysis_integration.py tests/test_review_history_similarity.py`: 17 passed, 0 failed, 0 skipped, 19 warnings in 52.05 s. Full current-source `python -m pytest -q --disable-warnings`: **896 passed, 1 failed, 1 skipped**, 3,349 warnings in 438.20 s. The sole failure is the preserved historical source-manifest mismatch for development `config.py`. The skip is the opt-in real-model resource benchmark, which was executed explicitly twice above. No passing-full-suite claim is made.

Files added: `tests/test_stage8i_full_system.py` and this report; raw JSON under ignored `scratch/stage8i/`. Remaining gates: authorized independent accuracy and quantization evaluation, full populated-corpus/scanned-PDF/DOCX and real-auth deployment measurements, true cold startup, paging/commit/headroom on an actual 4 GB PC, offline executable testing, and a reviewed frozen release. Keep Check AI fail-closed until these pass.
