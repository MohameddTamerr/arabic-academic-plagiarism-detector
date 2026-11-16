# Offline AI-writing analysis integration status

## Current behavior

The single-document and multi-file scan services extract pages and pass the original page text to `analyze_academic_document`. The report builder performs the existing similarity analysis and adds `ai_analysis` to the same report. The report repository already exposes this field. No database migration, model, extra extraction, network request, or inference worker is introduced. Similarity calculations are independent.

AI analysis is unavailable: the report contains null percentages and no paragraph results. The UI and HTML export do not interpret legacy stylistic indicators as authorship. Historical stored reports are not rewritten. `enable_experimental_ai_writing_analysis` defaults to false; even if enabled, it reports `no_validated_model`. It is not an activation switch for predictions. There is no supported way to enable inference in this version.

## Model assessment

Start with a local sparse TF-IDF and calibrated logistic regression or linear SVM baseline after obtaining suitable authorized data; measure false positives and resource usage before considering a transformer. Farras is a candidate classifier, but its [model page](https://huggingface.co/Rashidbm/farras-xlmr-arabic-ai-detector) has no model card and lists 0.3B F32 parameters; license, dataset provenance, independent academic-domain evaluation and performance on the target hardware require verification. Its [repository](https://github.com/Rashidbm/farras) reports its own accuracy, which is not independent validation. [AraBERT](https://huggingface.co/aubmindlab/bert-base-arabertv02) is a pretrained language model, not an authorship classifier; it requires an appropriately trained and validated classification head. Quantized ONNX is a possible future optimization; [ONNX Runtime documentation](https://onnxruntime.ai/docs/performance/model-optimizations/quantization.html) recommends evaluating accuracy and performance for the model and hardware. No model was downloaded, trained, or benchmarked.

## Data and acceptance gates

Stage 8B found no acquired, verified Arabic academic training corpus with appropriate provenance and permissions. Its fixtures are synthetic and cannot establish accuracy. See `STAGE8B_DATASET_DISCOVERY.md`, `STAGE8B_DATA_QUALITY_REPORT.md`, and `STAGE8B_SPLIT_STRATEGY.md`. Before training, verify permissions and retention/derivative rights, label provenance and quality, class balance and domain relevance, deduplicate including near duplicates, and hold out groups by source, author, prompt and generator as applicable. Include human writing, quotations, OCR, mixed and AI-edited writing in independent evaluation. Establish false-positive limits, uncertainty and calibration on a validation set without tuning against the locked test set.

## Future implementation requirements

Preserve original page text and provenance for paragraph segmentation; do not infer precise PDF coordinates where mapping is unavailable. Establish paragraph eligibility and exclusions with validated rules. Store model and calibration identity, classify only when supported, and calculate word-weighted AI, human, uncertain and unanalyzed coverage with an explicit denominator; probabilities are not document percentages. Run inference sequentially after similarity on low-memory hosts, with bounded batches, lazy local-only model loading and bounded concurrency. On the target 4 GB Windows machine measure cold/warm latency, peak process memory, and concurrent workload performance. A validated report UI, safe highlights, artifact integrity checks, failure isolation and offline tests remain to be implemented. No inference speed or memory measurements are possible without an eligible model.
