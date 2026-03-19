#!/usr/bin/env python3
"""
ROAS D7 Optimization Tool

Analyzes site_performance (internal) and DT_DX (client) files to generate
optimization recommendations based on a target ROAS D7 goal.

Campaign Actions:
- PAUSE: Campaigns significantly below target ROAS
- REDUCE: Campaigns moderately below target ROAS
- MAINTAIN: Campaigns near target ROAS
- SCALE: Campaigns exceeding target ROAS with sufficient spend
"""

import argparse
import csv
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional


# Configuration
DEFAULT_ROAS_GOAL = 2.18  # D7 ROAS target as percentage
CLIENT_ROAS_COLUMN = "Domino Dreams Marketing Campaigns Daily Metrics Full ROAS D7"

# Thresholds for optimization decisions
PAUSE_THRESHOLD = 0.5    # Below 50% of goal -> PAUSE
REDUCE_THRESHOLD = 0.8   # Below 80% of goal -> REDUCE
SCALE_THRESHOLD = 1.2    # Above 120% of goal -> SCALE
MIN_SPEND_FOR_SCALE = 100  # Minimum spend to consider scaling


@dataclass
class Campaign:
    """Represents a campaign with its performance metrics."""
    name: str
    source: str  # 'internal' or 'client'
    spend: float
    revenue: float
    roas_d7: float
    installs: Optional[int] = None
    cpi: Optional[float] = None
    country: Optional[str] = None
    platform: Optional[str] = None


@dataclass
class Recommendation:
    """Optimization recommendation for a campaign."""
    campaign: Campaign
    action: str  # PAUSE, REDUCE, MAINTAIN, SCALE
    roas_vs_goal: float  # Ratio of actual ROAS to goal
    reason: str
    priority: int  # 1 = highest priority


def normalize_column_name(col: str) -> str:
    """Normalize column names for matching."""
    return col.lower().strip().replace(" ", "_").replace("-", "_")


def find_column(headers: list[str], candidates: list[str]) -> Optional[str]:
    """Find a column name from a list of possible candidates."""
    normalized_headers = {normalize_column_name(h): h for h in headers}
    for candidate in candidates:
        norm_candidate = normalize_column_name(candidate)
        if norm_candidate in normalized_headers:
            return normalized_headers[norm_candidate]
    return None


