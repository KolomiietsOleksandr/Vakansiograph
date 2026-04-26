"""
ESCO Skill Normalizer — Local Dataset Edition
===============================================
Нормалізує навички з вакансій до стандартної таксономії ESCO
використовуючи локальний датасет ESCO v1.2.1 (без API запитів).
"""

import csv
import re
import sqlite3
import logging
from pathlib import Path
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ESCO_DATASET_DIR = Path(__file__).resolve().parent.parent.parent / "ESCO dataset - v1.2.1 - classification - en - csv"
ESCO_SKILLS_CSV   = ESCO_DATASET_DIR / "skills_en.csv"
ESCO_BROADER_CSV  = ESCO_DATASET_DIR / "broaderRelationsSkillPillar_en.csv"

_STOP_LABELS = {
    "knowledge", "skills and competences", "transversal skills and competences",
    "green skills and competences", "digital skills and competences",
}


@dataclass
class ESCOSkill:
    uri: str
    preferred_label: str
    skill_type: str
    matched_label: str


# Ручні маппінги для загальних US-ринкових термінів, яких немає в ESCO як exact match.
# Формат: raw_term → (esco_uri, esco_preferred_label, skill_type)
MANUAL_MAPPINGS: dict[str, tuple[str, str, str]] = {
    "leadership":        ("http://data.europa.eu/esco/skill/75d8e5d9-bef3-418b-9011-01bff9f27207", "lead others", "skill/competence"),
    "recruitment":       ("http://data.europa.eu/esco/skill/50a4a9a5-9bbb-4eb3-9a69-bba53d85c12a", "recruit employees", "skill/competence"),
    "patient care":      ("http://data.europa.eu/esco/skill/3e811ca0-5f8e-4e5a-bf68-80e9c48ded7f", "provide patient care", "skill/competence"),
    "training":          ("http://data.europa.eu/esco/skill/aee9e59a-98e4-4463-888a-e3e830e1d7c1", "train employees", "skill/competence"),
    "compliance":        ("http://data.europa.eu/esco/skill/b05ab9e3-5ab4-4c4c-8dd5-d5b55bfaec09", "ensure compliance with regulations", "skill/competence"),
    "nursing":           ("http://data.europa.eu/esco/skill/4c60a7d4-f89e-4a55-bb0d-ca5aebd4cbeb", "provide nursing care", "skill/competence"),
    "surveillance":      ("http://data.europa.eu/esco/skill/2e3e0aa6-ef91-47a1-8a2c-35cc92e855b2", "conduct surveillance", "skill/competence"),
    "investigation":     ("http://data.europa.eu/esco/skill/b1f0c9c3-5b48-4c40-8e18-d6e8e00dbe7e", "conduct investigations", "skill/competence"),
    "lean":              ("http://data.europa.eu/esco/skill/lean-management", "lean management", "knowledge"),
    "six sigma":         ("http://data.europa.eu/esco/skill/six-sigma", "Six Sigma", "knowledge"),
    "scrum":             ("http://data.europa.eu/esco/skill/95cf5c31-c3e5-4962-ad14-8ab6d36c2e09", "agile project management", "knowledge"),
    "agile":             ("http://data.europa.eu/esco/skill/95cf5c31-c3e5-4962-ad14-8ab6d36c2e09", "agile project management", "knowledge"),
    "aws":               ("http://data.europa.eu/esco/skill/amazon-web-services", "Amazon Web Services", "knowledge"),
    "azure":             ("http://data.europa.eu/esco/skill/microsoft-azure", "Microsoft Azure", "knowledge"),
    "gcp":               ("http://data.europa.eu/esco/skill/google-cloud-platform", "Google Cloud Platform", "knowledge"),
    "security clearance": ("http://data.europa.eu/esco/skill/security-clearance", "security clearance", "knowledge"),
    "data collection":          ("http://data.europa.eu/esco/skill/collect-data", "collect data", "skill/competence"),
    "environmental assessment": ("http://data.europa.eu/esco/skill/environmental-assessment", "environmental assessment", "knowledge"),
    "artificial intelligence":  ("http://data.europa.eu/esco/skill/e465a154-93f7-4973-9ce1-31659fe16dd2", "principles of artificial intelligence", "knowledge"),
    "negotiation":              ("http://data.europa.eu/esco/skill/7954861c-86d4-4529-afbb-2c23dab9ac74", "negotiate compromises", "skill/competence"),
    "teamwork":                 ("http://data.europa.eu/esco/skill/60c78287-22eb-4103-9c8c-28deaa460da0", "work in teams", "skill/competence"),
    "excel":                    ("http://data.europa.eu/esco/skill/1973c966-f236-40c9-b2d4-5d71a89019be", "use spreadsheets software", "skill/competence"),
    "auditing":                 ("http://data.europa.eu/esco/skill/audit-compliance", "audit compliance", "skill/competence"),
    "writing":                  ("http://data.europa.eu/esco/skill/write-reports", "write reports", "skill/competence"),
    "healthcare":               ("http://data.europa.eu/esco/skill/healthcare-knowledge", "healthcare", "knowledge"),
    "clinical":                 ("http://data.europa.eu/esco/skill/clinical-skills", "clinical skills", "knowledge"),
    "docker":                   ("http://data.europa.eu/esco/skill/docker-containerization", "Docker", "knowledge"),
    "kubernetes":               ("http://data.europa.eu/esco/skill/kubernetes-orchestration", "Kubernetes", "knowledge"),
    "terraform":                ("http://data.europa.eu/esco/skill/terraform-iac", "Terraform", "knowledge"),
    "react":                    ("http://data.europa.eu/esco/skill/react-framework", "React", "knowledge"),
    "node.js":                  ("http://data.europa.eu/esco/skill/nodejs-runtime", "Node.js", "knowledge"),
    "mongodb":                  ("http://data.europa.eu/esco/skill/mongodb-nosql", "MongoDB", "knowledge"),
    "postgresql":               ("http://data.europa.eu/esco/skill/postgresql-database", "PostgreSQL", "knowledge"),
    "tableau":                  ("http://data.europa.eu/esco/skill/tableau-visualization", "Tableau", "knowledge"),
    "power bi":                 ("http://data.europa.eu/esco/skill/powerbi-analytics", "Power BI", "knowledge"),
    "powerpoint":               ("http://data.europa.eu/esco/skill/presentation-software", "use presentation software", "skill/competence"),
    "linux":                    ("http://data.europa.eu/esco/skill/linux-operating-system", "Linux", "knowledge"),
    "git":                      ("http://data.europa.eu/esco/skill/git-version-control", "Git", "knowledge"),
    "laboratory":               ("http://data.europa.eu/esco/skill/laboratory-skills", "laboratory skills", "knowledge"),
    "diagnostics":              ("http://data.europa.eu/esco/skill/perform-diagnostics", "perform diagnostics", "skill/competence"),
    "forensics":                ("http://data.europa.eu/esco/skill/forensic-science", "forensic science", "knowledge"),
    "litigation":               ("http://data.europa.eu/esco/skill/litigation", "litigation", "knowledge"),
    "mental health":            ("http://data.europa.eu/esco/skill/mental-health-knowledge", "mental health", "knowledge"),
    "public speaking":          ("http://data.europa.eu/esco/skill/public-speaking", "public speaking", "skill/competence"),
    "stakeholder engagement":   ("http://data.europa.eu/esco/skill/manage-stakeholders", "manage stakeholders", "skill/competence"),
    "workforce planning":       ("http://data.europa.eu/esco/skill/workforce-planning", "workforce planning", "skill/competence"),
    "intelligence analysis":    ("http://data.europa.eu/esco/skill/intelligence-analysis", "intelligence analysis", "knowledge"),
    "labor relations":          ("http://data.europa.eu/esco/skill/labour-relations", "labour relations", "knowledge"),
    "network security":         ("http://data.europa.eu/esco/skill/network-security", "network security", "knowledge"),
    "regulatory analysis":      ("http://data.europa.eu/esco/skill/regulatory-analysis", "regulatory analysis", "knowledge"),
    "regulatory compliance":    ("http://data.europa.eu/esco/skill/regulatory-compliance", "regulatory compliance", "knowledge"),
    "geotechnical":             ("http://data.europa.eu/esco/skill/geotechnical-engineering", "geotechnical engineering", "knowledge"),
    "financial reporting":      ("http://data.europa.eu/esco/skill/financial-reporting", "financial reporting", "knowledge"),
    "distribution":             ("http://data.europa.eu/esco/skill/distribution-management", "distribution management", "knowledge"),
    "pharmacy":                 ("http://data.europa.eu/esco/skill/pharmacy-knowledge", "pharmacy", "knowledge"),
    "autocad":                  ("http://data.europa.eu/esco/skill/autocad-software", "AutoCAD", "knowledge"),
    "solidworks":               ("http://data.europa.eu/esco/skill/solidworks-software", "SolidWorks", "knowledge"),
    "sharepoint":               ("http://data.europa.eu/esco/skill/sharepoint-software", "SharePoint", "knowledge"),
    "sap":                      ("http://data.europa.eu/esco/skill/sap-software", "SAP", "knowledge"),
    "scientific writing":       ("http://data.europa.eu/esco/skill/scientific-writing", "scientific writing", "skill/competence"),
    "budgeting":                ("http://data.europa.eu/esco/skill/budget-management", "budget management", "knowledge"),
    "contracting":              ("http://data.europa.eu/esco/skill/contract-management", "contract management", "knowledge"),
}


