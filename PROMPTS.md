# PROMPTS — Prompt Templates for the Human Operator

> Doc version: 1.0.0 | Status: ACTIVE (non-normative, human-facing) | Last updated: 2026-10-28
> Copy-paste templates for working with AI coding agents on this repo. Agents do not need to read this file.
> These templates are intentionally STRICTER than `AGENTS.md` (for example, the agent proposes `DONE`, you confirm). They never relax any rule in `AGENTS.md` §2.
> Text in `<angle brackets>` is for you to fill in. You may chat in Indonesian; the agent should keep code, docs, and identifiers in English (D-013).

---

## 0. The loop (one task per session)

```
P1 Plan  ->  you read  ->  P2 Approve/Correct  ->  P3 Implement  ->  P4 Report
   ->  you run `make check` yourself  ->  P5 Independent review (NEW session)
   ->  fix findings (P3 again, small)  ->  you confirm DONE + commit
```

Rules of thumb:
- One task per session. Start a fresh session for each new task and for every review.
- Never reply "yes" without reading the plan. If you do not understand part of it, ask (P6).
- The agent that wrote the code must not be the only reviewer.
- Run `make check` on your own machine; do not rely on the agent's claim.
- Commit after each confirmed task: `<type>(<scope>): <summary> [T-x.y]`.

---

## P0. One-time kickoff (first session ever)

```
Read AGENTS.md, then every file in docs/ in the order given in AGENTS.md §3.
Do NOT write code or create files.

Reply with:
1. A 10-line summary of the project in your own words.
2. The absolute rules (R-01..R-13) restated briefly.
3. Any contradictions or ambiguities you found between documents
   (cite document + section IDs).
4. The list of open decisions/questions (D-* with status PROPOSED/OPEN,
   OQ-1..OQ-7) that block upcoming tasks.
5. Which task you would start with and why.
Reply in Indonesian; keep identifiers and quotes from docs in English.
```

Use the answer to find unclear parts of the docs. Fix docs first (with a `DECISIONS.md` entry if meaning changes), then start tasks.

---

## P1. Session start: plan only (no code)

```
Read AGENTS.md, then docs/TASKS.md.
Task for this session: <T-x.y>   (or: "the first TODO task whose dependencies are DONE").

Do NOT write code yet. Produce a plan containing:
1. Task ID, goal, and the "Done when" criteria copied from TASKS.md.
2. Spec sections you will follow (FR-*, DV-*, F-*, INV-*, TC-*, LK-* IDs).
3. Files to create or change (paths), and files you will NOT touch.
4. Tests you will add (IDs) and how they prove the criteria.
5. Assumptions you are making. For each: is it stated in the docs? If not, mark it
   ASSUMPTION and say whether it needs my decision (see AGENTS.md §9 STOP rules).
6. Risks: anything touching AGENTS.md §2 rules, look-ahead, secrets, or scope.
7. New dependencies required (if any) -> must be a DECISIONS entry first (R-13).
Then wait for my approval.
Reply in Indonesian; keep identifiers in English.
```

Plan checklist for you (60 seconds):
- Does the plan stay inside the task? (no extra features)
- Are tests listed before implementation?
- Any "I will assume..." that is not in the docs? Decide it or reject it.
- Any new dependency or schema/config change? Require a DECISIONS entry.

---

## P2. Approve or correct

Approve (only after reading):
```
Plan approved. Proceed with implementation exactly as planned.
```

Approve with changes:
```
Approved with changes:
1. <change>
2. <change>
Update the plan mentally; do not expand scope. Proceed.
```

Reject:
```
Not approved. Problem: <what is wrong>. Revise the plan and resubmit; no code yet.
```

---

## P3. Implement

