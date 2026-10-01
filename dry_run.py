from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from adobe_parser import parse_adobe_csv
from ppt_report import build_ppt_report
from traffic_analyzer import (
    build_table_rows,
    channel_share_line,
    cta_summary_line,
    fallback_headline,
    format_compact,
    format_ratio,
)
from url_utils import breadcrumb_label, report_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('csv', nargs='?', default='/mnt/data/今週-explore-上位Page - P6 WEB - Japan - Oct 1, 2026.csv')
    parser.add_argument('--out', default='/mnt/data/page-traffic-report-dry-run-v2.pptx')
    parser.add_argument('--as-of', default='2026-10-01')
    args = parser.parse_args()

    csv_path = Path(args.csv)
    out_path = Path(args.out)
    anchor = date.fromisoformat(args.as_of)
    parsed = parse_adobe_csv(csv_path.read_bytes(), top_n=None, as_of_date=anchor)
    start = date.fromisoformat(parsed['last_week_start'])
    end = date.fromisoformat(parsed['last_week_end'])
    period = f'{start.year}/{start.month}/{start.day}~{end.year}/{end.month}/{end.day}'

    pages = []
    for page in parsed['pages']:
        prev = page['previous']['entry'].get('Total', 0)
        curr = page['current']['entry'].get('Total', 0)
        pages.append({
            'url': page['url'],
            'meta_title': '（実行時にページソースの <title> から自動取得）',
            'report_path': report_path(page['url']),
            'breadcrumb': breadcrumb_label(page['url']),
            'period_label': period,
            'total_current_compact': format_compact(curr),
            'total_ratio_label': format_ratio(curr, prev),
            'headline_comment': fallback_headline(page),
            'share_line': channel_share_line(page),
            'secondary_line': cta_summary_line(page),
            'table_rows': build_table_rows(page),
            'gsc_queries': [],
            'screenshot_bytes': None,
        })
    out_path.write_bytes(build_ppt_report(pages))
    print(out_path)


if __name__ == '__main__':
    main()
