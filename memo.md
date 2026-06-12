## Summary

I reviewed all 50,000 claims and $26.4M in payments processed in 2025. The analysis identified **$45,290.24 in leakage** across four distinct issues, representing roughly 0.17% of total spend. Three of the four findings are high-confidence and mechanically verifiable. One finding is medium-confidence and should be researched further before any recovery action.

The good news is controls that should be working largely are. Uncontracted providers ($0 paid on 1,208 claims) and providers with leading-zero TIN encoding mismatches (313 claims) were both correctly blocked. The leakage found stems from a small number of specific system gaps, not a widespread control failure.


## What We Found

### Finding 1 — Duplicate Payments: $1,837 with High Confidence

**What happened.** Eight claim IDs were each paid twice, on different dates. This appears to be a payment processing bug: the same claim was submitted or reprocessed and the system did not detect the duplicate.

**Evidence.** `CL00137119` was paid $850 twice (2025-12-09 and 2025-12-27); `CL00138361` was paid $330 twice (2025-03-03 and 2025-03-21). Similarly, the remaining six claims show identical amounts across the two payment dates.

**Recoverable.** $1,837 (one payment per claim id is correct, the second is an overpayment). Recovery is straightforward, as we can issue offsets or deduct from next remittance.

**Recommended action.** Recover all eight. Add a claim id uniqueness check as a pre-payment gate in the adjudication system.


### Finding 2 — Post-Termination Payments: $22,203 with High Confidence

**What happened.** 40 claims were paid to providers whose contracts had already expired on the date of service, spanning 12 provider TINs. The one active amendment in the reference data (TIN 886786077, term extended to 2025-12-08) was correctly accounted for as none of the 40 claims involve that provider.

**Evidence.** Example: `CL00129855` — paid $4,500 to Nob Hill Sports Medicine (TIN 632813741, contract end 2025-03-30). The largest single provider is Russian Hill Internal Medicine with 4 claims totaling $5,310.

**Recoverable.** $22,203 total. The recovery is defensible because no valid contract existed on the DOS.

**Recommended action.** Pursue recovery via provider offset for all 12 affected TINs. Before sending demand letters, ops should confirm no verbal extensions or unsigned renewals were in progress because if any provider can produce a countersigned agreement, that claim should be released. A hard adjudication block that rejects claims from providers whose contract end data has passed with no active amendment should also be implemented.


### Finding 3 — Billed-Charges Paid Due to TIN Format Bug: $15,777 with High Confidence

**What happened.** Two contracted providers — Pacific Heights Heart Center (correct TIN: 254184780) and Castro Bone & Joint (634174773) — have their TINs stored with a dash separator in claims data (e.g., 25-4184780). The adjudication system appears to fail its fee schedule lookup when it encounters this format and falls back to paying the provider's billed charges instead of the contracted rate. Every single one of the 50 affected claims was paid at exactly the billed amount.

**Evidence.** `CL00147778`: CPT 59400, 2 units × $3,200 fee schedule rate = $6,400 allowed. Paid: $12,182.91 (exact billed amount). Overpaid by $5,782.91.`CL00122779`: CPT 29881, 2 units × $1,850 = $3,700 allowed. Paid: $5,989.15. Overpaid by $2,289.15.

**Recoverable.** $15,777.01 (the difference between billed and fee schedule for all 50 claims).

**Important note.** The providers are contracted and the services are legitimate. The error is purely in TIN formatting. Recovery is a *recoupment* of the excess above contracted rates, not a denial. Include the contract language and the correct fee schedule in any demand letter.

**Recommended action.** Normalize TIN format (strip dashes) in the ingestion layer before fee schedule lookup. Recover the excess from both providers. This is the most operationally significant systemic fix. The same bug could affect additional providers if their TINs are ever submitted with dashes.


### Finding 4 — Ineligible Member Claims: $1,345 with Medium-High Confidence

**What happened.** Fifteen claims were paid where the date of service falls after the member's `eligible_thru` date, with no evidence of re-enrollment.