```
Implement task <T-x.y> per the approved plan.
Rules:
- Tests first or alongside; tests encode the "Done when" criteria.
- Minimal change. No unrelated refactors or extra features.
- Do not weaken, skip, or delete any test to get green (R-12).
- Do not invent API fields, model IDs, fees, thresholds, or library behavior (R-07).
  If you need one, STOP using the format in AGENTS.md §9.
- Run `make check` and fix until green.
- Update affected docs and docs/CHANGELOG.md.
- Do NOT set the task to DONE. Propose it in your report; I will confirm.
```

---

## P4. Completion report (agent must produce this)

```
Report for <T-x.y>. Include:
1. Summary of the diff (files, what changed, why).
2. Exact output summary of `make check` (counts of passed/failed/skipped).
3. Definition of Done checklist from AGENTS.md §10, each item marked
   [x] or [ ] with evidence (test names, file paths).
4. Rules check: confirm for each of R-01..R-13 that it is not violated,
   or state the concern.
5. Assumptions made, STOPs raised, and anything left undone.
6. Docs updated (list) and CHANGELOG entry text.
Be honest: if something is unverified, say so. Do not claim "all tests pass" without output.
```

Then, on your machine:
```bash
git status && git diff --stat
make check
```

---

## P5. Independent review (NEW session, different from the author)

```
You are a reviewer, not an implementer. Do NOT modify files.
Read AGENTS.md, then the task <T-x.y> in docs/TASKS.md and its referenced specs.
Review the current diff (git diff <base>..HEAD or the working tree).

Check and report findings with file:line references, grouped by severity
(BLOCKER / MAJOR / MINOR):
1. Violations of AGENTS.md §2 (R-01..R-13), especially: secrets, real-order code,
   LLM in historical backtest path, LLM-computed numbers, silent data pass, holdout access.
2. Look-ahead: any use of future information; are INV-01/INV-02 tests meaningful
   (not trivially true)? Is there a canary that proves the guard can fail?
3. Tests: weakened, skipped, trivially passing, missing failure cases, missing seeds.
4. Spec mismatch: behavior or schema differing from DATA_SPEC / AI_SPEC / ARCHITECTURE.
5. Invented facts: API endpoints/fields, model IDs, fees, thresholds, formulas.
6. Scope creep: changes outside the task.
7. Determinism and error handling: swallowed exceptions, nondeterminism, naive datetimes.
8. Docs/CHANGELOG not updated.
End with: PASS / PASS WITH FIXES / FAIL and a prioritized fix list.
Reply in Indonesian; keep identifiers in English.
```

Then give the fix list to a new P3-style session ("Fix only these findings: ..."), re-run `make check`, and optionally re-review.

---

## P6. Ask for explanation (when you do not understand)

```
Explain, in simple Indonesian, what <function/module/decision> does and why it is
designed that way. Cite the spec IDs it implements. Then list how I can verify it
myself (which test to run, which output to look at). Do not change any code.
```

---

## P7. Handling a STOP from the agent

The agent should send: `STOP: <what is unclear> | Options: <A/B> | Recommendation: <X> | Blocks: <task id>`.

Your reply:
```
Decision for the STOP on <task id>: <choice and reason>.
Record it in docs/DECISIONS.md (new entry D-0XX, status ACCEPTED), update any doc
that depends on it, add a CHANGELOG line, then continue the task.
```

If you do not know the answer: ask for the trade-offs (P6) and decide later; mark the task `BLOCKED`.

---

## P8. [HUMAN] tasks (decisions and manual runs)

Owner decisions (OQ-*):
```
I am answering <OQ-n>: <answer + source/doc link if applicable>.
Update PRD.md §12, DECISIONS.md (<D-0XX> status), config/default.yaml if relevant,
and unblock the dependent tasks in TASKS.md. Do not implement anything yet.
```

Holdout boundary (T-5.2, do this BEFORE any strategy work):
```
Set the holdout boundary to <date or fraction> in config. Record it in DECISIONS.md
as a new ACCEPTED entry and register it in the experiment registry. Confirm that
holdout rows are unreachable through the default DataView. No strategy code yet.
```

