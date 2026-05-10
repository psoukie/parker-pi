#!/usr/bin/env python3
"""Deterministic transaction handler for Sterling bookkeeping workflows.

This script can:
- preprocess a transaction CSV into journal TSV lines
- write a review-ready unknowns file containing only unresolved transactions
- persist selected reviewed unknowns into Sterling's merchant rules while
  generating final journal TSV output

Input CSV format examples:
  Posted Date, Payee, Amount
  Date, Description, Amount

Journal TSV format:
  date\taccount_code\tdescription\tdebit\tcredit

Unknowns / review TSV format:
  txn_key\tdate\tmerchant\traw_payee\tamount\taccount_code\tdescription\tlearning_mode\tnotes

Rules:
- Amount direction is interpreted using --account-normal-direction, which means
  "the side that normally increases for the account on the statement".
- For a liability-style statement account (like a credit card), use
  --account-normal-direction credit.
- For an asset-style statement account (like checking or savings), use
  --account-normal-direction debit.
- Merchant lookup is deterministic, case-insensitive, and substring-based.
- Longest matching merchant key wins.
- Unknown merchants default to 6099 Uncategorized spending in the unknowns
  report.
- Unknowns files contain full unresolved transaction detail and are not
  deduplicated.
- Reviewed unknowns may be marked persistent (learn into merchants.tsv) or
  batch_only (use only for this import).
"""

from __future__ import annotations

import csv
import sys
import re
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

SKILL_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = Path.cwd()
DATA_ROOT = WORKSPACE_ROOT / 'data' / 'bookkeeping'
DEFAULT_MERCHANTS = DATA_ROOT / 'merchants.tsv'
DEFAULT_OUTPUT = DATA_ROOT / 'journal' / 'preprocessed.tsv'
DEFAULT_UNKNOWNS = DATA_ROOT / 'journal' / 'unknowns.tsv'
DEFAULT_REVIEWED_UNKNOWNS = DATA_ROOT / 'journal' / 'reviewed_unknowns.tsv'
DEFAULT_BALANCING_ACCOUNT = '2001'
DEFAULT_ACCOUNT_NORMAL_DIRECTION = 'debit'


@dataclass(frozen=True)
class Mapping:
    merchant: str
    account_code: str
    description: str
    notes: str = ''


@dataclass(frozen=True)
class Transaction:
    txn_key: str
    date: str
    payee: str
    amount: float


@dataclass(frozen=True)
class ClassifiedTransaction:
    transaction: Transaction
    account_code: str
    description: str
    matched_merchant: Optional[str]


@dataclass(frozen=True)
class EnrichedCategory:
    merchant: str
    amount: str = ''
    account_code: str = ''
    description: str = ''
    notes: str = ''


