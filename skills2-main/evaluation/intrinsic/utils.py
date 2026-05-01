import json
from pathlib import Path

from esco_pipeline.esco_interface import ESCOIndexInterface, ESCOSkill


def count_lines(path: str | Path) -> int:
    count = 0
    with open(path, "r") as f:
        for _ in f:
            count += 1
    return count


def stream_jsonl(path: str | Path):
    total = count_lines(path)
    with open(path, "r") as f:
        for i, line in enumerate(f, 1):
            if i % 1000 == 0:
                print(f"  Progress: {i}/{total} lines")
            line = line.strip()
            if line:
                yield json.loads(line)
    print(f"  Done: {total} lines total")


class NoGraphESCOIndex(ESCOIndexInterface):
    """Wrapper that disables graph traversal (parent/sibling lookups)."""

    def __init__(self, inner: ESCOIndexInterface):
        self._inner = inner

    def get_skill(self, uri: str) -> ESCOSkill | None:
        return self._inner.get_skill(uri)

    def get_all_labels(self) -> dict[str, str]:
        return self._inner.get_all_labels()

    def uri_exists(self, uri: str) -> bool:
        return self._inner.uri_exists(uri)

    def search_by_embedding(self, text: str, top_k: int = 5) -> list[tuple[str, float]]:
        return self._inner.search_by_embedding(text, top_k)

    def compute_embedding_similarity(self, text: str, uri: str) -> float:
        return self._inner.compute_embedding_similarity(text, uri)

    def batch_search_by_embedding(self, texts: list[str], top_k: int = 5) -> dict[str, list[tuple[str, float]]]:
        return self._inner.batch_search_by_embedding(texts, top_k)

    def get_parent(self, uri: str) -> None:
        return None

    def get_children(self, uri: str) -> list[ESCOSkill]:
        return self._inner.get_children(uri)

    def get_siblings(self, uri: str) -> list[ESCOSkill]:
        return []
