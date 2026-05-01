import pytest
from esco_pipeline.enrichment import GraphEnrichment
from esco_pipeline.esco_interface import ESCOIndexInterface, ESCOSkill


class HierarchyMockIndex(ESCOIndexInterface):
    """Minimal ESCO index with a small hierarchy for testing enrichment."""

    SKILLS = {
        "A": ESCOSkill(uri="A", preferred_label="skill A"),
        "B": ESCOSkill(uri="B", preferred_label="skill B"),
        "C": ESCOSkill(uri="C", preferred_label="skill C"),  # parent of A, B
        "D": ESCOSkill(uri="D", preferred_label="skill D"),  # sibling of A (same parent C)
    }
    # A -> parent C; B -> parent C; D -> parent C
    _parents = {"A": "C", "B": "C", "D": "C"}
    _children = {"C": ["A", "B", "D"]}

    def get_skill(self, uri): return self.SKILLS.get(uri)
    def get_all_labels(self): return {v.preferred_label: k for k, v in self.SKILLS.items()}
    def uri_exists(self, uri): return uri in self.SKILLS
    def search_by_embedding(self, text, top_k=5): return []

    def get_parent(self, uri):
        parent_uri = self._parents.get(uri)
        return self.SKILLS.get(parent_uri) if parent_uri else None

    def get_children(self, uri):
        return [self.SKILLS[u] for u in self._children.get(uri, []) if u in self.SKILLS]

    def get_siblings(self, uri):
        parent = self.get_parent(uri)
        if parent is None:
            return []
        return [
            self.SKILLS[u]
            for u in self._children.get(parent.uri, [])
            if u != uri and u in self.SKILLS
        ]


@pytest.fixture
def hierarchy_index():
    return HierarchyMockIndex()


def test_enrich_adds_parent(hierarchy_index):
    enrichment = GraphEnrichment(hierarchy_index)
    result, graph_cats, scores = enrichment.enrich(["A"])
    assert "C" in result  # parent of A
    assert "C" in graph_cats
    assert graph_cats["C"] == "graph_parent"


def test_enrich_adds_siblings(hierarchy_index):
    enrichment = GraphEnrichment(hierarchy_index)
    result, graph_cats, scores = enrichment.enrich(["A"])
    assert "B" in result  # sibling of A
    assert "D" in result  # sibling of A
    assert graph_cats["B"] == "graph_sibling"
    assert graph_cats["D"] == "graph_sibling"


def test_enrich_preserves_original(hierarchy_index):
    enrichment = GraphEnrichment(hierarchy_index)
    result, graph_cats, scores = enrichment.enrich(["A"])
    assert "A" in result
    assert result[0] == "A"  # original URIs come first
    assert "A" not in graph_cats


def test_enrich_no_duplicates(hierarchy_index):
    enrichment = GraphEnrichment(hierarchy_index)
    result, graph_cats, scores = enrichment.enrich(["A", "B"])
    assert len(result) == len(set(result))


def test_enrich_no_hierarchy(mock_esco_index):
    # MockESCOIndex has no hierarchy: get_parent returns None, get_siblings returns []
    enrichment = GraphEnrichment(mock_esco_index)
    uris = ["http://data.europa.eu/esco/skill/S001", "http://data.europa.eu/esco/skill/S002"]
    result, graph_cats, scores = enrichment.enrich(uris)
    assert result == uris
    assert graph_cats == {}


def test_enrich_empty_list(hierarchy_index):
    enrichment = GraphEnrichment(hierarchy_index)
    result, graph_cats, scores = enrichment.enrich([])
    assert result == []
    assert graph_cats == {}


def test_enrich_uri_without_parent(hierarchy_index):
    # C has no parent in our test hierarchy
    enrichment = GraphEnrichment(hierarchy_index)
    result, graph_cats, scores = enrichment.enrich(["C"])
    assert "C" in result
    # C has no parent, so no parent added; children are not added (only parent/siblings)
    assert "A" not in result


def test_enrich_scores_with_input(hierarchy_index):
    enrichment = GraphEnrichment(hierarchy_index)
    uri_scores = {"A": 0.9}
    result, graph_cats, scores = enrichment.enrich(["A"], uri_scores=uri_scores)
    assert scores["A"] == 0.9
    # Parent C inherits child score directly
    assert scores["C"] == pytest.approx(0.9)
    # Siblings should have default score (no source texts, no embedding sim)
    assert "B" in scores
    assert "D" in scores
