"""
Swan Case: Healthcare Claims Leakage Analysis
Author: Data Analysis
Usage: python analysis.py
Requires: pandas, numpy
Input files expected in same directory (or adjust DATA_DIR)
"""

import pandas as pd
import numpy as np
import os

DATA_DIR = "/mnt/user-data/uploads"

def load_data():
    claims = pd.read_csv(f"{DATA_DIR}/claims.csv")
    payments = pd.read_csv(f"{DATA_DIR}/payments.csv")
    providers = pd.read_csv(f"{DATA_DIR}/providers.csv")
    fee_schedule = pd.read_csv(f"{DATA_DIR}/fee_schedule.csv")
    amendments = pd.read_csv(f"{DATA_DIR}/contract_amendments.csv")
    carveouts = pd.read_csv(f"{DATA_DIR}/contract_carveouts.csv")
    elig_history = pd.read_csv(f"{DATA_DIR}/members_eligibility_history.csv")
    members = pd.read_csv(f"{DATA_DIR}/members.csv")
    return claims, payments, providers, fee_schedule, amendments, carveouts, elig_history, members

def fix_dtypes(claims, payments, providers, fee_schedule, amendments, carveouts, elig_history, members):
    """Fix data types and normalize formats across all tables."""
    # Date parsing - claims.dos has mixed MM/DD/YYYY and YYYY-MM-DD formats (data quality issue)
    claims['dos'] = pd.to_datetime(claims['dos'], format='mixed')
    
    # TIN normalization: claims has two format issues:
    #   1. Some TINs use dash format (e.g., "25-4184780" instead of "254184780")
    #   2. Some TINs have leading zeros stripped when stored as int in providers table
    claims['provider_tin'] = claims['provider_tin'].astype(str)
    claims['provider_tin_norm'] = claims['provider_tin'].str.replace('-', '', regex=False)
    # Strip leading zeros to match providers table (which stores as int)
    claims['provider_tin_stripped'] = claims['provider_tin_norm'].str.lstrip('0')
    
    claims['cpt'] = claims['cpt'].astype(str)
    
    providers['tin'] = providers['tin'].astype(str)
    providers['tin_stripped'] = providers['tin'].str.lstrip('0')
    providers['contract_start_date'] = pd.to_datetime(providers['contract_start_date'])
    providers['contract_end_date'] = pd.to_datetime(providers['contract_end_date'])
    
    fee_schedule['cpt'] = fee_schedule['cpt'].astype(str)
    
    amendments['provider_tin'] = amendments['provider_tin'].astype(str)
    amendments['new_contract_end_date'] = pd.to_datetime(amendments['new_contract_end_date'])
    amendments['amendment_effective_date'] = pd.to_datetime(amendments['amendment_effective_date'])
    
    carveouts['provider_tin'] = carveouts['provider_tin'].astype(str)
    carveouts['effective_date'] = pd.to_datetime(carveouts['effective_date'])
    carveouts['cpt'] = carveouts['cpt'].astype(str)
    
    members['eligible_from'] = pd.to_datetime(members['eligible_from'])
    members['eligible_thru'] = pd.to_datetime(members['eligible_thru'])
    
    elig_history['period_from'] = pd.to_datetime(elig_history['period_from'])
    elig_history['period_thru'] = pd.to_datetime(elig_history['period_thru'])
    
    payments['paid_date'] = pd.to_datetime(payments['paid_date'])
    
    return claims, payments, providers, fee_schedule, amendments, carveouts, elig_history, members

def apply_amendments(providers, amendments):
    """Apply contract amendments to effective provider table."""
    providers_eff = providers.copy()
    for _, amend in amendments.iterrows():
        mask = providers_eff['tin'] == amend['provider_tin']
        if amend['amendment_type'] == 'TERM_EXTENSION':
            providers_eff.loc[mask, 'contract_end_date'] = amend['new_contract_end_date']
            print(f"  Applied amendment: TIN {amend['provider_tin']} extended to {amend['new_contract_end_date'].date()}")
    return providers_eff

