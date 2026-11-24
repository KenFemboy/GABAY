"""Seed obviously fake learners for local development.

    python -m app.scripts.seed_learners

Never put real learner data in a development database. Existing codes are
skipped, so the script is safe to run more than once. Refuses to run in
production.
"""

import sys
from datetime import date

from app.core.config import get_settings
from app.models.learner import GradeLevel, Sex
from app.schemas.learner import LearnerCreate

SCHOOL_YEAR = "2025-2026"

SAMPLE_LEARNERS = [
    ("DEV-0001", "Juan", "Dela Cruz", Sex.MALE, date(2017, 3, 14), GradeLevel.GRADE_2, "Sampaguita"),
    ("DEV-0002", "Maria", "Santos", Sex.FEMALE, date(2016, 7, 2), GradeLevel.GRADE_3, "Sampaguita"),
    ("DEV-0003", "Jose", "Reyes", Sex.MALE, date(2018, 11, 21), GradeLevel.GRADE_1, "Ilang-Ilang"),
    ("DEV-0004", "Ana", "Garcia", Sex.FEMALE, date(2019, 1, 9), GradeLevel.KINDERGARTEN, "Rosal"),
    ("DEV-0005", "Pedro", "Bautista", Sex.MALE, date(2014, 5, 30), GradeLevel.GRADE_5, "Narra"),
    ("DEV-0006", "Liza", "Mendoza", Sex.FEMALE, date(2012, 9, 17), GradeLevel.GRADE_7, "Molave"),
    ("DEV-0007", "Ramon", "Aquino", Sex.MALE, date(2013, 12, 3), GradeLevel.NON_GRADED, "Transition"),
    ("DEV-0008", "Clara", "Villanueva", Sex.FEMALE, date(2015, 4, 25), GradeLevel.GRADE_4, "Narra"),
]


def main() -> int:
    settings = get_settings()
    if settings.environment == "production":
        print("Refusing to seed sample learners in production.", file=sys.stderr)
        return 1

    from app.db.session import SessionLocal
    from app.services.learner_service import create_learner, get_by_code

    created = skipped = 0
    with SessionLocal() as db:
        for code, first, last, sex, birth_date, grade, section in SAMPLE_LEARNERS:
            if get_by_code(db, code):
                skipped += 1
                continue
            create_learner(
                db,
                LearnerCreate(
                    learner_code=code,
                    first_name=first,
                    last_name=f"{last} (Sample)",
                    sex=sex,
                    birth_date=birth_date,
                    grade_level=grade,
                    section=section,
                    school_year=SCHOOL_YEAR,
                ),
            )
            created += 1
    print(f"Sample learners: {created} created, {skipped} already present.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