**What was NOT flagged.** Six additional claims had DOS after `eligible_thru`, but for members whose eligibility history shows a `RETRO_REINSTATE` event. This means that their eligibility was retroactively restored. Those claims are correctly paid and excluded from this finding.

**Evidence.** `CL00125979` — member M101545 (eligible through 2025-07-02), claim DOS 2025-07-09, paid $285. `CL00131609` — member M102728 (eligible through 2025-03-09), DOS 2025-03-20, paid $145.

**Recoverable.** $1,345. However, before pursuing recovery, ops should verify with the enrollment team that no retroactive re-enrollment occurred for any of the 15 members. Some termination events are processed with a lag; a brief check prevents demanding money for legitimately covered services.

**Recommended action.** Confirm eligibility status for all 15 members, then recover on confirmed cases. Add a real-time eligibility check at adjudication using the eligibility history table, not just `members.eligible_thru`.


### Finding 5 — Miscellaneous Fee Schedule Overpayments: $4,128 with Medium Confidence — Do Not Recover Yet

**What happened.** Eighteen additional claims across 18 different providers were paid above the fee schedule allowed amount. The two largest are `CL00135890` ($1,668 over, CPT 19120) and `CL00123296` ($1,178 over, CPT 29827).

**Why I'm less certain.** Unlike Findings 1–4, I cannot identify a clear single mechanism. Some of these may reflect legitimate rate carve-outs not captured in the reference data I was given, verbal amendments, or bilateral agreements outside the central contract management system. The overpaid amounts vary widely and do not share a common pattern (not all billed-equals- paid; not all same-modifier).

**Recommended action.** Do not send recovery demands on these 18 claims until the contracts team has reviewed each provider's file. If no rate exception exists, recover. If any do, document them in `contract_carveouts.csv` going forward.


## What We Should NOT Recover

**Carveout claims (provider 238494007, CPT 72148).** Nob Hill Pediatric Group has a negotiated carveout rate of $720 for CPT 72148 versus the standard $480 fee schedule rate. Five claims were paid at $720 — this is correct. These look like overpayments if you compare to the fee schedule alone, but the carveout overrides the schedule. Do not recover.

**Retro-reinstated members (6 claims).** As noted above, six post-termination member claims were paid for members subsequently reinstated retroactively. These are correct payments. Do not recover.

**Zero-payment uncontracted claims (1,208 claims, $0 paid).** The system correctly paid nothing for uncontracted providers. These should remain $0. Do not recover. 


## Totals

| Finding | Claims | Amount | Confidence |
|---------|--------|--------|------------|
| F1: Duplicate payments | 8 | $1,837 | High |
| F2: Post-termination | 40 | $22,203 | High |
| F3: TIN format / billed charges | 50 | $15,777 | High |
| F4: Ineligible members | 15 | $1,345 | Medium-High |
| F5: Misc fee schedule | 18 | $4,128 | Medium |
| **Total** | **131** | **$45,290** | |

High-confidence leakage (F1–F4): **$41,162**

Medium-confidence leakage (F5): **$4,128**


## Operational Recommendations

**Immediate (this week):**
- Block duplicate payments at adjudication with a claim_id uniqueness check.
- Normalize TIN format (remove dashes, add leading zeros) before fee schedule lookup — single code fix, eliminates Finding 3 permanently.
- Issue recovery letters for F1 and F3 (no contractual ambiguity).

**Near-term (30 days):**
- Pursue F2 provider recovery after contract extension check.
- Confirm eligibility for F4 members, then recover on confirmed cases.
- Investigate F5 claims with contracts team.

**Systemic:**
- Rebuild the eligibility check to query `members_eligibility_history` in real time, not rely solely on `members.eligible_thru`.
- Add a contract expiry gate that hard-stops claims from providers past their end date unless an active amendment exists.
- Centralize all carve-outs and amendments in a single reference store; manual side agreements create audit gaps.

**Legal/compliance flag:** Finding 3 (billed-charges / TIN format bug) should be reviewed with legal before issuing demand letters. Paying billed charges rather than contracted rates could be characterized as a billing error on the provider's part or a system failure on ours, depending on how the contracts are written. The recovery is likely valid, but the framing of the demand matters.