def parse_numeric(value: str) -> float:
    """Parse a numeric value, handling currency symbols and percentages."""
    if not value or value.strip() in ('', '-', 'N/A', 'null'):
        return 0.0
    
    cleaned = value.strip()
    cleaned = cleaned.replace('$', '').replace(',', '').replace('%', '')
    
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def load_csv_file(filepath: str) -> tuple[list[str], list[dict]]:
    """Load a CSV file and return headers and rows as dicts."""
    rows = []
    headers = []
    
    with open(filepath, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        for row in reader:
            rows.append(row)
    
    return headers, rows


def load_site_performance(filepath: str) -> list[Campaign]:
    """Load campaigns from the internal site_performance file."""
    campaigns = []
    headers, rows = load_csv_file(filepath)
    
    campaign_col = find_column(headers, ['campaign', 'campaign_name', 'name', 'campaign name', 'ad_campaign'])
    spend_col = find_column(headers, ['spend', 'cost', 'total_spend', 'media_cost', 'total spend'])
    revenue_col = find_column(headers, ['revenue', 'total_revenue', 'gross_revenue', 'total revenue'])
    roas_col = find_column(headers, ['roas_d7', 'roas d7', 'd7_roas', 'roas', 'd7 roas'])
    installs_col = find_column(headers, ['installs', 'install', 'total_installs', 'conversions'])
    cpi_col = find_column(headers, ['cpi', 'cost_per_install', 'cost per install'])
    country_col = find_column(headers, ['country', 'geo', 'region', 'country_code'])
    platform_col = find_column(headers, ['platform', 'os', 'device_type'])
    
    for row in rows:
        campaign_name = row.get(campaign_col, 'Unknown') if campaign_col else 'Unknown'
        spend = parse_numeric(row.get(spend_col, '0')) if spend_col else 0
        revenue = parse_numeric(row.get(revenue_col, '0')) if revenue_col else 0
        
        if roas_col and row.get(roas_col):
            roas_d7 = parse_numeric(row.get(roas_col, '0'))
        elif spend > 0:
            roas_d7 = (revenue / spend) * 100
        else:
            roas_d7 = 0
        
        installs = int(parse_numeric(row.get(installs_col, '0'))) if installs_col else None
        cpi = parse_numeric(row.get(cpi_col, '0')) if cpi_col else None
        country = row.get(country_col) if country_col else None
        platform = row.get(platform_col) if platform_col else None
        
        if campaign_name and campaign_name != 'Unknown':
            campaigns.append(Campaign(
                name=campaign_name,
                source='internal',
                spend=spend,
                revenue=revenue,
                roas_d7=roas_d7,
                installs=installs,
                cpi=cpi,
                country=country,
                platform=platform,
            ))
    
    return campaigns


def load_dt_dx_client(filepath: str) -> list[Campaign]:
    """Load campaigns from the DT_DX client file."""
    campaigns = []
    headers, rows = load_csv_file(filepath)
    
    campaign_col = find_column(headers, ['campaign', 'campaign_name', 'name', 'campaign name', 'ad_campaign'])
    spend_col = find_column(headers, ['spend', 'cost', 'total_spend', 'media_cost', 'total spend'])
    revenue_col = find_column(headers, ['revenue', 'total_revenue', 'gross_revenue', 'total revenue'])
    
    roas_col = find_column(headers, [
        CLIENT_ROAS_COLUMN,
        'domino_dreams_marketing_campaigns_daily_metrics_full_roas_d7',
        'roas_d7', 'roas d7', 'd7_roas', 'roas', 'd7 roas',
        'full_roas_d7', 'full roas d7'
    ])
    
    installs_col = find_column(headers, ['installs', 'install', 'total_installs', 'conversions'])
    country_col = find_column(headers, ['country', 'geo', 'region', 'country_code'])
    platform_col = find_column(headers, ['platform', 'os', 'device_type'])
    
    for row in rows:
        campaign_name = row.get(campaign_col, 'Unknown') if campaign_col else 'Unknown'
        spend = parse_numeric(row.get(spend_col, '0')) if spend_col else 0
        revenue = parse_numeric(row.get(revenue_col, '0')) if revenue_col else 0
        
        if roas_col and row.get(roas_col):
            roas_d7 = parse_numeric(row.get(roas_col, '0'))
        elif spend > 0:
            roas_d7 = (revenue / spend) * 100
        else:
            roas_d7 = 0
        
        installs = int(parse_numeric(row.get(installs_col, '0'))) if installs_col else None
        country = row.get(country_col) if country_col else None
        platform = row.get(platform_col) if platform_col else None
        
        if campaign_name and campaign_name != 'Unknown':
            campaigns.append(Campaign(
                name=campaign_name,
                source='client',
                spend=spend,
                revenue=revenue,
                roas_d7=roas_d7,
                installs=installs,
                country=country,
                platform=platform,
            ))
    
    return campaigns


def analyze_campaign(campaign: Campaign, roas_goal: float) -> Recommendation:
    """Analyze a single campaign and generate a recommendation."""
    
    if campaign.roas_d7 <= 0 or campaign.spend <= 0:
        return Recommendation(
            campaign=campaign,
            action="PAUSE",
            roas_vs_goal=0,
            reason="No ROAS data or no spend recorded",
            priority=1
        )
    
    roas_ratio = campaign.roas_d7 / roas_goal
    
    if roas_ratio < PAUSE_THRESHOLD:
        action = "PAUSE"
        priority = 1
        reason = f"ROAS {campaign.roas_d7:.2f}% is severely below goal ({roas_ratio:.0%} of target)"
    elif roas_ratio < REDUCE_THRESHOLD:
        action = "REDUCE"
        priority = 2
        reason = f"ROAS {campaign.roas_d7:.2f}% is below goal ({roas_ratio:.0%} of target)"
    elif roas_ratio >= SCALE_THRESHOLD and campaign.spend >= MIN_SPEND_FOR_SCALE:
        action = "SCALE"
        priority = 3
        reason = f"ROAS {campaign.roas_d7:.2f}% exceeds goal ({roas_ratio:.0%} of target) with ${campaign.spend:.2f} spend"
    elif roas_ratio >= SCALE_THRESHOLD:
        action = "MAINTAIN"
        priority = 4
        reason = f"ROAS {campaign.roas_d7:.2f}% exceeds goal but spend ${campaign.spend:.2f} is below threshold for scaling"
    else:
        action = "MAINTAIN"
        priority = 4
        reason = f"ROAS {campaign.roas_d7:.2f}% is near goal ({roas_ratio:.0%} of target)"
    
    return Recommendation(
        campaign=campaign,
        action=action,
        roas_vs_goal=roas_ratio,
        reason=reason,
        priority=priority
    )


def generate_recommendations(
    campaigns: list[Campaign], 
    roas_goal: float
) -> list[Recommendation]:
    """Generate optimization recommendations for all campaigns."""
    recommendations = []
    
    for campaign in campaigns:
        rec = analyze_campaign(campaign, roas_goal)
        recommendations.append(rec)
    
    recommendations.sort(key=lambda r: (r.priority, -r.campaign.spend))
    
    return recommendations


def print_summary(
    recommendations: list[Recommendation],
    roas_goal: float,
    internal_file: Optional[str],
    client_file: Optional[str]
):
    """Print a formatted summary of recommendations."""
    
    print("\n" + "=" * 80)
    print(f"  ROAS D7 OPTIMIZATION REPORT")
    print(f"  Target ROAS Goal: {roas_goal:.2f}%")
    print(f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    
    if internal_file:
        print(f"  Internal Data: {internal_file}")
    if client_file:
        print(f"  Client Data: {client_file}")
    print()
    
    action_counts = {'PAUSE': 0, 'REDUCE': 0, 'MAINTAIN': 0, 'SCALE': 0}
    total_spend_by_action = {'PAUSE': 0, 'REDUCE': 0, 'MAINTAIN': 0, 'SCALE': 0}
    
    for rec in recommendations:
        action_counts[rec.action] += 1
        total_spend_by_action[rec.action] += rec.campaign.spend
    
    print("  SUMMARY")
    print("  " + "-" * 76)
    print(f"  {'Action':<12} {'Campaigns':>10} {'Total Spend':>15}")
    print("  " + "-" * 76)
    for action in ['PAUSE', 'REDUCE', 'MAINTAIN', 'SCALE']:
        print(f"  {action:<12} {action_counts[action]:>10} ${total_spend_by_action[action]:>14,.2f}")
    print("  " + "-" * 76)
    print(f"  {'TOTAL':<12} {sum(action_counts.values()):>10} ${sum(total_spend_by_action.values()):>14,.2f}")
    print()
    
    for action in ['PAUSE', 'REDUCE', 'SCALE', 'MAINTAIN']:
        action_recs = [r for r in recommendations if r.action == action]
        if not action_recs:
            continue
        
        emoji = {'PAUSE': '🛑', 'REDUCE': '⚠️', 'MAINTAIN': '✓', 'SCALE': '🚀'}.get(action, '')
        print(f"\n  {emoji} {action} RECOMMENDATIONS ({len(action_recs)} campaigns)")
        print("  " + "-" * 76)
        print(f"  {'Campaign':<35} {'Source':<10} {'Spend':>12} {'ROAS D7':>10} {'vs Goal':>10}")
        print("  " + "-" * 76)
        
        for rec in action_recs[:15]:
            campaign_name = rec.campaign.name[:33] + '..' if len(rec.campaign.name) > 35 else rec.campaign.name
            print(f"  {campaign_name:<35} {rec.campaign.source:<10} ${rec.campaign.spend:>10,.2f} {rec.campaign.roas_d7:>9.2f}% {rec.roas_vs_goal:>9.0%}")
        
        if len(action_recs) > 15:
            print(f"  ... and {len(action_recs) - 15} more campaigns")
    
    print("\n" + "=" * 80)
    
    pause_recs = [r for r in recommendations if r.action == 'PAUSE']
    scale_recs = [r for r in recommendations if r.action == 'SCALE']
    
    print("\n  KEY ACTIONS:")
    print()
    
    if pause_recs:
        top_pause = sorted(pause_recs, key=lambda r: r.campaign.spend, reverse=True)[:5]
        print("  🛑 IMMEDIATE PAUSE (High-spend underperformers):")
        for rec in top_pause:
            print(f"     • {rec.campaign.name}: ROAS {rec.campaign.roas_d7:.2f}% (${rec.campaign.spend:,.2f} spend)")
    
    print()
    
    if scale_recs:
        top_scale = sorted(scale_recs, key=lambda r: r.roas_vs_goal, reverse=True)[:5]
        print("  🚀 RECOMMENDED SCALING (Top performers):")
        for rec in top_scale:
            print(f"     • {rec.campaign.name}: ROAS {rec.campaign.roas_d7:.2f}% ({rec.roas_vs_goal:.0%} of goal)")
    
    print("\n" + "=" * 80 + "\n")


def export_csv(recommendations: list[Recommendation], output_path: str):
    """Export recommendations to a CSV file."""
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([
            'Campaign', 'Source', 'Action', 'Priority', 'Spend', 'Revenue',
            'ROAS_D7', 'ROAS_vs_Goal', 'Reason'
        ])
        
        for rec in recommendations:
            writer.writerow([
                rec.campaign.name,
                rec.campaign.source,
                rec.action,
                rec.priority,
                f'{rec.campaign.spend:.2f}',
                f'{rec.campaign.revenue:.2f}',
                f'{rec.campaign.roas_d7:.2f}%',
                f'{rec.roas_vs_goal:.0%}',
                rec.reason
            ])
    
    print(f"  Recommendations exported to: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="ROAS D7 Optimization Tool - Generate campaign optimization recommendations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Analyze both internal and client files
  python roas_optimizer.py --internal site_performance.csv --client DT_DX.csv --goal 2.18
  
  # Analyze only client file
  python roas_optimizer.py --client DT_DX.csv --goal 2.18
  
  # Export recommendations to CSV
  python roas_optimizer.py --internal site_performance.csv --client DT_DX.csv --goal 2.18 --export recommendations.csv

Notes:
  - site_performance: Internal performance data file
  - DT_DX: Client file with "Domino Dreams Marketing Campaigns Daily Metrics Full ROAS D7" column
  - ROAS goal is expressed as a percentage (e.g., 2.18 = 2.18%)
        """
    )
    
    parser.add_argument('--internal', '-i', help='Path to internal site_performance CSV file')
    parser.add_argument('--client', '-c', help='Path to client DT_DX CSV file')
    parser.add_argument('--goal', '-g', type=float, default=DEFAULT_ROAS_GOAL,
                        help=f'Target ROAS D7 goal as percentage (default: {DEFAULT_ROAS_GOAL})')
    parser.add_argument('--export', '-e', help='Export recommendations to CSV file')
    parser.add_argument('--verbose', '-v', action='store_true', help='Show verbose output')
    
    args = parser.parse_args()
    
    if not args.internal and not args.client:
        parser.print_help()
        print("\n[ERROR] Please provide at least one data file (--internal or --client)")
        sys.exit(1)
    
    all_campaigns: list[Campaign] = []
    
    if args.internal:
        if not os.path.isfile(args.internal):
            print(f"[ERROR] Internal file not found: {args.internal}")
            sys.exit(1)
        
        print(f"  Loading internal data from: {args.internal}")
        internal_campaigns = load_site_performance(args.internal)
        print(f"  Loaded {len(internal_campaigns)} campaigns from internal file")
        all_campaigns.extend(internal_campaigns)
    
    if args.client:
        if not os.path.isfile(args.client):
            print(f"[ERROR] Client file not found: {args.client}")
            sys.exit(1)
        
        print(f"  Loading client data from: {args.client}")
        client_campaigns = load_dt_dx_client(args.client)
        print(f"  Loaded {len(client_campaigns)} campaigns from client file")
        all_campaigns.extend(client_campaigns)
    
    if not all_campaigns:
        print("[ERROR] No campaigns found in the provided files")
        sys.exit(1)
    
    print(f"\n  Analyzing {len(all_campaigns)} total campaigns against ROAS goal: {args.goal}%")
    
    recommendations = generate_recommendations(all_campaigns, args.goal)
    
    print_summary(
        recommendations,
        args.goal,
        args.internal,
        args.client
    )
    
    if args.export:
        export_csv(recommendations, args.export)


if __name__ == "__main__":
    main()
