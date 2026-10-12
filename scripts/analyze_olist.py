"""Local Olist analysis runner (no database or deployed services needed)."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'dashboard'))
from historical_data import download_dataset, read_dataset, build_sales, summarize, group_sales


def main():
    parser = argparse.ArgumentParser(description='Calculate actual historical Olist sales metrics')
    parser.add_argument('--data-dir', type=Path, default=Path('data/olist'), help='Folder of original Olist CSV files')
    parser.add_argument('--download', action='store_true', help='Download original CSVs from a public Olist mirror')
    parser.add_argument('--output-dir', type=Path, default=Path('data/processed'))
    args = parser.parse_args()
    if args.download:
        download_dataset(args.data_dir)
    sales, audit = build_sales(read_dataset(args.data_dir))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    group_sales(sales, ['seller_id', 'seller_city', 'seller_state']).to_csv(args.output_dir / 'seller_ranking.csv', index=False)
    group_sales(sales, ['product_id', 'category']).to_csv(args.output_dir / 'product_ranking.csv', index=False)
    group_sales(sales, ['month']).sort_values('month').to_csv(args.output_dir / 'monthly_sales.csv', index=False)
    (args.output_dir / 'audit.json').write_text(json.dumps(audit, indent=2), encoding='utf-8')
    print(json.dumps({'metrics': summarize(sales), 'audit': audit}, indent=2))


if __name__ == '__main__':
    main()