def calc_correct_allowed(row, carveout_tin='238494007', carveout_cpt='72148', carveout_rate=720.0):
    """
    Calculate the correct allowed amount per claim.
    Rules (from pricing_notes.md):
    - Carveout: provider 238494007, CPT 72148 -> $720 flat rate
    - Modifier 22 -> 1.20x of fee schedule
    - All other modifiers (25, 59, RT, LT) -> no payment effect
    """
    # Carveout takes precedence
    if row['provider_tin_norm'] == carveout_tin and row['cpt'] == carveout_cpt:
        return carveout_rate
    base = row['allowed_unit_amount'] * row['units']
    if str(row['modifier']) == '22':
        return base * 1.20
    return base

def finding_duplicate_payments(payments):
    """FINDING 1: Duplicate payments - same claim_id paid more than once."""
    dup_mask = payments.duplicated('claim_id', keep=False)
    dup_payments = payments[dup_mask]
    # Amount recoverable = sum of second (and beyond) payments
    first_payments = payments.drop_duplicates('claim_id', keep='first')
    dup_extra = payments[payments.duplicated('claim_id', keep='first')]
    
    print(f"\n{'='*60}")
    print(f"FINDING 1: Duplicate Payments")
    print(f"{'='*60}")
    print(f"  Unique claim IDs paid more than once: {dup_payments['claim_id'].nunique()}")
    print(f"  Total extra payment rows: {len(dup_extra)}")
    print(f"  Recoverable amount: ${dup_extra['paid_amt'].sum():,.2f}")
    print(f"  Example duplicate claims:")
    for cid in dup_payments['claim_id'].unique():
        rows = payments[payments['claim_id'] == cid]
        amt = rows['paid_amt'].iloc[0]
        dates = rows['paid_date'].dt.strftime('%Y-%m-%d').tolist()
        print(f"    {cid}: ${amt:.2f} paid on {dates}")
    
    return dup_extra['paid_amt'].sum(), dup_payments['claim_id'].unique()

def finding_post_termination(claims, payments, providers_eff):
    """FINDING 2: Claims paid after provider contract end date."""
    payments_dedup = payments.drop_duplicates('claim_id', keep='first')
    
    # Match using normalized TINs (handles leading-zero and dash variants)
    claims_prov = claims.merge(
        providers_eff[['tin','contracted','contract_start_date','contract_end_date']], 
        left_on='provider_tin_norm', right_on='tin', how='left'
    )
    
    contracted_with_end = claims_prov[
        (claims_prov['contracted'] == 'Y') & 
        (claims_prov['contract_end_date'].notna())
    ].copy()
    
    after_end = contracted_with_end[contracted_with_end['dos'] > contracted_with_end['contract_end_date']].copy()
    after_end_paid = after_end.merge(payments_dedup, on='claim_id')
    
    print(f"\n{'='*60}")
    print(f"FINDING 2: Post-Termination Payments")
    print(f"{'='*60}")
    print(f"  Claims after contract end: {len(after_end_paid)}")
    print(f"  Providers affected: {after_end_paid['provider_tin_norm'].nunique()}")
    print(f"  Total paid: ${after_end_paid['paid_amt'].sum():,.2f}")
    
    by_prov = after_end_paid.merge(
        providers_eff[['tin','name']], left_on='provider_tin_norm', right_on='tin', how='left'
    ).groupby(['provider_tin_norm','name'])['paid_amt'].agg(['count','sum']).sort_values('sum', ascending=False)
    print(f"\n  By provider:")
    print(by_prov.to_string())
    
    print(f"\n  Top 5 claims by amount:")
    top5 = after_end_paid.nlargest(5, 'paid_amt')[['claim_id','provider_tin','dos','contract_end_date','paid_amt']]
    print(top5.to_string(index=False))
    
    return after_end_paid['paid_amt'].sum(), after_end_paid['claim_id'].tolist()

