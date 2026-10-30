# Cleanup output review

Synthetic fixture replay; every output requires human review. This is not a Windows application benchmark.

Judge final intended facts, correction handling, voice and readable formatting before checking the identity key.

## integration-01 (literal_whitespace)

Input:

```text
Um send it to   Claude	Code   please.
```

### Candidate 1 / repetition 1

```text
Um send it to   Claude	Code   please.
```

### Candidate 2 / repetition 1

```text
Send it to [[FREEHAND_LITERAL_5e39575a23244f7caf3e174a3875e2fe_0_START]]  Claude	Code  [[FREEHAND_LITERAL_5e39575a23244f7caf3e174a3875e2fe_0_END]], please.
```

### Candidate 3 / repetition 1

```text
Send it to   Claude	Code  , please.
```

## integration-02 (literal_path)

Input:

```text
Uh open C:\Work\Freehand\src\App.cs and check the logs.
```

### Candidate 1 / repetition 1

```text
Uh open C:\Work\Freehand\src\App.cs and check the logs.
```

### Candidate 2 / repetition 1

```text
Open [[FREEHAND_LITERAL_4ed7d86914ed4057b8828351a38ca157_0_START]]C:\Work\Freehand\src\App.cs[[FREEHAND_LITERAL_4ed7d86914ed4057b8828351a38ca157_0_END]] and check the logs.
```

### Candidate 3 / repetition 1

```text
Open C:\Work\Freehand\src\App.cs and check the logs.
```

## integration-03 (literal_currency)

Input:

```text
Um the quoted price is $  42.00 exactly.
```

### Candidate 1 / repetition 1

```text
Um the quoted price is $  42.00 exactly.
```

### Candidate 2 / repetition 1

```text
The quoted price is [[FREEHAND_LITERAL_cdc85cda54b348c0b1ce9a701c70a3bc_0_START]]$  42.00[[FREEHAND_LITERAL_cdc85cda54b348c0b1ce9a701c70a3bc_0_END]] exactly.
```

### Candidate 3 / repetition 1

```text
The quoted price is $  42.00 exactly.
```

## integration-04 (literal_multiple)

Input:

```text
Uh send ACME  Labs the /etc/freehand/settings.json this afternoon.
```

### Candidate 1 / repetition 1

```text
Uh send ACME  Labs the /etc/freehand/settings.json this afternoon.
```

### Candidate 2 / repetition 1

```text
Send [[FREEHAND_LITERAL_fd66e99945b9443cb4a5394a577a3f68_0_START]]ACME  Labs[[FREEHAND_LITERAL_fd66e99945b9443cb4a5394a577a3f68_0_END]] the [[FREEHAND_LITERAL_fd66e99945b9443cb4a5394a577a3f68_1_START]]/etc/freehand/settings.json[[FREEHAND_LITERAL_fd66e99945b9443cb4a5394a577a3f68_1_END]] this afternoon.
```

### Candidate 3 / repetition 1

```text
Send ACME  Labs the /etc/freehand/settings.json this afternoon.
```

## integration-05 (literal_multiline)

Input:

```text
Um replace the snippet with v2::Thing<T>
  value exactly.
```

### Candidate 1 / repetition 1

```text
Um replace the snippet with v2::Thing<T>
  value exactly.
```

### Candidate 2 / repetition 1

```text
Replace the snippet with [[FREEHAND_LITERAL_3bb0b6743feb4ae0a9a93f5517a9f6e0_0_START]]v2::Thing<T>
  value[[FREEHAND_LITERAL_3bb0b6743feb4ae0a9a93f5517a9f6e0_0_END]] exactly.
```

### Candidate 3 / repetition 1

```text
Replace the snippet with v2::Thing<T>
  value exactly.
```

## integration-06 (literal_number_normalization)

Input:

```text
Uh send $50 to ACME before lunch.
```

### Candidate 1 / repetition 1

```text
Uh send $50 to ACME before lunch.
```

### Candidate 2 / repetition 1

```text
Send $50 to [[FREEHAND_LITERAL_d57caf6702924cba8515ab26deb646d7_0_START]]ACME[[FREEHAND_LITERAL_d57caf6702924cba8515ab26deb646d7_0_END]] before lunch.
```

### Candidate 3 / repetition 1

```text
Send $50 to ACME before lunch.
```

## integration-07 (literal_no_cascade)

Input:

```text
Um BetaProject is ready.
```

### Candidate 1 / repetition 1

```text
Um BetaProject is ready.
```

### Candidate 2 / repetition 1

```text
[[FREEHAND_LITERAL_83a1d9d0a2824484a31a343c15fa3745_0_START]]BetaProject[[FREEHAND_LITERAL_83a1d9d0a2824484a31a343c15fa3745_0_END]] is ready.
```

### Candidate 3 / repetition 1

```text
BetaProject is ready.
```

## integration-08 (literal_correction)

Input:

```text
Send it to ACME on Thursday, sorry, Friday.
```

### Candidate 1 / repetition 1

```text
Send it to ACME on Thursday, sorry, Friday.
```

### Candidate 2 / repetition 1

```text
Send it to [[FREEHAND_LITERAL_e87134c646af41af8305418a458f2271_0_START]]ACME[[FREEHAND_LITERAL_e87134c646af41af8305418a458f2271_0_END]] on Friday.
```

### Candidate 3 / repetition 1

```text
Send it to ACME on Friday.
```

## integration-09 (literal_superseded)

Input:

```text
Send it to ACME, sorry, send it to Priya instead.
```

### Candidate 1 / repetition 1

```text
Send it to ACME, sorry, send it to Priya instead.
```

### Candidate 2 / repetition 1

```text
Send it to [[FREEHAND_LITERAL_718befda746041129cda5bf7f0d7093a_0_START]]ACME[[FREEHAND_LITERAL_718befda746041129cda5bf7f0d7093a_0_END]]; sorry, send it to Priya instead.
```

### Candidate 3 / repetition 1

```text
Send it to ACME; sorry, send it to Priya instead.
```

## integration-10 (literal_unicode)

Input:

```text
Uh ask Zoë Nguyễn whether the test passed.
```

### Candidate 1 / repetition 1

```text
Uh ask Zoë Nguyễn whether the test passed.
```

### Candidate 2 / repetition 1

```text
Ask [[FREEHAND_LITERAL_cfcd1e20837c464f938c55883d9bdcca_0_START]]Zoë Nguyễn[[FREEHAND_LITERAL_cfcd1e20837c464f938c55883d9bdcca_0_END]] whether the test passed.
```

### Candidate 3 / repetition 1

```text
Ask Zoë Nguyễn whether the test passed.
```
