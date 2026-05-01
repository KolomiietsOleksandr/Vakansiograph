# Scored Candidate Ranking — Analysis & Rationale

## Problem

`_prefetch_candidates` in `LLMMapper` accumulated candidate URIs from fuzzy, embedding, and graph enrichment in insertion order with no scoring. Truncation to `llm_max_candidates` (100) arbitrarily dropped later-added candidates (typically graph siblings).

Analysis of 599 mappings across 24 documents:
- 98.2% direct (fuzzy/embedding), 1.8% graph, 20.5% unmapped
- Graph mappings are rare but high-confidence (mean 0.95)
- Many unmapped skills ("Навички продажів", "MS Excel", "Ведення переговорів") are clearly ESCO-mappable — likely missing from candidate pool due to arbitrary truncation

## Score Ranges by Category

| Category | Score Source | Typical Range |
|----------|-------------|---------------|
| fuzzy | `mapping.confidence` (0-1) | 0.80–1.00 |
| embedding | raw cosine similarity | 0.75–0.95 |
| graph_parent | child_score (inherited) | 0.80–1.00 |
| graph_sibling | embedding similarity to source text | 0.50–0.90 |

## Slot Allocation

Minimum guaranteed slots per category (out of 100 total):

| Category | Min Slots | Rationale |
|----------|-----------|-----------|
| fuzzy | 15 | High-precision matches, most frequently selected by LLM |
| embedding | 15 | Catches semantic matches missed by fuzzy |
| graph_sibling | 5 | Rare but high-confidence when selected |
| graph_parent | 3 | Broader concepts, occasionally useful for context |

Remaining slots (62+) filled by global score ranking across all categories.

## Design Decisions

1. **Sibling score = max_sim**: Already computed during filtering, represents actual semantic relevance.
2. **Category-first then score-fill**: Guarantees diversity without sacrificing overall quality.
3. **Final sort by score**: LLM sees highest-confidence candidates first, improving prompt quality.

Output analyses:

## Comparison: Weighted vs Original LLM Two-Stage CV Results

Comparing `output/cv_results_weight_llm_two_stage.jsonl` (scored candidate ranking) vs `output/cv_results_llm_two_stage.jsonl` (original insertion-order truncation) across 3 CV documents (164 total skills).

### Aggregate

| Metric | Original | Weighted | Delta |
|--------|----------|----------|-------|
| Mapped | 124/164 (75.6%) | 128/164 (78.0%) | **+4 (+2.4pp)** |
| Unmapped | 40 | 36 | **-4** |
| Avg confidence | 0.901 | 0.930 | **+0.029** |
| Graph mappings | 0 | 3 | **+3** |

### Per-Document

| Doc | Original mapped | Weighted mapped | Δ |
|-----|----------------|-----------------|---|
| 14682931 (admin/beauty salon) | 16/21 (76%) | **21/21 (100%)** | **+5** |
| 10985368 (lawyer, multi-role) | 61/87 (70%) | 60/87 (69%) | -1 |
| 980817 (business/sales manager) | 47/56 (84%) | 47/56 (84%) | 0 |

### Doc 14682931 — Big win: 5 previously unmapped skills now mapped
All 5 newly-mapped: Вміння працювати з касовим апаратом, Грамотна усна мова, Здійснення вихідних дзвінків, Комунікабельність, Пунктуальність. Zero skills lost.

### Doc 10985368 — Mixed: +11 gained, -12 lost (net -1)
**Newly mapped (11)**: Вільне орієнтування в законодавчій базі, Законодавство України, Збір інформації, Контекстна реклама, Правове забезпечення, Написання рекламних статей, Наполегливість, Перевірка контрагентів, Підготовка до публічних виступів, Складання депутатських запитів, Юридичне письмо

**Lost (12)**: Ведення переговорів, Вирішення міграційних питань, Вміння вести переговори, Здатність до формулювання точки зору, Кадрове діловодство, Організаторські здібності, Реєстрація компаній, Робота в госп./цивіл. судах (2), Судовий супровід, Супровід бухгалт. аутсорсингу, Швидке навчання

### Doc 980817 — Swap: +3 gained, -3 lost (net 0)

### Quality of Mapping Changes (92 skill-level differences across all docs)

#### Clear improvements (~14 cases)
Weighted finds more specific/accurate ESCO labels:
- "Багатозадачність" → "виконувати кілька завдань одночасно" (was: "обробляти кілька замовлень")
- "Уважність до деталей" → "приділяти увагу деталям" (was: "зберігати концентрацію уваги")
- "Відповідальність" → "нести відповідальність" (was: "відповідальність за управління бізнесом")
- "Керівництво виробничим підприємством" → exact match (was: "керувати малим бізнесом")
- "Управління відділом продажів" → "керувати відділами продажів" (was: "керувати колективом")
- "Управління запасами" → "управляти запасами" (was: "логістика")
- "Юридичне консультування" → "консультувати щодо юридичних послуг" (was: "консультувати керівників")
- "Відкриття рахунків в ЄС" → "відкривати банківські рахунки" (was: "консультувати щодо")
- "Знання нормативно-правової бази" → "забезпечувати виконання вимог законодавства" (was: "отримувати дозволи")

#### Clear regressions (~9 cases)
Weighted picks overly generic or wrong ESCO labels:
- "MS Office" → "навички роботи на комп'ютері" (was: exact match "використовувати Microsoft Office")
- "SMM" → "розробляти рекламні інструменти" (was: "маркетинг у соціальних мережах")
- "Транспортна логістика" → "керувати операціями дистрибуції" (was: "мультимодальна транспортна логістика")
- "Робота в адмін. судах" → "складати юридичні документи" (was: "представляти інтереси в судах")
- "Управління бізнесом" → "стратегічне планування" (was: "відповідальність за управління бізнесом")
- "Розвиток партнерської мережі" → "нові можливості для бізнесу" (was: "розвивати професійну мережу")

#### Pattern: over-concentration on popular candidates
Weighted version shows a tendency to map many different skills to the same high-scoring ESCO label — e.g., many legal skills → "складати юридичні документи", many business skills → "визначати нові можливості". This suggests the score-based ranking pushes certain candidates too high, causing the LLM to favor them.

### Conclusions

1. **Coverage improved**: +2.4pp mapped rate, +3 graph mappings — the scored ranking does surface better candidates
2. **Precision improved for generic skills**: soft skills and generic competencies map much better (Відповідальність, Стресостійкість, etc.)
3. **Regression for specific skills**: when the original had a precise ESCO match (MS Office, SMM, transport logistics), the weighted version sometimes picks a more generic alternative — likely because the precise match got a lower retrieval score and appears lower in the candidate list
4. **Over-concentration problem**: high-scoring candidates dominate, causing LLM to reuse them across many different skills

### Fix applied: Boost high-confidence fuzzy matches (≥0.95 → +0.15 bonus)
Ensures near-exact fuzzy matches (e.g., "MS Office" → "використовувати Microsoft Office") always outrank generic embedding candidates in the scored ranking.

