"""Load the DRAFT starter goal bank (taxonomy + goals) from app/data/goal_bank_seed.json.

    python -m app.scripts.seed_goal_bank
    python -m app.scripts.seed_goal_bank --allow-production   # only after Coordinator review

Idempotent: domains and skills are upserted by code (names/descriptions are
only filled in when created, so Coordinator renames are kept); goals are only
created when their code does not exist yet - existing goals are never changed.
All new goals are loaded as 'draft' for the SNED Coordinator to review.
"""

import argparse
import json
import sys
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.goal import Goal, GoalDomain, GoalSkill
from app.services import goal_service

SEED_FILE = Path(__file__).resolve().parent.parent / "data" / "goal_bank_seed.json"


def load_seed(path: Path = SEED_FILE) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def seed(db: Session, data: dict | None = None) -> dict[str, int]:
    data = data or load_seed()
    counts = {"domains": 0, "skills": 0, "goals": 0, "goals_skipped": 0}
    domains: dict[str, GoalDomain] = {}
    skills: dict[tuple[str, str], GoalSkill] = {}

    for d_order, d in enumerate(data["domains"], 1):
        domain = db.scalar(select(GoalDomain).where(GoalDomain.code == d["code"]))
        if domain is None:
            domain = GoalDomain(
                code=d["code"],
                name=d["name"],
                description=d.get("description"),
                sort_order=d.get("sort_order", d_order),
            )
            db.add(domain)
            db.flush()
            counts["domains"] += 1
        domains[d["code"]] = domain
        for s_order, s in enumerate(d.get("skills", []), 1):
            skill = db.scalar(
                select(GoalSkill).where(GoalSkill.domain_id == domain.id, GoalSkill.code == s["code"])
            )
            if skill is None:
                skill = GoalSkill(
                    domain_id=domain.id,
                    code=s["code"],
                    name=s["name"],
                    description=s.get("description"),
                    sort_order=s.get("sort_order", s_order),
                )
                db.add(skill)
                db.flush()
                counts["skills"] += 1
            skills[(d["code"], s["code"])] = skill
    db.commit()

    existing = set(db.scalars(select(Goal.code)).all())
    for g in data["goals"]:
        if g["code"] in existing:
            counts["goals_skipped"] += 1
            continue
        fields = {
            "domain_id": domains[g["domain"]].id,
            "skill_id": skills[(g["domain"], g["skill"])].id,
            "statement": g["statement"],
            "measurement_method": g["measurement_method"],
            "target_value": g["target_value"],
            "target_unit": g["target_unit"],
            "criterion": g.get("criterion"),
            "grade_band": g.get("grade_band", "any"),
            "change_note": "Starter set (draft, pending Coordinator review)",
        }
        goal_service.create_goal(db, None, fields, code=g["code"])
        counts["goals"] += 1
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--allow-production", action="store_true")
    args = parser.parse_args()
    if get_settings().environment == "production" and not args.allow_production:
        sys.exit("Refusing to load the draft starter goal bank in production without --allow-production.")

    from app.db.session import SessionLocal

    with SessionLocal() as db:
        counts = seed(db)
    print(
        f"Added {counts['domains']} domains, {counts['skills']} skills, {counts['goals']} draft goals "
        f"({counts['goals_skipped']} goals already existed and were left unchanged)."
    )


if __name__ == "__main__":
    main()