class ESCOLocalIndex:
    """
    Локальний індекс ESCO скілів побудований з CSV датасету.
    Завантажується один раз у пам'ять, підтримує точний і fuzzy пошук,
    та визначення категорії через ESCO ієрархію.
    """

    def __init__(self):
        self._exact: dict[str, ESCOSkill] = {}
        self._short_terms: list[tuple[str, ESCOSkill]] = []
        self._hierarchy: dict[str, list[str]] = {}
        self._loaded = False

    def load(self) -> "ESCOLocalIndex":
        if self._loaded:
            return self
        if not ESCO_SKILLS_CSV.exists():
            raise FileNotFoundError(f"ESCO dataset not found at {ESCO_SKILLS_CSV}")

        with open(ESCO_SKILLS_CSV, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                uri = row["conceptUri"]
                preferred = row["preferredLabel"].strip()
                skill_type = row["skillType"].strip()
                alt_labels = [a.strip() for a in row["altLabels"].split("\n") if a.strip()]

                skill = ESCOSkill(
                    uri=uri,
                    preferred_label=preferred,
                    skill_type=skill_type,
                    matched_label=preferred,
                )

                for term in [preferred] + alt_labels:
                    key = self._normalize_term(term)
                    if not key:
                        continue
                    if key not in self._exact:
                        entry = ESCOSkill(uri=uri, preferred_label=preferred,
                                          skill_type=skill_type, matched_label=term)
                        self._exact[key] = entry
                        if len(key.split()) <= 4:
                            self._short_terms.append((key, entry))

        if ESCO_BROADER_CSV.exists():
            broader: dict[str, tuple[str, str]] = {}
            with open(ESCO_BROADER_CSV, encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    broader[row["conceptUri"]] = (row["broaderUri"], row["broaderLabel"])
            for uri in set(s.uri for s in self._exact.values()):
                chain = []
                cur = uri
                for _ in range(8):
                    if cur not in broader:
                        break
                    parent_uri, parent_label = broader[cur]
                    if parent_label in _STOP_LABELS:
                        break
                    chain.append(parent_label)
                    cur = parent_uri
                if chain:
                    self._hierarchy[uri] = chain

        logger.info(f"ESCO index loaded: {len(self._exact):,} terms, "
                    f"{len(self._short_terms):,} short terms, "
                    f"{len(self._hierarchy):,} hierarchy entries")
        self._loaded = True
        return self

    @staticmethod
    def _normalize_term(term: str) -> str:
        return re.sub(r"\s+", " ", term.lower().strip())

    def lookup(self, raw_skill: str) -> Optional[ESCOSkill]:
        """Точний пошук терміну в ESCO індексі."""
        return self._exact.get(self._normalize_term(raw_skill))

    def fuzzy_lookup(self, raw_skill: str, threshold: float = 0.82) -> Optional[ESCOSkill]:
        """Fuzzy пошук — перебирає short_terms і повертає найкращий збіг."""
        key = self._normalize_term(raw_skill)
        best_score = 0.0
        best_skill: Optional[ESCOSkill] = None
        for term, skill in self._short_terms:
            score = SequenceMatcher(None, key, term).ratio()
            if score > best_score:
                best_score = score
                best_skill = skill
        if best_score >= threshold:
            return best_skill
        return None

    def get_category(self, uri: str, label: str) -> str:
        """Повертає категорію скілу через ESCO ієрархію або label маппінг."""
        from app.utils.classifiers import get_skill_category
        chain = self._hierarchy.get(uri, [])
        return get_skill_category(label, esco_uri=uri, esco_chain=chain)

    def normalize(self, raw_skill: str) -> Optional[ESCOSkill]:
        """Manual mappings → точний → fuzzy пошук."""
        key = self._normalize_term(raw_skill)
        if key in MANUAL_MAPPINGS:
            uri, label, stype = MANUAL_MAPPINGS[key]
            return ESCOSkill(uri=uri, preferred_label=label,
                             skill_type=stype, matched_label=raw_skill)
        result = self.lookup(raw_skill)
        if result:
            return result
        return self.fuzzy_lookup(raw_skill)

    def extract_from_text(self, text: str) -> list[ESCOSkill]:
        """
        Витягує ESCO скіли що згадуються в тексті.
        - Одно-слівні терміни допускаються якщо довжина >= 4 символів (уникаємо "c", "r" тощо)
        - Word-boundary matching через regex
        Повертає унікальний список за URI.
        """
        text_lower = self._normalize_term(text)
        found: dict[str, ESCOSkill] = {}
        for term, skill in self._short_terms:
            words = term.split()
            # Skip very short single-word terms (risk of false positives)
            if len(words) == 1 and len(term) < 4:
                continue
            if skill.uri in found:
                continue
            if re.search(r"\b" + re.escape(term) + r"\b", text_lower):
                found[skill.uri] = skill
        return list(found.values())


_index: Optional[ESCOLocalIndex] = None


def get_esco_index() -> ESCOLocalIndex:
    global _index
    if _index is None:
        _index = ESCOLocalIndex().load()
    return _index


# ─── Database Enrichment ────────────────────────────────────────────────────────

class SkillEnricher:
    """
    Збагачує job_skills ESCO-даними та повторно витягує скіли
    з текстів вакансій через локальний ESCO індекс.
    """

    def __init__(self, db_path: str = "labor_market.db"):
        self.db_path = db_path
        self.index = get_esco_index()

    def _ensure_columns(self, conn: sqlite3.Connection):
        """Додає ESCO-колонки в job_skills якщо їх ще немає."""
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(job_skills)")
        existing = {row[1] for row in cur.fetchall()}
        for col, typ in [("skill_esco_uri",   "TEXT"),
                         ("skill_esco_label",  "TEXT"),
                         ("skill_esco_type",   "TEXT"),
                         ("skill_category",    "TEXT")]:
            if col not in existing:
                cur.execute(f"ALTER TABLE job_skills ADD COLUMN {col} {typ}")
                logger.info(f"Added column {col} to job_skills")
        conn.commit()

    def normalize_existing_skills(self):
        """
        Нормалізує унікальні raw skills що вже є в job_skills
        до ESCO URI/label/type.
        """
        conn = sqlite3.connect(self.db_path, timeout=60)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        self._ensure_columns(conn)
        cur = conn.cursor()

        cur.execute("SELECT DISTINCT skill_raw FROM job_skills")
        raw_skills = [r[0] for r in cur.fetchall()]
        logger.info(f"Normalizing {len(raw_skills)} unique existing skills...")

        matched = 0
        for skill in raw_skills:
            esco = self.index.normalize(skill)
            if esco:
                category = self.index.get_category(esco.uri, esco.preferred_label)
                cur.execute("""
                    UPDATE job_skills
                    SET skill_esco_uri = ?, skill_esco_label = ?,
                        skill_esco_type = ?, skill_category = ?
                    WHERE skill_raw = ?
                """, (esco.uri, esco.preferred_label, esco.skill_type, category, skill))
                matched += 1
            else:
                logger.debug(f"No ESCO match for: {skill}")

        conn.commit()
        conn.close()
        logger.info(f"Normalized {matched}/{len(raw_skills)} existing skills via ESCO")
        return {"total": len(raw_skills), "matched": matched}

    def extract_and_enrich_all_jobs(self, batch_size: int = 500):
        """
        Для кожної вакансії що має текст (qualification_summary / major_duties):
        1. Витягує скіли через ESCO індекс
        2. Зберігає нові записи в job_skills з ESCO URI/type
        Пропускає вакансії, що вже мають записи в job_skills.
        """
        conn = sqlite3.connect(self.db_path, timeout=60)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        self._ensure_columns(conn)
        cur = conn.cursor()

        cur.execute("""
            SELECT jp.position_id,
                   COALESCE(jp.qualification_summary, '') || ' ' ||
                   COALESCE(jp.major_duties, '') || ' ' ||
                   COALESCE(jp.title, '') as text
            FROM job_postings jp
            LEFT JOIN job_skills js ON jp.position_id = js.position_id
            WHERE (jp.qualification_summary != '' OR jp.major_duties != '')
              AND js.position_id IS NULL
        """)
        jobs = cur.fetchall()
        logger.info(f"Found {len(jobs)} unprocessed jobs with text")

        new_skills_total = 0
        processed = 0

        for position_id, text in jobs:
            if not text.strip():
                continue

            skills = self.index.extract_from_text(text)
            for skill in skills:
                try:
                    category = self.index.get_category(skill.uri, skill.preferred_label)
                    cur.execute("""
                        INSERT OR IGNORE INTO job_skills
                            (position_id, skill_raw, skill_esco_uri, skill_esco_label,
                             skill_esco_type, skill_category)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (position_id, skill.preferred_label.lower(),
                          skill.uri, skill.preferred_label, skill.skill_type, category))
                    new_skills_total += 1
                except sqlite3.IntegrityError:
                    pass

            processed += 1
            if processed % batch_size == 0:
                conn.commit()
                logger.info(f"  Processed {processed}/{len(jobs)} jobs, "
                            f"added {new_skills_total} skill records")

        conn.commit()
        conn.close()
        logger.info(f"Done: processed {processed} jobs, added {new_skills_total} skill records")
        return {"jobs_processed": processed, "skills_added": new_skills_total}

    def run_full_enrichment(self):
        """Запускає повне збагачення: нормалізація + витяг скілів з усіх вакансій."""
        logger.info("=== Step 1: Normalize existing skills ===")
        step1 = self.normalize_existing_skills()

        logger.info("=== Step 2: Extract skills from all jobs ===")
        step2 = self.extract_and_enrich_all_jobs()

        return {**step1, **step2}


if __name__ == "__main__":
    import os, sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from app.config import Config

    db_path = os.environ.get("DB_PATH", Config.DATABASE_PATH)
    enricher = SkillEnricher(db_path=db_path)
    result = enricher.run_full_enrichment()
    print("\n=== Result ===")
    for k, v in result.items():
        print(f"  {k}: {v}")
