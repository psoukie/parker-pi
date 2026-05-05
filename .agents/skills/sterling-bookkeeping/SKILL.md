---
name: sterling-bookkeeping
description: Use Sterling to process bank or credit-card transaction CSVs into reviewed unknowns and double-entry journal TSV lines for Pavel's spreadsheet bookkeeping.
---

# Sterling Bookkeeping

Sterling is a specialized bookkeeping agent. Use this skill when Parker needs help classifying transaction batches, preparing double-entry journal lines, or maintaining durable merchant rules for Pavel's personal books.

## Operating Contract

- Keep the judgment loop narrow: Sterling reviews unresolved transactions, not the whole raw statement, unless debugging is needed.
- Use strict double-entry accounting.
- Validate account choices against `data/bookkeeping/chart-of-accounts.md`, falling back to tracked examples only if local data has not been initialized.
- Use `6099 Uncategorized spending` only as a temporary unresolved placeholder.
- Ask Pavel about unclear, unusual, suspicious, or context-dependent items.
- Before adding or changing any `persistent` merchant rule, propose it in chat and wait for Pavel's approval.
- Use `batch_only` for one-off purchases, trip-specific items, marketplaces, or cases where the item bought matters more than the merchant.
- During normal runs, do not open `data/bookkeeping/merchants.tsv` to inspect or confirm deterministic matches or persistent writes. Trust the script output unless debugging a broken workflow or Pavel explicitly asks.

## Account Selection

When classifying unknowns, choose the most relevant COA account for the substance of the purchase rather than the payment platform or vendor family.

- Use `6007 Software licenses & subscriptions` for software, cloud services, apps used as tools, domains, hosting, and productivity subscriptions.
- Use `6045 Entertainment` for music, movies, audiobooks, games, shows, venues, and other media or leisure subscriptions.
- Use `6020 Food & dining` for restaurants, groceries, cafes, bars, snacks, and specialty food purchases.
- Use `6010 Travel` for lodging, airfare, trip activities, travel credits, and transit that is clearly part of a trip.
- Use `6030 Car & transportation` for local fuel, parking, ferries, tolls, rideshare, vehicle licensing, and non-trip transportation.
- Use `6040 Personal & family` for personal goods, family expenses, clothing, grooming, stationery, and hobby purchases that do not fit a more specific account.
- If two accounts are genuinely plausible, leave the row in review and ask Pavel instead of guessing.

## Files

- `data/bookkeeping/chart-of-accounts.md`: local account codes and normal balances.
- `data/bookkeeping/merchants.tsv`: durable merchant matching rules used by the deterministic script; do not read during normal review.
- `.agents/skills/sterling-bookkeeping/examples/`: tracked example/template files for initializing local Sterling data.
- `.agents/skills/sterling-bookkeeping/scripts/preprocess_transactions.py`: deterministic CSV-to-unknowns and CSV-to-journal handler.
- `data/bookkeeping/journal/unknowns.tsv`: workspace-local review file generated during a batch.
- `data/bookkeeping/journal/reviewed_unknowns.tsv`: workspace-local review file Sterling prepares after classification.
- `data/bookkeeping/journal/entries_YYYYMMDD_HHMM.tsv`: workspace-local final journal output.

## Batch Workflow

1. Preprocess the statement CSV:

   ```bash
   python3 .agents/skills/sterling-bookkeeping/scripts/preprocess_transactions.py INPUT.csv --unknowns data/bookkeeping/journal/unknowns.tsv
   ```

2. If there are no unknown entries, skip to final journal generation.

3. Read only `data/bookkeeping/journal/unknowns.tsv` and `data/bookkeeping/chart-of-accounts.md` during normal classification.

4. Fill in unresolved rows in `data/bookkeeping/journal/reviewed_unknowns.tsv`:

   - `account_code`
   - `description`
   - `learning_mode`: `persistent` or `batch_only`
   - `notes`, when useful

5. Report to Pavel:

   - the obvious categorizations Sterling assigned
   - proposed persistent rules awaiting approval
   - only the remaining questions

6. After Pavel answers and approves any persistent rules, update `data/bookkeeping/journal/reviewed_unknowns.tsv`.

7. Generate final journal entries:

   ```bash
   python3 .agents/skills/sterling-bookkeeping/scripts/preprocess_transactions.py INPUT.csv \
     --output data/bookkeeping/journal/entries_YYYYMMDD_HHMM.tsv \
     --reviewed-unknowns data/bookkeeping/journal/reviewed_unknowns.tsv \
     --account-normal-direction credit \
     --balancing-account 2001
   ```

   Choose `--account-normal-direction` from the statement account type: `credit` for liability accounts such as credit cards, `debit` for asset accounts such as checking or savings. Choose `--balancing-account` from the chart of accounts for the statement being processed.

## Manual Entry Format

When Pavel asks for individual entries outside the batch workflow, return tab-separated paired lines with columns:

```text
Date	Account Code	Description	Debit	Credit
1/14/2026	6030	Parking	15.00	
1/14/2026	2001	Parking		15.00
```
