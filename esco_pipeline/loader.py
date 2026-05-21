import json
import logging
import random
from pathlib import Path

from datasets import load_dataset
from huggingface_hub import snapshot_download

from esco_pipeline.config import Settings
from esco_pipeline.models import Resume, Vacancy

logger = logging.getLogger(__name__)

from huggingface_hub import login

# HuggingFace authentication
login(token="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")


def load_vacancies(config: Settings) -> list[Vacancy]:
    logger.info("Loading dataset: %s", config.dataset_name)
    ds = load_dataset(config.dataset_name, split="train")

    if config.select_first is not None:
        ds = ds.select(range(min(config.select_first, len(ds))))
    elif config.sample_size is not None:
        ds = ds.shuffle(seed=config.random_seed).select(range(min(config.sample_size, len(ds))))

    vacancies = []
    for row in ds:
        skills_raw = row.get("skills") or []
        description = row.get("description_text") or ""

        # Filter: skip if no skills AND no description
        if not skills_raw and not description.strip():
            continue

        # Normalize skills field
        if isinstance(skills_raw, str):
            skills_raw = [s.strip() for s in skills_raw.split(",") if s.strip()]
        elif not isinstance(skills_raw, list):
            skills_raw = []

        vacancy = Vacancy(
            id=str(row.get("id", row.get("vacancy_id", ""))),
            title=str(row.get("title", row.get("name", "")) or ""),
            raw_skills=[str(s) for s in skills_raw if s],
            description_text=description,
            location=str(row.get("location", row.get("city", "")) or ""),
            company_name=str(row.get("company_name", row.get("employer", "")) or ""),
            salary=str(row.get("salary", "") or ""),
        )
        vacancies.append(vacancy)

    logger.info("Loaded %d vacancies", len(vacancies))
    return vacancies


def load_resumes(config: Settings) -> list[Resume]:
    logger.info("Loading dataset: %s", config.resume_dataset_name)
    # Load as raw JSONL to bypass Arrow timestamp inference that fails on
    # invalid dates like '2022-02-29' in work_experiences[].start_date.
    repo_path = snapshot_download(config.resume_dataset_name, repo_type="dataset")
    json_files = sorted(Path(repo_path).glob("**/*.jsonl"))
    if not json_files:
        json_files = sorted(Path(repo_path).glob("**/*.ndjson"))
    if not json_files:
        json_files = sorted(Path(repo_path).glob("**/*.json"))

    rows: list[dict] = []
    for fpath in json_files:
        with open(fpath, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
    logger.info("Read %d raw rows from JSONL files", len(rows))

    if config.select_first is not None:
        rows = rows[: config.select_first]
    elif config.sample_size is not None:
        rng = random.Random(config.random_seed)
        rows = rng.sample(rows, min(config.sample_size, len(rows)))

    resumes = []
    for row in rows:
        skills_raw = row.get("skills") or []
        work_experiences = row.get("work_experiences") or []
        educations = row.get("educations") or []
        additional_info = str(row.get("additional_info") or "")

        # Normalize skills field
        if isinstance(skills_raw, str):
            skills_raw = [s.strip() for s in skills_raw.split(",") if s.strip()]
        elif not isinstance(skills_raw, list):
            skills_raw = []

        # Build description_text as concat fallback
        desc_parts = []
        for exp in work_experiences:
            if isinstance(exp, dict):
                resp = exp.get("responsibilities") or ""
                if resp:
                    desc_parts.append(resp)
        if additional_info.strip():
            desc_parts.append(additional_info)
        description_text = "\n\n".join(desc_parts)

        # Filter: skip if no skills AND no work_experiences AND no description_text
        if not skills_raw and not work_experiences and not description_text.strip():
            continue

        resume = Resume(
            id=str(row.get("id", "")),
            title=str(row.get("title") or ""),
            raw_skills=[str(s) for s in skills_raw if s],
            description_text=description_text,
            location=str(row.get("city") or ""),
            candidate_name=str(row.get("candidate_name") or ""),
            salary=str(row.get("desired_salary") or ""),
            work_experiences=[e for e in work_experiences if isinstance(e, dict)],
            educations=[e for e in educations if isinstance(e, dict)],
            additional_info=additional_info,
        )
        resumes.append(resume)

    logger.info("Loaded %d resumes", len(resumes))
    return resumes
