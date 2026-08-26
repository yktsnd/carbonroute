# Contributing

## Ground rules that are not negotiable

These come from the design spec (`docs/spec-ja.md`, section 13) and a change
that breaks one of them will be rejected regardless of how useful it is.

1. **No language model ever produces a numeric factor.** v0 keeps language
   models out of the calculation path entirely.
2. **Missing data is reported, never defaulted.** If a factor cannot be
   resolved, the material stays unresolved and the report says so.
3. **Nothing non-redistributable enters the repository.** ecoinvent-derived
   values in particular must never be committed.
4. **No single absolute number is presented as the conclusion.** The output is
   a ranking with a probability.
5. **No row without a source.** The factor-table loader enforces this.

## Determinism

Every calculation must be reproducible: the same ledger, factor tables,
uncertainty configuration and seed must produce byte-identical output. The
regression tests check this. If you add a stochastic step, seed it explicitly
and draw in a sorted, stable order.

## Before you open a pull request

```
PYTHONPATH=src python3 -m pytest
python3 scripts/gen_schema.py   # if you touched schema.py
```

Adding a factor table? Read `docs/data.md` first. Every row needs a source, a
database version, a region, a retrieval date, an uncertainty class and a licence.
