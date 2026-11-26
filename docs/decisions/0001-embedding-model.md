# 0001 — Embedding model for goal matching

- **Status:** Accepted (2026-11-26)
- **Decision:** Use `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (run locally through fastembed/ONNX) to embed goal-bank goals and learner needs.
- **Recorded in code:** `EMBEDDING_MODEL` (config). Every matching run and recommendation stores `model_version` = `"<model>|text-v1"`.

## Context

GABAY suggests IEP goals by comparing a learner's approved **needs** (sentences extracted from assessment reports) with the goals in the goal bank. The comparison has to:

- understand paraphrases ("struggles to take away numbers" ≈ "subtraction"),
- handle English, Filipino and mixed text,
- run on the school's own server, without sending learner text to an outside service,
- run on a CPU in well under a second per learner.

## Candidates

| Model | Languages | Dimensions | Size | Notes |
|---|---|---|---|---|
| **paraphrase-multilingual-MiniLM-L12-v2** | 50+ including Filipino/Tagalog | 384 | ~240 MB | Trained for paraphrase similarity |
| all-MiniLM-L6-v2 | English only | 384 | ~90 MB | Common English baseline |
| paraphrase-multilingual-mpnet-base-v2 | 50+ | 768 | ~1 GB | Larger; not tested (would need vector(768)) |
| Hosted APIs (e.g. Voyage AI) | many | varies | — | Rejected: sends text off the server and adds a paid dependency |

Both tested models are Apache-2.0 licensed.

## Benchmark results

The benchmark has 68 synthetic needs: 50 English, 10 Filipino and 8 with OCR-style errors. They're matched against the 50-goal starter set with all goals active and the grade-band filter on. See `app/data/matching_benchmark.json` and `python -m app.scripts.benchmark_matching`. Full reports are in `docs/benchmarks/`.

| Model | Domain filter | Top-1 | Top-3 | **Top-5** | MRR | Filipino top-5 |
|---|---|---|---|---|---|---|
| **paraphrase-multilingual-MiniLM-L12-v2** | on | 79.4% | 91.2% | **97.1%** | 0.858 | 80% |
| **paraphrase-multilingual-MiniLM-L12-v2** | off | 76.5% | 88.2% | **97.1%** | 0.836 | — |
| all-MiniLM-L6-v2 | on | 77.9% | 91.2% | **95.6%** | 0.848 | 80% |
| all-MiniLM-L6-v2 | off | 75.0% | 91.2% | **95.6%** | 0.828 | — |

How to read these numbers:

- **Domain filter on:** a need only competes with goals in its own domain and grade band, a median of 6 candidates. Random ordering would already put a correct goal in the top 5 for 82% of needs, so top-1 and MRR say more here than top-5.
- **Domain filter off:** each need competes with a median of 44 goals. Random ordering would reach 15% top-5, and the chosen model reaches 97%.

## Why this model

- It scored best on every metric, by a small margin over the English-only baseline.
- It is multilingual by design. Both models score 80% top-5 on the 10 Filipino needs, but with the domain filter only a few candidates remain, so that tie says little. A multilingual model is the safer choice for Filipino text that has no English words in it.
- It is small enough to run on a CPU, its 384 dimensions keep pgvector storage and the HNSW index small, and it needs no API key.

## Known weaknesses

- Filipino-only phrasing is the weakest area. Both misses in the top 5 were Filipino ("magbawas" for subtract, "mainip" for restless).
- The benchmark is synthetic and was written by the developer. It must be reviewed and extended with real, anonymised needs approved by the SNED Coordinator.
- `MATCH_MIN_SCORE=0.35` keeps 100% of the correct matches in the benchmark. The lowest score of a correct goal was 0.41. The threshold should be re-checked on real data.

## When to revisit

- When real (anonymised) needs are available, rerun the benchmark. If top-5 accuracy falls below about 85%, or Filipino stays clearly behind English, try a larger multilingual model, or write the goals in both languages.
- If the model changes, update `EMBEDDING_MODEL`, reindex the goal bank (old vectors are removed automatically), and bump `TEXT_VERSION` in `matching_service.py` if the text format changes. A model with a different dimension also needs a migration of the `vector(384)` columns.