def normalize(text: str) -> str:
    text = text.upper()
    text = re.sub(
        r'\bID:([^\s]+)',
        lambda match: 'ID:' + re.sub(r'\d+', '', match.group(1)),
        text,
    )
    text = re.sub(r"[^A-Z0-9 &./'\-]+", ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def money_to_str(amount: float) -> str:
    return f'{abs(amount):.2f}'


def read_tsv_rows(path: Path) -> List[dict]:
    if not path.exists():
        return []
    with path.open(newline='') as f:
        return list(csv.DictReader(f, delimiter='\t'))


def load_mappings(merchants_file: Path) -> List[Mapping]:
    mappings: List[Mapping] = []
    for row in read_tsv_rows(merchants_file):
        merchant = (row.get('merchant') or row.get('Merchant') or '').strip()
        account_code = (row.get('account_code') or row.get('Account Code') or '').strip()
        description = (row.get('description') or row.get('Description') or '').strip()
        notes = (row.get('notes') or row.get('Notes') or '').strip()
        if merchant and account_code and description:
            mappings.append(Mapping(merchant=merchant, account_code=account_code, description=description, notes=notes))
    return mappings


def match_mapping(payee: str, mappings: List[Mapping]) -> Optional[Mapping]:
    norm_payee = normalize(payee)
    best: Optional[Mapping] = None
    best_len = -1
    best_desc_len = -1
    for mapping in mappings:
        key = normalize(mapping.merchant)
        if key and key in norm_payee:
            if len(key) > best_len or (len(key) == best_len and len(mapping.description) > best_desc_len):
                best = mapping
                best_len = len(key)
                best_desc_len = len(mapping.description)
    return best


def parse_amount(raw: str) -> float:
    cleaned = raw.strip().replace(',', '')
    if cleaned.startswith('(') and cleaned.endswith(')'):
        cleaned = '-' + cleaned[1:-1]
    return float(cleaned)


def parse_date(raw: str) -> datetime:
    return datetime.strptime(raw.strip(), '%m/%d/%Y')


def read_transactions(csv_path: Path) -> List[Transaction]:
    transactions: List[Transaction] = []
    with csv_path.open(newline='') as f:
        reader = csv.DictReader(f)
        for row_index, row in enumerate(reader, start=1):
            date = (row.get('Posted Date') or row.get('Date') or '').strip()
            payee = (row.get('Payee') or row.get('Description') or row.get('Merchant') or '').strip()
            amount_raw = (row.get('Amount') or row.get('amount') or '').strip()
            if not date or not payee or not amount_raw:
                continue
            transactions.append(Transaction(txn_key=str(row_index), date=date, payee=payee, amount=parse_amount(amount_raw)))
    return transactions


def classify_transactions(transactions: List[Transaction], mappings: List[Mapping]) -> List[ClassifiedTransaction]:
    classified: List[ClassifiedTransaction] = []
    for tx in transactions:
        mapping = match_mapping(tx.payee, mappings)
        if mapping:
            description = mapping.description if mapping.account_code != '6099' else f'Unknown: {mapping.merchant}'
            classified.append(ClassifiedTransaction(transaction=tx, account_code=mapping.account_code, description=description, matched_merchant=mapping.merchant))
        else:
            classified.append(ClassifiedTransaction(transaction=tx, account_code='6099', description=f'Unknown: {tx.payee}', matched_merchant=None))
    classified.sort(key=lambda item: (parse_date(item.transaction.date), item.transaction.payee, item.transaction.amount))
    return classified


def purchase_sign(tx: Transaction, account_normal_direction: str) -> bool:
    if account_normal_direction == 'credit':
        return tx.amount < 0
    return tx.amount > 0


def payment_like_sign(tx: Transaction, account_normal_direction: str) -> bool:
    return not purchase_sign(tx, account_normal_direction) and tx.amount != 0


def render_journal_lines(classified: List[ClassifiedTransaction], balancing_account: str, account_normal_direction: str) -> List[str]:
    out: List[str] = ['date\taccount_code\tdescription\tdebit\tcredit']
    for item in classified:
        tx = item.transaction
        amt = abs(tx.amount)
        if amt == 0:
            continue
        if purchase_sign(tx, account_normal_direction):
            out.append(f'{tx.date}\t{item.account_code}\t{item.description}\t{money_to_str(amt)}\t')
            out.append(f'{tx.date}\t{balancing_account}\t{item.description}\t\t{money_to_str(amt)}')
        elif payment_like_sign(tx, account_normal_direction):
            out.append(f'{tx.date}\t{balancing_account}\t{item.description}\t{money_to_str(amt)}\t')
            out.append(f'{tx.date}\t{item.account_code}\t{item.description}\t\t{money_to_str(amt)}')
    return out


def render_unknowns(classified: List[ClassifiedTransaction]) -> List[str]:
    rows = ['txn_key\tdate\tmerchant\traw_payee\tamount\taccount_code\tdescription\tlearning_mode\tnotes']
    for item in classified:
        if item.matched_merchant is not None:
            continue
        payee = item.transaction.payee
        merchant = normalize(payee)
        txn_key = item.transaction.txn_key
        rows.append(f'{txn_key}\t{item.transaction.date}\t{merchant}\t{payee}\t{item.transaction.amount:.2f}\t6099\tUncategorized spending\treview\t')
    return rows


def write_text(path: Path, lines: Iterable[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")


def parse_enriched_file(path: Path) -> List[EnrichedCategory]:
    entries: List[EnrichedCategory] = []
    for row in read_tsv_rows(path):
        normalized_row = {str(k).lstrip('\ufeff'): v for k, v in row.items()}
        merchant = (normalized_row.get('merchant') or normalized_row.get('Merchant') or '').strip()
        amount = (normalized_row.get('amount') or normalized_row.get('Amount') or '').strip()
        account_code = (normalized_row.get('account_code') or normalized_row.get('Account Code') or '').strip()
        description = (normalized_row.get('description') or normalized_row.get('Description') or '').strip()
        notes = (normalized_row.get('notes') or normalized_row.get('Notes') or '').strip()
        if merchant and account_code and description:
            entries.append(EnrichedCategory(merchant=merchant, amount=amount, account_code=account_code, description=description, notes=notes))
    return entries


def append_merchant_entries(entries: List[EnrichedCategory], merchants_file: Path) -> int:
    existing_rows = []
    existing_by_key = {}
    for row in read_tsv_rows(merchants_file):
        merchant = (row.get('merchant') or row.get('Merchant') or '').strip()
        account_code = (row.get('account_code') or row.get('Account Code') or '').strip()
        description = (row.get('description') or row.get('Description') or '').strip()
        notes = (row.get('notes') or row.get('Notes') or '').strip()
        if merchant:
            normalized = normalize(merchant)
            record = {'merchant': merchant, 'account_code': account_code, 'description': description, 'notes': notes}
            existing_rows.append(record)
            existing_by_key[normalized] = record
    added = 0
    updated = 0
    for entry in entries:
        key = normalize(entry.merchant)
        if not key:
            continue
        new_record = {'merchant': entry.merchant, 'account_code': entry.account_code, 'description': entry.description, 'notes': entry.notes}
        if key in existing_by_key:
            record = existing_by_key[key]
            if record != new_record:
                record.update(new_record)
                updated += 1
            continue
        existing_rows.append(new_record)
        existing_by_key[key] = new_record
        added += 1
    merchants_file.parent.mkdir(parents=True, exist_ok=True)
    with merchants_file.open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['merchant', 'account_code', 'description', 'notes'], delimiter='\t')
        writer.writeheader()
        writer.writerows(existing_rows)
    return added + updated


def usage(prog: str) -> str:
    return (
        f'Usage: {prog} [--unknowns [FILE]] '
        f'[--output OUTPUT.tsv] [--reviewed-unknowns FILE] [--merchants FILE] '
        f'[--account-normal-direction debit|credit] '
        f'--balancing-account ACCT INPUT.csv'
    )


def main(argv: List[str]) -> int:
    if len(argv) >= 2 and argv[1] in {'-h', '--help'}:
        print(usage(Path(argv[0]).name), file=sys.stderr)
        return 0
    if len(argv) < 2:
        print(usage(Path(argv[0]).name), file=sys.stderr)
        return 2

    output_path = DEFAULT_OUTPUT
    unknowns_path = DEFAULT_UNKNOWNS
    reviewed_unknowns_path: Optional[Path] = None
    csv_path: Optional[Path] = None
    write_unknowns = False
    balancing_account = DEFAULT_BALANCING_ACCOUNT
    account_normal_direction = DEFAULT_ACCOUNT_NORMAL_DIRECTION
    merchants_path = DEFAULT_MERCHANTS

    args = argv[1:]
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == '--output':
            i += 1
            if i >= len(args):
                print('--output requires a file path', file=sys.stderr)
                return 2
            output_path = Path(args[i])
        elif arg == '--unknowns':
            write_unknowns = True
            if i + 1 < len(args) and not args[i + 1].startswith('--'):
                unknowns_path = Path(args[i + 1])
                i += 1
        elif arg == '--reviewed-unknowns':
            i += 1
            if i >= len(args):
                print('--reviewed-unknowns requires a file path', file=sys.stderr)
                return 2
            reviewed_unknowns_path = Path(args[i])
        elif arg == '--merchants':
            i += 1
            if i >= len(args):
                print('--merchants requires a file path', file=sys.stderr)
                return 2
            merchants_path = Path(args[i])
        elif arg == '--balancing-account':
            i += 1
            if i >= len(args):
                print('--balancing-account requires an account code', file=sys.stderr)
                return 2
            balancing_account = args[i]
        elif arg == '--account-normal-direction':
            i += 1
            if i >= len(args):
                print('--account-normal-direction requires debit or credit', file=sys.stderr)
                return 2
            account_normal_direction = args[i].lower()
            if account_normal_direction not in {'debit', 'credit'}:
                print('--account-normal-direction must be debit or credit', file=sys.stderr)
                return 2
        else:
            csv_path = Path(arg)
        i += 1

    if csv_path is None:
        print('No transaction CSV supplied', file=sys.stderr)
        return 2
    if not csv_path.exists():
        print(f'File not found: {csv_path}', file=sys.stderr)
        return 2

    reviewed_by_key = {}
    persistent_entries: List[EnrichedCategory] = []
    if reviewed_unknowns_path is not None:
        if not reviewed_unknowns_path.exists():
            print(f'File not found: {reviewed_unknowns_path}', file=sys.stderr)
            return 2
        for row in read_tsv_rows(reviewed_unknowns_path):
            normalized_row = {str(k).lstrip('\ufeff'): v for k, v in row.items()}
            txn_key = (normalized_row.get('txn_key') or '').strip()
            merchant = (normalized_row.get('merchant') or normalized_row.get('Merchant') or '').strip()
            account_code = (normalized_row.get('account_code') or normalized_row.get('Account Code') or '').strip()
            description = (normalized_row.get('description') or normalized_row.get('Description') or '').strip()
            learning_mode = (normalized_row.get('learning_mode') or normalized_row.get('learning mode') or '').strip().lower()
            notes = (normalized_row.get('notes') or normalized_row.get('Notes') or '').strip()
            if txn_key and account_code and description:
                reviewed_by_key[txn_key] = {
                    'merchant': merchant,
                    'account_code': account_code,
                    'description': description,
                    'learning_mode': learning_mode,
                    'notes': notes,
                }
                if learning_mode == 'persistent' and merchant:
                    persistent_entries.append(EnrichedCategory(
                        merchant=merchant,
                        account_code=account_code,
                        description=description,
                        notes=notes,
                    ))
        if persistent_entries:
            added = append_merchant_entries(persistent_entries, merchants_path)
            print(f'Updated {added} merchant rows in {merchants_path}')

    mappings = load_mappings(merchants_path)
    transactions = read_transactions(csv_path)
    classified = classify_transactions(transactions, mappings)

    if reviewed_by_key:
        updated_classified: List[ClassifiedTransaction] = []
        for item in classified:
            tx = item.transaction
            reviewed = reviewed_by_key.get(tx.txn_key)
            if reviewed is not None:
                updated_classified.append(ClassifiedTransaction(
                    transaction=tx,
                    account_code=reviewed['account_code'],
                    description=reviewed['description'],
                    matched_merchant=reviewed['merchant'] or item.matched_merchant,
                ))
            else:
                updated_classified.append(item)
        classified = updated_classified

    if write_unknowns:
        unknown_lines = render_unknowns(classified)
        if len(unknown_lines) == 1:
            print('The transaction CSV does not contain any unknown entries.')
            return 0
        write_text(unknowns_path, unknown_lines)
        print(f'Wrote unknowns report to {unknowns_path}')
        return 0

    journal_lines = render_journal_lines(classified, balancing_account=balancing_account, account_normal_direction=account_normal_direction)
    write_text(output_path, journal_lines)
    print(f'Wrote journal lines to {output_path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
