# Dataset permission package — drafts, not sent

## Priority request: KFUPM Arabic generated abstracts

The [publisher's repository](https://github.com/KFUPM-JRCAI/arabic-text-detection) identifies Moataz Ahmed as corresponding author (`moataz.ahmed@kfupm.edu.sa`). The [dataset card](https://huggingface.co/datasets/KFUPM-JRCAI/arabic-generated-abstracts) describes original journal abstracts and generated variants. The institutional representative should verify the correct recipient and send from an official institutional address. This draft does not claim authority or permission.

**Subject:** Permission request: Arabic generated abstracts for offline academic integrity research

Dear Dr. Ahmed and dataset team,

Our institution, [institution name and department], is evaluating an offline Arabic academic similarity-review system. We would like to use the Arabic Generated Abstracts dataset at revision [version/revision] for research on detecting AI-assisted writing, including separate evaluation of human, generated and AI-polished text. The system is intended for use on an isolated Windows computer and later on an internal server. Its results would be reviewed by people and would not automatically establish authorship.

Could you please provide the applicable dataset license or written authorization and clarify:

1. May we download, retain, preprocess and use the original human abstracts and generated variants to train and independently evaluate a classifier for our institution?
2. Are permissions for the original journal texts included, and are there source-specific restrictions we must satisfy? May we retain linked source/author and generation-group identifiers for leakage control?
3. May we create and retain model weights, vectorizer vocabulary and evaluation results derived from the dataset, and deploy those artifacts offline within our institution? Are later updates, distribution to other institutions, publications, commercial use or redistribution permitted or restricted?
4. Which attribution, access controls, retention/deletion, citation and reporting terms apply? Do the generator outputs have additional use restrictions?
5. Can you provide a versioned download, dataset-specific license, provenance documentation and any source IDs or grouping information needed to keep original abstracts and their generated variants together?

Please indicate the scope of any grant and any permissions we should obtain from journal publishers or other rights holders. We will not use the data until the applicable terms are confirmed.

Kind regards,
[Name, role, institution, official contact]

## Alternative: institution-authorized corpus

Request a written decision from the institution's data steward and relevant rights holders covering: specific document collections and authors; authority/consent and privacy basis; permitted extraction and de-identification; offline processing and storage; generating and labeling AI and AI-polished derivatives; research training/evaluation and offline internal deployment of derived models; retention/deletion, access and sharing limits; and any publication restrictions. The existence of documents in a plagiarism corpus is not authorization. Never classify a document as human-written solely from its age or location. Record the evidence for each label and the source ID linking original and derivatives.

For mixed documents, independently record human and generated spans with offsets against exact original text. Retain model name/version, generation time, prompt/source group, editing category, topic/domain and annotation evidence; protect sensitive data and do not include actual source content or identifiers in public reports. Preserve raw originals in restricted non-Git staging. Keep all variants of the same source in the same split and hold out independent sources, topics and generators where feasible. AI-polished and mixed material remains separate evaluation data; do not silently relabel it as fully AI-generated.

Once authority and source labels are established, follow the import and audit commands in `docs/STAGE8D_REAL_MODEL_TRAINING_REPORT.md`. Do not set a permission field to true merely because the form exists: retain the underlying grant and verify its scope.

## Other candidate access

* [GRACE shared task](https://github.com/belgats/gen-ai-detection): follow its published data-sharing process and obtain specific permission for use beyond the shared task before using restricted components.
* [MULTITuDE Zenodo record](https://zenodo.org/records/10013755): the files are restricted; access requires an institutional email and agreement to research-only/no-resharing terms. The Arabic subset is test-only and news-domain. Ask the owners and applicable rights holders about any proposed use beyond those conditions; it cannot substitute for academic training data.
* [ALHD v2](https://zenodo.org/records/22829905) and [Ar-APT](https://github.com/Saleh-Almohaimeed/Ar-APT): request the dataset license, provenance and upstream-text/use rights before acquisition for this project. ALHD is out-of-domain; Ar-APT is relevant to polished-human evaluation.