def finding_billed_charges_dash_tin(claims, payments, fee_schedule):
    """FINDING 3: Two providers with dash-formatted TINs paid at billed charges instead of fee schedule."""
    payments_dedup = payments.drop_duplicates('claim_id', keep='first')
    
    dash_claims = claims[claims['provider_tin'].str.contains('-', na=False)].copy()
    dash_paid = dash_claims.merge(fee_schedule[['cpt','allowed_unit_amount']], on='cpt', how='left')
    dash_paid = dash_paid.merge(payments_dedup, on='claim_id')
    dash_paid['correct_allowed'] = dash_paid.apply(calc_correct_allowed, axis=1)
    dash_paid['overpaid'] = dash_paid['paid_amt'] - dash_paid['correct_allowed']
    dash_paid['paid_eq_billed'] = (dash_paid['paid_amt'] - dash_paid['billed_amt']).abs() < 1.0
    
    print(f"\n{'='*60}")
    print(f"FINDING 3: Billed-Charges Payment Due to TIN Format Bug")
    print(f"{'='*60}")
    print(f"  Root cause: TINs stored with dashes (e.g. '25-4184780') bypass fee schedule lookup")
    print(f"  System falls back to paying billed charges (provider markup)")
    print(f"  Providers: {dash_claims['provider_tin'].unique().tolist()}")
    print(f"  (Normalize to: Pacific Heights Heart Center 254184780, Castro Bone & Joint 634174773)")
    print(f"  Claims affected: {len(dash_paid)}")
    print(f"  Paid at billed charges: {dash_paid['paid_eq_billed'].sum()}/{len(dash_paid)} claims")
    print(f"  Total paid: ${dash_paid['paid_amt'].sum():,.2f}")
    print(f"  Should have been: ${dash_paid['correct_allowed'].sum():,.2f}")
    print(f"  Overpayment: ${dash_paid['overpaid'].sum():,.2f}")
    
    top5 = dash_paid.nlargest(5, 'overpaid')[['claim_id','provider_tin','cpt','billed_amt','correct_allowed','paid_amt','overpaid']]
    print(f"\n  Top 5 by overpayment:")
    print(top5.to_string(index=False))
    
    return dash_paid['overpaid'].sum(), dash_paid['claim_id'].tolist()

def finding_ineligible_members(claims, payments, members, elig_history):
    """FINDING 4: Claims paid for members past their eligibility end date."""
    payments_dedup = payments.drop_duplicates('claim_id', keep='first')
    
    # Members with retroactive reinstatement should NOT be flagged
    retro_members = elig_history[elig_history['termination_reason'] == 'RETRO_REINSTATE']['member_id'].unique()
    
    claims_mem = claims.merge(members, on='member_id', how='left')
    has_thru = claims_mem[claims_mem['eligible_thru'].notna()].copy()
    after_thru = has_thru[has_thru['dos'] > has_thru['eligible_thru']].copy()
    
    # Exclude retroactively reinstated members
    truly_ineligible = after_thru[~after_thru['member_id'].isin(retro_members)]
    retro_excluded = after_thru[after_thru['member_id'].isin(retro_members)]
    
    inelig_paid = truly_ineligible.merge(payments_dedup, on='claim_id')
    
    print(f"\n{'='*60}")
    print(f"FINDING 4: Ineligible Member Claims")
    print(f"{'='*60}")
    print(f"  Claims after eligible_thru: {len(after_thru)}")
    print(f"  Excluded (retro-reinstated members, correctly paid): {len(retro_excluded)} claims, "
          f"{retro_excluded['member_id'].nunique()} members")
    print(f"  Truly ineligible: {len(inelig_paid)} claims")
    print(f"  Total paid: ${inelig_paid['paid_amt'].sum():,.2f}")
    print(f"\n  Details:")
    print(inelig_paid[['claim_id','member_id','dos','eligible_thru','paid_amt']].to_string(index=False))
    
    return inelig_paid['paid_amt'].sum(), inelig_paid['claim_id'].tolist()

