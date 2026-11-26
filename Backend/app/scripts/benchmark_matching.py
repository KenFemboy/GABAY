"""Measure goal-matching quality on the synthetic benchmark set.

    python -m app.scripts.benchmark_matching
    python -m app.scripts.benchmark_matching --model sentence-transformers/all-MiniLM-L6-v2
    python -m app.scripts.benchmark_matching --out ../docs/benchmarks

The starter goal bank is loaded into a temporary in-memory database (the real
database is never touched), every goal is activated and indexed with the chosen
model, and each benchmark need is matched with the same ``vector_search`` used in
production. Reports top-1/3/5 accuracy and MRR, with and without the domain
filter, by language and by domain, plus score statistics for choosing
MATCH_MIN_SCORE.
"""

import argparse
import json
import os
import statistics
from math import comb
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

os.environ.setdefault("ENVIRONMENT", "test")

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

import app.models  # noqa: E402,F401
from app.core.config import get_settings  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.models.goal import Goal, GoalDomain, GoalVersion  # noqa: E402
from app.scripts.seed_goal_bank import seed  # noqa: E402
from app.services import embedding_service  # noqa: E402
from app.services.embedding_service import Embedder, check_dims, vector_search  # noqa: E402

BENCHMARK_FILE = Path(__file__).resolve().parent.parent / "data" / "matching_benchmark.json"
THRESHOLDS = (0.25, 0.30, 0.35, 0.40, 0.45, 0.50)


def load_items(path: Path = BENCHMARK_FILE) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))["items"]


@dataclass
class Result:
    label: str
    n: int = 0
    hits: dict[int, int] = field(default_factory=lambda: {1: 0, 3: 0, 5: 0})
    rr_sum: float = 0.0
    random_top5_sum: float = 0.0  # expected top-5 hits if the candidates were ranked at random
    candidates: list[int] = field(default_factory=list)
    by_lang: dict[str, list[int]] = field(default_factory=dict)  # lang -> [n, top5 hits]
    by_domain: dict[str, list[int]] = field(default_factory=dict)
    correct_scores: list[float] = field(default_factory=list)  # score of the best correct goal in top-5
    wrong_top1_scores: list[float] = field(default_factory=list)
    misses: list[str] = field(default_factory=list)

    def acc(self, k: int) -> float:
        return self.hits[k] / self.n if self.n else 0.0

    @property
    def random_top5(self) -> float:
        return self.random_top5_sum / self.n if self.n else 0.0

    @property
    def mrr(self) -> float:
        return self.rr_sum / self.n if self.n else 0.0


def build_bank(embedder: Embedder) -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, autoflush=False)()
    seed(db)
    for goal in db.query(Goal):
        goal.status = "active"
    db.commit()
    embedding_service.reindex(db, embedder)
    return db


def _candidates(db: Session, domain: str | None, band: str | None) -> list[str]:
    codes = []
    for goal in db.query(Goal).filter(Goal.status == "active"):
        v: GoalVersion = goal.current_version
        if domain and v.domain.code != domain:
            continue
        if band and v.grade_band not in (band, "any"):
            continue
        codes.append(goal.code)
    return codes


def _random_top5(n_candidates: int, n_correct: int) -> float:
    """Chance that a random ordering puts at least one correct goal in the top 5."""
    if n_correct == 0:
        return 0.0
    k = min(5, n_candidates)
    return 1 - comb(n_candidates - n_correct, k) / comb(n_candidates, k)


def evaluate(db: Session, embedder: Embedder, items: list[dict], *, same_domain: bool, label: str) -> Result:
    names = {d.code: d.name for d in db.query(GoalDomain)}
    texts = [f"{names[i['domain']]} – {i['text']}" if i.get("domain") in names else i["text"] for i in items]
    vectors = check_dims(embedder.embed(texts))
    result = Result(label=label)
    for item, vector in zip(items, vectors, strict=True):
        hits = vector_search(
            db,
            vector,
            model=embedder.model,
            k=5,
            domain_code=item["domain"] if same_domain else None,
            grade_band=item.get("grade_band"),
        )
        codes = [h.goal.code for h in hits]
        expected = set(item["expected"])
        pool = _candidates(db, item["domain"] if same_domain else None, item.get("grade_band"))
        result.candidates.append(len(pool))
        result.random_top5_sum += _random_top5(len(pool), len(expected & set(pool)))
        rank = next((i + 1 for i, c in enumerate(codes) if c in expected), None)
        result.n += 1
        lang = result.by_lang.setdefault(item["lang"], [0, 0])
        dom = result.by_domain.setdefault(item["domain"], [0, 0])
        lang[0] += 1
        dom[0] += 1
        if rank is not None:
            for k in (1, 3, 5):
                if rank <= k:
                    result.hits[k] += 1
            result.rr_sum += 1 / rank
            lang[1] += 1
            dom[1] += 1
            result.correct_scores.append(hits[rank - 1].score)
        else:
            result.misses.append(f"{item['id']}: \"{item['text']}\" -> got {codes[:3]}, expected {sorted(expected)}")
        if hits and codes[0] not in expected:
            result.wrong_top1_scores.append(hits[0].score)
    return result


