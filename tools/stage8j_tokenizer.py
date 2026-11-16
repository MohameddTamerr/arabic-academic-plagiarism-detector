"""Research-only direct use of a verified serialized fast tokenizer."""


class LocalFastTokenizer:
    def __init__(self, path):
        from tokenizers import Tokenizer
        self.tokenizer = Tokenizer.from_file(str(path))
        pad = self.tokenizer.token_to_id('[PAD]')
        if pad is None:
            raise ValueError('Missing padding token')
        self.tokenizer.enable_padding(pad_id=pad, pad_token='[PAD]')
        self.tokenizer.enable_truncation(max_length=512)

    def __call__(self, texts, *, padding=True, truncation=True, max_length=512, return_tensors='pt'):
        if (padding, truncation, max_length, return_tensors) != (True, True, 512, 'pt'):
            raise ValueError('Research tokenizer supports only the validated 512-token padded profile')
        import torch
        encoded = self.tokenizer.encode_batch(texts)
        return {key: torch.tensor([getattr(item, attribute) for item in encoded], dtype=torch.long)
                for key, attribute in (('input_ids', 'ids'),
                    ('attention_mask', 'attention_mask'), ('token_type_ids', 'type_ids'))}
