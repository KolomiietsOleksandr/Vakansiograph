import pytest
from esco_pipeline.evaluation import evaluate, _average_metrics, EvaluationMetrics
from esco_pipeline.models import DocumentResult, ESCOMapping


def _make_doc(doc_id, mapped_uris, unmapped_skills=None):
    mappings = [
        ESCOMapping(raw_skill=f"skill_{i}", esco_uri=uri, esco_label="label", confidence=1.0, method="test")
        for i, uri in enumerate(mapped_uris)
    ]
    return DocumentResult(
        document_id=doc_id,
        direct_mappings=mappings,
        graph_mappings=[],
        unmapped_skills=unmapped_skills or [],
    )


def test_evaluate_perfect_match():
    doc = _make_doc("doc1", ["uri:A", "uri:B"])
    gold = {"doc1": ["uri:A", "uri:B"]}
    metrics = evaluate([doc], gold)
    assert metrics["doc1"].precision == 1.0
    assert metrics["doc1"].recall == 1.0
    assert metrics["doc1"].f1 == 1.0


def test_evaluate_partial_match():
    doc = _make_doc("doc1", ["uri:A", "uri:B", "uri:C"])
    gold = {"doc1": ["uri:A", "uri:B"]}
    metrics = evaluate([doc], gold)
    m = metrics["doc1"]
    # tp=2, fp=1, fn=0
    assert m.precision == pytest.approx(2 / 3, abs=1e-4)
    assert m.recall == 1.0
    assert m.f1 > 0


def test_evaluate_no_match():
    doc = _make_doc("doc1", ["uri:X"])
    gold = {"doc1": ["uri:A"]}
    metrics = evaluate([doc], gold)
    m = metrics["doc1"]
    assert m.precision == 0.0
    assert m.recall == 0.0
    assert m.f1 == 0.0


def test_evaluate_all_unmapped():
    doc = _make_doc("doc1", [], unmapped_skills=["skill1", "skill2"])
    gold = {"doc1": ["uri:A"]}
    metrics = evaluate([doc], gold)
    m = metrics["doc1"]
    assert m.recall == 0.0
    assert m.unmapped_rate == 1.0


def test_evaluate_skips_doc_not_in_gold():
    doc = _make_doc("doc_not_in_gold", ["uri:A"])
    gold = {"other_doc": ["uri:A"]}
    metrics = evaluate([doc], gold)
    assert "doc_not_in_gold" not in metrics


def test_evaluate_false_positive_rate():
    doc = _make_doc("doc1", ["uri:X", "uri:Y"])  # neither in gold
    gold = {"doc1": ["uri:A"]}
    metrics = evaluate([doc], gold)
    assert metrics["doc1"].false_positive_rate == 1.0


def test_evaluate_unmapped_rate():
    doc = _make_doc("doc1", ["uri:A"], unmapped_skills=["b", "c"])
    gold = {"doc1": ["uri:A"]}
    metrics = evaluate([doc], gold)
    # total = 1 mapped + 2 unmapped = 3; unmapped_rate = 2/3
    assert metrics["doc1"].unmapped_rate == pytest.approx(2 / 3, abs=1e-4)


def test_average_metrics_empty():
    avg = _average_metrics({})
    assert avg.precision == 0.0
    assert avg.recall == 0.0
    assert avg.f1 == 0.0


def test_average_metrics_single():
    m = EvaluationMetrics(precision=0.8, recall=0.6, f1=0.686, unmapped_rate=0.1, false_positive_rate=0.2, coverage=0.9)
    avg = _average_metrics({"doc1": m})
    assert avg.precision == 0.8
    assert avg.recall == 0.6


def test_average_metrics_multiple():
    m1 = EvaluationMetrics(precision=1.0, recall=1.0, f1=1.0, unmapped_rate=0.0, false_positive_rate=0.0, coverage=1.0)
    m2 = EvaluationMetrics(precision=0.0, recall=0.0, f1=0.0, unmapped_rate=1.0, false_positive_rate=1.0, coverage=0.0)
    avg = _average_metrics({"d1": m1, "d2": m2})
    assert avg.precision == 0.5
    assert avg.recall == 0.5
    assert avg.f1 == 0.5
