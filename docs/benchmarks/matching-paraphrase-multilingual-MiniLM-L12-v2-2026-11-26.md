# Goal matching benchmark — `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`

Date: 2026-11-26 · Items: 68 (synthetic, see app/data/matching_benchmark.json) · Goal bank: starter set (50 goals, all activated) · Grade-band filter: on

| Setting | Top-1 | Top-3 | **Top-5** | MRR | Candidates per need (median) | Random-ranking top-5 |
|---|---|---|---|---|---|---|
| Domain filter on (default) | 79.4% | 91.2% | **97.1%** | 0.858 | 6 | 82.3% |
| Domain filter off | 76.5% | 88.2% | **97.1%** | 0.836 | 44 | 15.0% |

The random-ranking column is what top-5 accuracy would be if the filtered candidates were put in a random order. The gap between it and the model's top-5 shows what the embeddings add. With the domain filter on, each need only competes with a few goals, so top-1 and MRR are the more telling numbers there.

## Top-5 accuracy by language (domain filter on)

| Language | Items | Top-5 |
|---|---|---|
| en | 50 | 100.0% |
| fil | 10 | 80.0% |
| ocr | 8 | 100.0% |

## Top-5 accuracy by domain (domain filter on)

| Domain | Items | Top-5 |
|---|---|---|
| behavior_social | 14 | 92.9% |
| cognitive | 4 | 100.0% |
| communication | 7 | 100.0% |
| mathematics | 11 | 90.9% |
| motor | 7 | 100.0% |
| reading | 16 | 100.0% |
| self_help | 4 | 100.0% |
| writing | 5 | 100.0% |

## Scores (domain filter on)

- Score of the correct goal when found: median 0.677, min 0.411
- Score of a wrong top-1 goal: median 0.646, max 0.719

Share of correct matches that a minimum score would keep:

| MATCH_MIN_SCORE | Correct matches kept |
|---|---|
| 0.25 | 66/66 (100.0%) |
| 0.30 | 66/66 (100.0%) |
| 0.35 | 66/66 (100.0%) |
| 0.40 | 66/66 (100.0%) |
| 0.45 | 63/66 (95.5%) |
| 0.50 | 63/66 (95.5%) |

## Misses (domain filter on, not in top-5)

- fil-03: "Hindi pa niya kayang magbawas ng mga numero." -> got ['MA-002', 'MA-007', 'MA-006'], expected ['MA-004']
- fil-05: "Madaling mainip at hindi natatapos ang gawain sa upuan." -> got ['BS-008', 'BS-009', 'BS-006'], expected ['BS-001', 'BS-002']
