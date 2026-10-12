"""Read JoinQuant's ragged position export without changing any run artifacts."""
import argparse
import csv
import io
import json
from pathlib import Path
import re
import zipfile

import pandas as pd


def analyze(archive, run_directory, output, initial_cash=500000):
    with zipfile.ZipFile(archive) as bundle:
        raw = bundle.read('position.csv')
    try:
        text = raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        text = raw.decode('gb18030')
    rows = list(csv.reader(io.StringIO(text)))[1:]
    daily, positions = {}, []
    for row in rows:
        # Cash rows have 16 columns; invested rows additionally contain total NAV.
        if len(row) not in (16, 17):
            raise ValueError(f'Unexpected row width: {len(row)}')
        date = row[0]
        day = daily.setdefault(date, {'cash': 0.0, 'positions_value': 0.0})
        value = float(row[7])
        if row[2] == 'Cash':
            day['cash'] += value
        else:
            day['positions_value'] += value
            match = re.search(r'\(([^)]+)\)', row[2])
            if not match:
                raise ValueError('Missing security code')
            positions.append({'date': date, 'code': match[1],
                              'amount': int(re.sub(r'\D', '', row[4])),
                              'price': float(row[6]), 'value': value})
            if len(row) == 17:
                day['exported_total_value'] = float(row[15])
    own = pd.read_csv(run_directory / 'daily_records.csv')
    own['date'] = own.date.str[:10]
    equity = pd.DataFrame([dict(date=date, **values) for date, values in sorted(daily.items())])
    equity['total_value'] = equity.cash + equity.positions_value
    if not ((equity.total_value - equity.exported_total_value).dropna().abs() <= .011).all():
        raise ValueError('Position totals disagree with exported NAV')
    if set(equity.date) != set(own.date):
        raise ValueError('Trading dates differ; benchmark cannot be aligned')
    if initial_cash <= 0:
        raise ValueError('Initial cash must be positive')
    equity['returns_pct'] = (equity.total_value / initial_cash - 1) * 100
    equity = equity.merge(own[['date', 'benchmark_returns_pct']], on='date', validate='one_to_one')
    output.mkdir(parents=True, exist_ok=True)
    equity.to_csv(output / 'daily_records.csv', index=False)
    # Empty trades: trade statistics must be supplied separately from the trade log.
    (output / 'trades.csv').write_text('direction\n', encoding='utf-8')
    jq = pd.DataFrame(positions)
    local = pd.read_csv(run_directory / 'daily_positions.csv')
    local['date'] = local.date.str[:10]
    joined = jq.merge(local[['date', 'code', 'amount', 'price']], on=['date', 'code'],
                      how='outer', suffixes=('_jq', '_local'), indicator=True)
    mismatch = joined[(joined['_merge'] != 'both') |
                      ((joined.price_jq - joined.price_local).abs() > 1e-8)]
    joined.to_csv(output / 'position_comparison.csv', index=False)
    result = {'days': len(equity), 'invested_rows': len(jq),
              'final_equity': float(equity.total_value.iloc[-1]),
              'return_pct': float(equity.returns_pct.iloc[-1]),
              'price_or_security_difference_rows': len(mismatch),
              'first_price_or_security_differences': json.loads(mismatch.head(8).drop(columns='_merge').to_json(orient='records')),
              'benchmark_source': 'Local run benchmark, not a JoinQuant benchmark export'}
    (output / 'summary.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('archive', type=Path)
    parser.add_argument('run_directory', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--initial-cash', type=float, default=500000)
    args = parser.parse_args()
    print(json.dumps(analyze(args.archive, args.run_directory, args.output, args.initial_cash)))
