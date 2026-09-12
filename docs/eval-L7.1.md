# L7.1 — Manual Evaluation: 10 Fixture Questions

This document covers the **manual half** of L7.1. The automated half
(compiler + executor pipeline) is covered by `backend/tests/test_eval_fixtures.py`
— all 10 pass against `tests/fixtures/sales.csv`.

The manual pass verifies the **LLM planning step** works correctly end-to-end
through the real UI: question → Groq planner → IR → SQL → result.

---

## Setup

1. Start the backend: `uvicorn app.main:app --reload` (from `backend/`)
2. Start the frontend: `npm run dev` (from `frontend/`)
3. Sign in at `http://localhost:3000/login`
4. Go to **Settings** → enter your Groq API key → **Save key**
5. Go to **Dashboard** → open or create a workspace
6. Upload `backend/tests/fixtures/sales.csv` (12 rows, 4 columns)
7. Wait for status **READY**, click the file to select it

---

## Fixture Dataset Schema

| Column | Type | Notes |
|---|---|---|
| `region` | text | North / South / East / West |
| `product` | text | Widget A / Widget B / Widget C |
| `quantity` | integer | Units sold |
| `price` | decimal | Per-unit price |

**12 rows total.** Full dataset:

| region | product | quantity | price |
|---|---|---|---|
| North | Widget A | 15 | 9.99 |
| North | Widget B | 8 | 14.99 |
| North | Widget A | 12 | 9.99 |
| South | Widget C | 20 | 4.99 |
| South | Widget A | 5 | 9.99 |
| South | Widget B | 18 | 14.99 |
| East | Widget C | 30 | 4.99 |
| East | Widget A | 7 | 9.99 |
| West | Widget B | 22 | 14.99 |
| West | Widget C | 11 | 4.99 |
| North | Widget C | 3 | 4.99 |
| East | Widget B | 14 | 14.99 |

---

## Evaluation Checklist

For each question: type it exactly into the chat box, submit, and mark the result.

| # | Question to type | Expected result | Pass? |
|---|---|---|---|
| Q1 | `What is the total quantity?` | **165** | ☐ |
| Q2 | `What is the average price?` | **9.99** | ☐ |
| Q3 | `Total quantity by region` | North 38, South 43, East 51, West 33 (order may vary) | ☐ |
| Q4 | `Show rows where region is North` | **4 rows**, all with region = North | ☐ |
| Q5 | `Top 3 products by total quantity` | Widget C (64), Widget B (62), Widget A (39) | ☐ |
| Q6 | `How many unique products?` | **3** | ☐ |
| Q7 | `What is the minimum and maximum price?` | min **4.99**, max **14.99** | ☐ |
| Q8 | `Show me the first 5 rows` | 5 rows returned, all 4 columns visible | ☐ |
| Q9 | `Which products have quantity greater than 10?` | **8 rows**, all with quantity > 10 | ☐ |
| Q10 | `Count rows by product sorted alphabetically` | Widget A: 4, Widget B: 4, Widget C: 4 | ☐ |

---

## Grading

- **10/10** — MVP complete. Proceed to L7.2 (adversarial check).
- **8–9/10** — Acceptable. Note which questions failed and fix in L7.3.
- **< 8/10** — Planner needs prompt tuning. Flag specific failures for L7.3.

### Common failure modes to watch for

| Symptom | Likely cause | Fix |
|---|---|---|
| Wrong column name in SQL | Planner hallucinated column | Prompt: emphasise column matching |
| Missing GROUP BY | Planner omitted `group_by` | Prompt: add example for grouped queries |
| `Auto-repaired` badge shown | Planner made a fixable error | L6.1 caught it — still counts as pass |
| Confidence < 50% fallback | Question too ambiguous | Rephrase slightly to re-test |
| 0 results | Filter value casing mismatch | Check DuckDB case-sensitivity |

---

## Notes column

Use this space while testing:

| # | Notes |
|---|---|
| Q1 | |
| Q2 | |
| Q3 | |
| Q4 | |
| Q5 | |
| Q6 | |
| Q7 | |
| Q8 | |
| Q9 | |
| Q10 | |

---

*After completing this checklist, proceed to **L7.2** (adversarial check) or
**L7.3** (fix and commit) depending on results.*
