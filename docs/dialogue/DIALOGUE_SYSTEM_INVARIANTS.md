# Dialogue system invariants

1. **Current UPN is authority.** Never mass-repair the stale root `eng.zip`.
2. **Same-name pristine Utage is structural authority.** Use `rom/jpn/id/<same archive>` for FIM ownership/control comparison.
3. **FIM primary col4 owns the secondary span.** For primary row `i`, owned secondaries are `[p4[i], p4[i+1])`.
4. **FFFD terminates a real speech.** `FFFE` is a line break. Styling controls (`FF91`, `FF92`, etc.) do not create another secondary speech.
5. **FIM secondary col0 is the reveal budget.** Preserve every other secondary byte unless independently proven otherwise.
6. **Never under-budget English.** Production corpus repair is monotonic: lines/chars may increase, never decrease.
7. **Preserve non-FFFE control opcodes AND arguments.** Opcode-only comparison is insufficient (`FC17`, `FED2`, `FF91`, `FF92`, `FFFB`, etc. carry arguments).
8. **Preserve FFFD count.** A mismatch is structural drift and blocks automatic repair.
9. **Do not auto-gate FFFE globally.** English legitimately needs extra line breaks; official Samurai Heroes uses them extensively.
10. **Preserve GSM pool padding when rebuilding.** Do not compact away Capcom's declared trailing pool cells.
11. **Do not infer `_r` ownership.** The production repair targets the coherent primary GSM/FIM pair and leaves reverse/auxiliary resources raw-identical.
12. **Fail closed.** Cardinality, primary-FIM, control, or ownership mismatch -> `BLOCKED_*`, not a guessed patch.
13. **Cold boot after deployment.** Runtime validation must not reuse a state with the old dialogue bank resident.
