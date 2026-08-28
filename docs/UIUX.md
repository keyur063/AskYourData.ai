# UI/UX Design Document
## AskYourData.ai

**Version:** 1.0

---

## 1. Design Principles

1. **Transparency over magic.** Every answer is one click away from the query/SQL that produced it. Users should never feel like they're trusting a black box.
2. **Clarify, don't guess.** When the system is unsure, it asks — through structured, tappable options, not open-ended re-prompting.
3. **Data first, chat second.** The chat interface is the entry point, but schema, tables, and results are always visible/reachable, not buried behind conversation.
4. **Progressive disclosure.** Non-technical users see plain language and charts by default; SQL/IR/technical detail is available on demand, not forced.
5. **Safe by default, visible when restricted.** If data is masked (PII) or a role can't do something, say so plainly rather than failing silently.

---

## 2. Primary User Flows

### 2.1 First-Time Upload → First Query
```text
Landing / Empty workspace
   → "Upload a file" (drag-and-drop or browse)
   → Upload progress (UPLOADING → PROCESSING)
   → Dataset preview (first rows, inferred schema, detected sheets as tabs)
   → Prompt: "Ask a question about this data"
   → Chat interface with suggested starter questions
   → Answer + table + chart + "View generated query" link
```

### 2.2 Ask → Clarify → Answer
```text
User types question
   → System shows a lightweight "thinking" state (never a blank spinner with no context)
   → If ambiguous: inline clarification card
        "Did you mean revenue by order count or by dollar amount?"
        [ Dollar amount ]  [ Order count ]
   → User taps an option (no retyping)
   → Answer renders
```

### 2.3 Follow-Up Question
```text
Previous answer stays visible (chat-thread style)
   → User types a refinement: "only for Maharashtra"
   → System shows a small "applying to previous question" indicator
   → Updated answer replaces/extends the thread, previous context still visible above
```

### 2.4 Connecting a Database (Raj / admin persona)
```text
Workspace settings → Data Sources → "Connect a database"
   → Select type (Postgres / MySQL / SQL Server)
   → Enter connection details + read-only credential
   → Test connection (explicit success/failure, never silent)
   → Schema auto-discovered → review/edit table & column descriptions
   → Ready for querying
```

### 2.5 Query Failure / Repair Exhausted
```text
Answer area shows:
   "I wasn't able to run this query."
   → Collapsed: "Show what was attempted" (last SQL + error, plain language)
   → Suggested actions: [ Rephrase question ]  [ Simplify question ]  [ Report issue ]
```

### 2.6 Managing Workspace Members
```text
Workspace settings → Members
   → List of members with role badges (Owner/Editor/Analyst/Viewer)
   → "Invite" → email + role selector
   → Role changes take effect immediately, reflected in what that user can do/see
```

---

## 3. Core Screens

### 3.1 Chat / Query Screen (primary)
* Left rail: dataset/table explorer (collapsible), query history.
* Center: chat thread — question bubbles, answer cards (text + table + chart), clarification cards.
* Each answer card has: plain-language answer, result table (scrollable, sortable), chart (if applicable), "View SQL/IR" expandable section, feedback control (thumbs up/down).
* Persistent input bar with suggested-question chips based on current dataset.

### 3.2 Dataset / Schema Explorer
* Table list with row counts, last-updated, source type (file/DB) badges.
* Column detail panel: type, semantic type, null %, sample values, PII badge if flagged.
* Relationship view: simple diagram of detected foreign-key links between tables.

### 3.3 Data Source Management
* List of connected files and databases with status (READY/PROCESSING/FAILED).
* Connection health indicator for live databases (last successful schema refresh).
* Upload new file / connect new database actions.

### 3.4 Query History
* Chronological list: question, timestamp, user, success/failure, cost (if visible to role).
* Click-through to re-open the full answer card.
* Filter by dataset, user, date range.

### 3.5 Workspace Settings
* Members & roles, entitlement/plan info, usage dashboard (LLM cost, query volume), retention policy configuration, audit log viewer (for permitted roles).

### 3.6 Admin/Analyst: Semantic Layer Editor
* List of defined metrics (name, definition, e.g. `SUM(quantity * unit_price)`), dimensions.
* Simple form-based editor — no code required, though an "advanced" raw-expression mode is available.

---

## 4. Interaction Patterns

* **Clarification cards** use tappable options wherever the ambiguity has enumerable choices (matching column/metric candidates); free-text is only requested when options genuinely can't be enumerated.
* **Progressive technical disclosure:** "View SQL/IR" is always collapsed by default for `analyst`/`viewer` roles, expanded by default for `editor`/`owner` roles who are more likely to want it immediately (configurable).
* **Trust indicators:** every answer is labeled with how it was produced — "Computed directly" (deterministic path) vs. "Generated with AI assistance" (LLM path) — so users calibrate trust appropriately.
* **Error states are never dead ends** — always paired with a concrete next action (rephrase, simplify, view details, contact support).
* **PII masking is visible, not silent** — masked fields show a "restricted" indicator rather than being omitted without explanation, so users understand why a field is missing.

---

## 5. Visual/Content Guidelines

* Plain-language answers lead; tables and charts support, not replace, the sentence-level answer.
* Avoid over-precision in language the model isn't certain of — hedge appropriately ("approximately," "based on available data through [date]") rather than presenting estimates as exact facts.
* Chart type follows the deterministic mapping in the Architecture doc (time series → line, categories → bar, part-to-whole → pie/donut, two numeric vars → scatter, distribution → histogram) so the same question type always produces a visually consistent answer.
* Role-based UI differences are explicit, not just permission errors — a `viewer` sees a clearly different (read-only) interface, not a full interface that silently fails on interaction.

---

## 6. Accessibility & Responsiveness

* WCAG 2.1 AA target: keyboard navigability for the chat interface and clarification cards, sufficient color contrast, screen-reader labels for chart content (with an accessible data-table alternative always available).
* Responsive layout: schema explorer collapses to a drawer on narrow viewports; chat/answer flow remains the primary, full-width experience on mobile.

---

## 7. Empty & Edge States

* **No data yet:** empty workspace shows upload CTA + 2–3 example questions from a sample dataset the user can try instantly.
* **Large file processing:** visible progress state, not a blocking spinner; user can navigate away and get notified when ready.
* **No results:** distinguished clearly between "query ran, zero rows matched" vs. "query failed" — these must never look the same.
* **Rate limit hit:** explicit message with the limit and reset time, plus an upgrade path if applicable — never a silent failure.