def _pct(x: float) -> str:
    return f"{100 * x:.1f}%"


def report(model: str, results: list[Result]) -> str:
    lines = [
        f"# Goal matching benchmark — `{model}`",
        "",
        f"Date: {date.today().isoformat()} · Items: {results[0].n} (synthetic, see app/data/matching_benchmark.json) · "
        "Goal bank: starter set (50 goals, all activated) · Grade-band filter: on",
        "",
        "| Setting | Top-1 | Top-3 | **Top-5** | MRR | Candidates per need (median) | Random-ranking top-5 |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in results:
        lines.append(
            f"| {r.label} | {_pct(r.acc(1))} | {_pct(r.acc(3))} | **{_pct(r.acc(5))}** | {r.mrr:.3f} | "
            f"{statistics.median(r.candidates):.0f} | {_pct(r.random_top5)} |"
        )
    lines += [
        "",
        "The random-ranking column is what top-5 accuracy would be if the filtered candidates were put in a "
        "random order. The gap between it and the model's top-5 shows what the embeddings add. With the domain "
        "filter on, each need only competes with a few goals, so top-1 and MRR are the more telling numbers there.",
    ]
    main = results[0]
    lines += ["", "## Top-5 accuracy by language (domain filter on)", "", "| Language | Items | Top-5 |", "|---|---|---|"]
    for lang, (n, hit) in sorted(main.by_lang.items()):
        lines.append(f"| {lang} | {n} | {_pct(hit / n)} |")
    lines += ["", "## Top-5 accuracy by domain (domain filter on)", "", "| Domain | Items | Top-5 |", "|---|---|---|"]
    for dom, (n, hit) in sorted(main.by_domain.items()):
        lines.append(f"| {dom} | {n} | {_pct(hit / n)} |")
    lines += ["", "## Scores (domain filter on)", ""]
    if main.correct_scores:
        lines.append(
            f"- Score of the correct goal when found: median {statistics.median(main.correct_scores):.3f}, "
            f"min {min(main.correct_scores):.3f}"
        )
    if main.wrong_top1_scores:
        lines.append(
            f"- Score of a wrong top-1 goal: median {statistics.median(main.wrong_top1_scores):.3f}, "
            f"max {max(main.wrong_top1_scores):.3f}"
        )
    lines += ["", "Share of correct matches that a minimum score would keep:", "", "| MATCH_MIN_SCORE | Correct matches kept |", "|---|---|"]
    for t in THRESHOLDS:
        kept = sum(1 for s in main.correct_scores if s >= t)
        lines.append(f"| {t:.2f} | {kept}/{len(main.correct_scores)} ({_pct(kept / max(1, len(main.correct_scores)))}) |")
    lines += ["", "## Misses (domain filter on, not in top-5)", ""]
    lines += [f"- {m}" for m in main.misses] or ["- none"]
    return "\n".join(lines) + "\n"


def run(model: str, cache_dir: str, items: list[dict] | None = None, embedder: Embedder | None = None) -> tuple[str, list[Result]]:
    embedder = embedder or embedding_service.FastEmbedEmbedder(model, cache_dir)
    items = items or load_items()
    db = build_bank(embedder)
    try:
        results = [
            evaluate(db, embedder, items, same_domain=True, label="Domain filter on (default)"),
            evaluate(db, embedder, items, same_domain=False, label="Domain filter off"),
        ]
    finally:
        db.close()
    return report(embedder.model, results), results


def main() -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Goal matching benchmark")
    parser.add_argument("--model", default=settings.embedding_model)
    parser.add_argument("--out", help="folder to write the markdown report into")
    args = parser.parse_args()
    text, results = run(args.model, settings.embedding_cache_dir)
    print(text)
    if args.out:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        path = out / f"matching-{args.model.split('/')[-1]}-{date.today().isoformat()}.md"
        path.write_text(text, encoding="utf-8")
        print(f"Written to {path}")


if __name__ == "__main__":
    main()
