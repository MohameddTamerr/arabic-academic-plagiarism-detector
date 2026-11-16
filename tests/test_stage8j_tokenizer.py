"""Optional real local tokenizer parity; no authorship accuracy claims."""
import os
from pathlib import Path
import pytest


@pytest.mark.skipif(os.environ.get('RUN_STAGE8J_PARITY') != '1', reason='requires local research tokenizer assets')
def test_direct_tokenizer_matches_transformers():
    from transformers import AutoTokenizer
    from tools.stage8j_tokenizer import LocalFastTokenizer
    directory=Path(__file__).resolve().parents[1]/'scratch/stage8f/nawaf'
    expected=AutoTokenizer.from_pretrained(str(directory),local_files_only=True,trust_remote_code=False)
    actual=LocalFastTokenizer(directory/'tokenizer.json')
    texts=['', 'تتناول هذه الدراسة تحليل البيانات وتوثيق مصادر المعلومات.',
           'نَصٌّ أَكَادِيمِيّ 2026 English mixed [MASK]', 'دراسة بحثية طويلة '*1000]
    for batch in ([texts[0]],texts[:2],texts[1:],texts):
        reference=expected(batch,padding=True,truncation=True,max_length=512,return_tensors='pt')
        observed=actual(batch)
        for key in ('input_ids','attention_mask','token_type_ids'):
            assert reference[key].equal(observed[key]), key
