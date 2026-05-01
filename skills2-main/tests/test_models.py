from esco_pipeline.models import DocumentResult, ESCOMapping, SkillSource, Vacancy


def test_skill_source_creation():
    ss = SkillSource(text="Python", source="platform_array", confidence=1.0)
    assert ss.text == "Python"
    assert ss.source == "platform_array"
    assert ss.confidence == 1.0


def test_vacancy_defaults():
    v = Vacancy(id="1", title="Developer")
    assert v.raw_skills == []
    assert v.extracted_skills == []
    assert v.description_text == ""
    assert v.location == ""
    assert v.company_name == ""
    assert v.salary == ""


def test_vacancy_with_skills():
    v = Vacancy(id="2", title="Engineer", raw_skills=["Python", "SQL"])
    assert len(v.raw_skills) == 2


def test_esco_mapping_creation():
    m = ESCOMapping(
        raw_skill="Python",
        esco_uri="http://data.europa.eu/esco/skill/S001",
        esco_label="Python programming",
        confidence=0.95,
        method="fuzzy",
    )
    assert m.method == "fuzzy"
    assert m.details == {}


def test_document_result_defaults():
    dr = DocumentResult(document_id="doc1")
    assert dr.direct_mappings == []
    assert dr.graph_mappings == []
    assert dr.unmapped_skills == []
    assert dr.metadata == {}


def test_document_result_with_data():
    mapping = ESCOMapping(
        raw_skill="Python",
        esco_uri="http://data.europa.eu/esco/skill/S001",
        esco_label="Python programming",
        confidence=0.9,
        method="fuzzy",
    )
    dr = DocumentResult(
        document_id="doc1",
        direct_mappings=[mapping],
        graph_mappings=[],
        unmapped_skills=["unknown skill"],
        metadata={"mapper": "fuzzy"},
    )
    assert len(dr.direct_mappings) == 1
    assert len(dr.graph_mappings) == 0
    assert len(dr.unmapped_skills) == 1
    assert dr.metadata["mapper"] == "fuzzy"
