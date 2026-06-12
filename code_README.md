# Claims Leakage Analysis — Code

## Requirements

```
pip install pandas numpy
```

Python 3.9+ required.

## Running

```bash
python analysis.py
```

By default, the script reads data from `/mnt/user-data/uploads/`. To change
the data path, update the `DATA_DIR` constant at the top of `analysis.py`.

Expected input files in `DATA_DIR`:
- `claims.csv`
- `payments.csv`
- `providers.csv`
- `members.csv`
- `fee_schedule.csv`
- `members_eligibility_history.csv`
- `contract_amendments.csv`
- `contract_carveouts.csv`

## What the script does

The script runs five leakage checks in sequence and prints a summary:

1. **Duplicate payments** — detects `claim_id` appearing more than once in `payments.csv`
2. **Post-termination payments** — compares claim DOS against effective contract end dates (after applying amendments)
3. **Billed-charges / TIN format bug** — finds claims where TINs are dash-formatted (e.g. `25-4184780`) causing the system to pay billed charges instead of fee schedule rates
4. **Ineligible member claims** — finds claims where DOS > `eligible_thru`, excluding members with retroactive reinstatement
5. **Miscellaneous fee schedule overpayments** — catches remaining claims paid above contracted allowed amounts

## Key data quality issues found

- `claims.dos` has two date formats (`MM/DD/YYYY` and `YYYY-MM-DD`) — handled via `format='mixed'`
- `provider_tin` in claims appears as integers in `providers.csv` (leading zeros stripped) but as zero-padded strings in some claims rows — handled via `.lstrip('0')` matching
- Two providers have TINs stored with dashes in claims (`25-4184780`, `63-4174773`) — normalized via `.str.replace('-', '')`

## Output

Console only. All findings print with claim-level examples and dollar totals.
