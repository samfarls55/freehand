# Cleanup output review

Synthetic fixture replay; every output requires human review. This is not a Windows application benchmark.

Judge final intended facts, correction handling, voice and readable formatting before checking the identity key.

## dev-035 (literal_marker)

Input:

```text
Uh, replace it with [[FREEHAND_LITERAL_01_START]]  Acme	Labs  [[FREEHAND_LITERAL_01_END]] exactly.
```

### Candidate 1 / repetition 1

```text
Uh, replace it with [[FREEHAND_LITERAL_01_START]]  Acme	Labs  [[FREEHAND_LITERAL_01_END]] exactly.
```

### Candidate 2 / repetition 1

```text
Replace it with [[FREEHAND_LITERAL_01_START]]  Acme	Labs  [[FREEHAND_LITERAL_01_END]] exactly.
```

## dev-044 (literal_marker)

Input:

```text
Keep [[FREEHAND_LITERAL_02_START]]v2::Thing<T>
  value[[FREEHAND_LITERAL_02_END]] and [[FREEHAND_LITERAL_03_START]]$  42[[FREEHAND_LITERAL_03_END]] in that order.
```

### Candidate 1 / repetition 1

```text
Keep [[FREEHAND_LITERAL_02_START]]v2::Thing<T>
  value[[FREEHAND_LITERAL_02_END]] and [[FREEHAND_LITERAL_03_START]]$  42[[FREEHAND_LITERAL_03_END]] in that order.
```

### Candidate 2 / repetition 1

```text
Keep [[FREEHAND_LITERAL_02_START]]v2::Thing<T>
  value[[FREEHAND_LITERAL_02_END]] and [[FREEHAND_LITERAL_03_START]]$  42[[FREEHAND_LITERAL_03_END]] in that order.
```
