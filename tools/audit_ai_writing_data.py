"""Audit local JSON/JSONL in isolation; no downloads or content in output."""
import argparse
import json
from pathlib import Path

from plagiarism_detector.ai_detection.quality_audit import audit_records
from tools.validate_ai_writing_dataset import _read_records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dataset', type=Path)
    parser.add_argument('--min-words', type=int, default=20)
    args = parser.parse_args()
    print(json.dumps(audit_records(_read_records(args.dataset), args.min_words), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