Smoke tests (network / LLM):
```
Run the opt-in smoke test for <T-2.11 | T-4.11>. Show the full log summary,
every validation WARN/FAIL, and any rejected AI output with its validator step.
Do not bypass or relax any validator to make it pass. Explain each anomaly.
```

---

## P9. Bug or failing test (debugging)

```
Bug: <symptom>. Evidence: <error output / failing test>.
Process (do not skip steps):
1. Reproduce with a minimal failing test first (add it, show it fails).
2. State the root cause with evidence (not a guess).
3. Fix the cause, not the symptom. No test weakening (R-12).
4. Show the new test now passes and `make check` is green.
5. Say whether the bug could exist elsewhere (same pattern) and check.
6. Add a CHANGELOG "Fixed" entry.
```

---

## P10. Requesting a spec or scope change

```
I want to change: <what>. Reason: <why>.
Do NOT implement. First produce an impact analysis:
1. Documents and sections affected (IDs).
2. Tests and tasks affected; any previous results invalidated.
3. Conflicts with AGENTS.md §2 rules or PRD non-goals.
4. Proposed DECISIONS.md entry text (context, decision, alternatives, consequences).
Wait for my approval before editing any file.
```

Anything touching R-01 (real orders) or PRD §8.3 is NOT a normal change: it requires a PRD major version and is out of scope for v1.

---

## P11. Resume after context loss or a new tool

```
Read AGENTS.md, docs/TASKS.md, and docs/CHANGELOG.md.
Check `git log --oneline -20` and `git status`.
Tell me: which tasks are DONE, which is IN_PROGRESS, and whether the working tree
has uncommitted changes. Do NOT continue any work until I confirm.
```

---

## P12. Documentation sync audit (run at every gate and before release)

```
Do not change code. Audit consistency:
1. Run `make docs-check` (if available) and report results.
2. List any behavior in code not described in docs, and any spec not implemented.
3. List config keys present in code but missing from DATA_SPEC §10 (and vice versa).
4. List decisions still PROPOSED/OPEN that code already depends on.
5. List claims in reports/docs that violate TEST_PLAN §11 language rules.
Output a table: item | location | severity | suggested fix.
```

---

## P13. Gate verification (end of each phase)

```
Verify gate <G1..G7> from docs/TEST_PLAN.md §10.
For each criterion: PASS/FAIL with evidence (command run + output summary, test IDs).
Do not mark anything PASS from memory. Run the commands. If a criterion needs a manual
action by me, list it explicitly instead of assuming it passed.
```

---

## Anti-patterns (avoid)

| Do not say | Why | Say instead |
|------------|-----|-------------|
| "yes" / "continue" without reading | you approve unseen assumptions | P2 after reading, or P6 |
| "analyze the code" only | vague; agent may skim or praise itself | P5 with the checklist |
| "make the strategy profitable" | invites overfitting, violates R-08 | register `H-XXX.md` yourself; test with the protocol |
| "just make the tests pass" | invites test weakening | P9: root cause first |
| "do the next 5 tasks" | big unreviewable diffs, drifting scope | one task per session |
| "use whatever model/API works" | invents IDs/fields (R-07) | provide verified doc links, or let it STOP |
| "skip validation for now" | breaks R-06 and INV-04 | fix the data or adjust the spec via P10 |
| "let the LLM decide trades" | violates D-002 / R-04 | keep LLM at interpretation only |
| pasting your API key into chat | leaks a secret (R-02) | put it in `.env` locally |

## Per-task checklist for you

- [ ] P1 plan read and approved (or corrected)
- [ ] P4 report received with evidence
- [ ] `make check` run by me, green
- [ ] P5 review in a fresh session: PASS or fixes applied
- [ ] Docs and CHANGELOG updated
- [ ] I confirmed `DONE`, task status updated, commit made
