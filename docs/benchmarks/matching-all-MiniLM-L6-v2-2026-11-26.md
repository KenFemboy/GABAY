# Goal matching benchmark — `sentence-transformers/all-MiniLM-L6-v2`

Date: 2026-11-26 · Items: 68 (synthetic, see app/data/matching_benchmark.json) · Goal bank: starter set (50 goals, all activated) · Grade-band filter: on

| Setting | Top-1 | Top-3 | **Top-5** | MRR | Candidates per need (median) | Random-ranking top-5 |
|---|---|---|---|---|---|---|
| Domain filter on (default) | 77.9% | 91.2% | **95.6%** | 0.848 | 6 | 82.3% |
| Domain filter off | 75.0% | 91.2% | **95.6%** | 0.828 | 44 | 15.0% |

The random-ranking column is what top-5 accuracy would be if the filtered candidates were put in a random order. The gap between it and the model's top-5 shows what the embeddings add. With the domain filter on, each need only competes with a few goals, so top-1 and MRR are the more telling numbers there.

## Top-5 accuracy by language (domain filter on)

| Language | Items | Top-5 |
|---|---|---|
| en | 50 | 98.0% |
| fil | 10 | 80.0% |
| ocr | 8 | 100.0% |

## Top-5 accuracy by domain (domain filter on)

| Domain | Items | Top-5 |
|---|---|---|
| behavior_social | 14 | 92.9% |
| cognitive | 4 | 100.0% |
| communication | 7 | 100.0% |
| mathematics | 11 | 100.0% |
| motor | 7 | 100.0% |
| reading | 16 | 87.5% |
| self_help | 4 | 100.0% |
| writing | 5 | 100.0% |

## Scores (domain filter on)

- Score of the correct goal when found: median 0.688, min 0.291
- Score of a wrong top-1 goal: median 0.515, max 0.668

Share of correct matches that a minimum score would keep:

| MATCH_MIN_SCORE | Correct matches kept |
|---|---|
| 0.25 | 65/65 (100.0%) |
| 0.30 | 64/65 (98.5%) |
| 0.35 | 62/65 (95.4%) |
| 0.40 | 61/65 (93.8%) |
| 0.45 | 60/65 (92.3%) |
| 0.50 | 58/65 (89.2%) |

## Misses (domain filter on, not in top-5)

- en-02: "Has difficulty blending sounds together to form words." -> got ['RD-005', 'RD-006', 'RD-001'], expected ['RD-002']
- fil-01: "Nahihirapan siyang bumasa ng mga simpleng salita." -> got ['RD-010', 'RD-009', 'RD-011'], expected ['RD-002', 'RD-004']
- fil-05: "Madaling mainip at hindi natatapos ang gawain sa upuan." -> got ['BS-003', 'BS-008', 'BS-006'], expected ['BS-001', 'BS-002']