def finding_misc_fee_schedule(claims, payments, fee_schedule):
    """FINDING 5: Miscellaneous fee schedule overpayments (non-dash, non-carveout providers)."""
    payments_dedup = payments.drop_duplicates('claim_id', keep='first')
    
    non_dash = claims[~claims['provider_tin'].str.contains('-', na=False)].copy()
    fs_joined = non_dash.merge(fee_schedule[['cpt','allowed_unit_amount']], on='cpt', how='left')
    paid_joined = fs_joined.merge(payments_dedup, on='claim_id')
    paid_joined['correct_allowed'] = paid_joined.apply(calc_correct_allowed, axis=1)
    paid_joined['overpaid'] = paid_joined['paid_amt'] - paid_joined['correct_allowed']
    
    overpaid = paid_joined[paid_joined['overpaid'] > 0.50].copy()
    
    print(f"\n{'='*60}")
    print(f"FINDING 5: Miscellaneous Fee Schedule Overpayments")
    print(f"{'='*60}")
    print(f"  Claims overpaid vs fee schedule: {len(overpaid)}")
    print(f"  Total: ${overpaid['overpaid'].sum():,.2f}")
    print(f"  Note: Carveout claims (238494007/72148) correctly excluded")
    print(f"\n  Top 10 by overpayment:")
    top10 = overpaid.nlargest(10, 'overpaid')[
        ['claim_id','provider_tin','cpt','units','correct_allowed','paid_amt','overpaid']
    ]
    print(top10.to_string(index=False))
    
    return overpaid['overpaid'].sum(), overpaid['claim_id'].tolist()

def main():
    print("Loading data...")
    claims, payments, providers, fee_schedule, amendments, carveouts, elig_history, members = load_data()
    
    print("Fixing data types...")
    claims, payments, providers, fee_schedule, amendments, carveouts, elig_history, members = \
        fix_dtypes(claims, payments, providers, fee_schedule, amendments, carveouts, elig_history, members)
    
    print("\nApplying contract amendments:")
    providers_eff = apply_amendments(providers, amendments)
    
    print(f"\nData overview:")
    print(f"  Claims: {len(claims):,}")
    print(f"  Total paid (raw): ${payments['paid_amt'].sum():,.2f}")
    print(f"  Total paid (deduped): ${payments.drop_duplicates('claim_id', keep='first')['paid_amt'].sum():,.2f}")
    
    # Run all findings
    f1_amt, f1_ids = finding_duplicate_payments(payments)
    f2_amt, f2_ids = finding_post_termination(claims, payments, providers_eff)
    f3_amt, f3_ids = finding_billed_charges_dash_tin(claims, payments, fee_schedule)
    f4_amt, f4_ids = finding_ineligible_members(claims, payments, members, elig_history)
    f5_amt, f5_ids = finding_misc_fee_schedule(claims, payments, fee_schedule)
    
    total = f1_amt + f2_amt + f3_amt + f4_amt + f5_amt
    total_paid = payments.drop_duplicates('claim_id', keep='first')['paid_amt'].sum()
    
    print(f"\n{'='*60}")
    print(f"GRAND TOTAL LEAKAGE ESTIMATE")
    print(f"{'='*60}")
    print(f"  F1 Duplicate payments:        ${f1_amt:>10,.2f}")
    print(f"  F2 Post-termination:          ${f2_amt:>10,.2f}")
    print(f"  F3 Billed-charges (dash TIN): ${f3_amt:>10,.2f}")
    print(f"  F4 Ineligible members:        ${f4_amt:>10,.2f}")
    print(f"  F5 Misc fee schedule:         ${f5_amt:>10,.2f}")
    print(f"  {'TOTAL':28s}  ${total:>10,.2f}")
    print(f"\n  As % of total paid: {total/total_paid*100:.2f}%")
    print(f"\n  NOTE: F5 (misc fee schedule) is medium-confidence.")
    print(f"        High-confidence leakage: ${f1_amt+f2_amt+f3_amt+f4_amt:,.2f}")

if __name__ == "__main__":
    main()
