#!/usr/bin/env python3
"""
ROAS D7 Optimization Suggestions Tool

Analyzes site_performance (internal) and DT_DX (client) data to provide
optimization recommendations based on the D7 ROAS goal.

Configuration:
- ROAS D7 Goal: 2.18%
- Internal file: site_performance (CSV/Excel)
- Client file: DT_DX (CSV/Excel)
- Client ROAS column: "Domino Dreams Marketing Campaigns Daily Metrics Full ROAS D7"
"""

import argparse
import os
import sys
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
import numpy as np


# ── Configuration ─────────────────────────────────────────────────────────────

ROAS_D7_GOAL = 0.0218  # 2.18% expressed as decimal
ROAS_D7_GOAL_PERCENT = 2.18

# Column name in client file (DT_DX)
CLIENT_ROAS_COLUMN = "Domino Dreams Marketing Campaigns Daily Metrics Full ROAS D7"

# Common column name variations to search for
ROAS_COLUMN_PATTERNS = [
    "roas",
    "roas_d7",
    "roas d7",
    "d7 roas",
    "full roas d7",
    CLIENT_ROAS_COLUMN.lower(),
]

SPEND_COLUMN_PATTERNS = ["spend", "cost", "media_cost", "media cost", "ad_spend"]
REVENUE_COLUMN_PATTERNS = ["revenue", "d7_revenue", "d7 revenue", "rev_d7"]
CAMPAIGN_COLUMN_PATTERNS = ["campaign", "campaign_name", "campaign name", "campaign_id"]
SITE_COLUMN_PATTERNS = ["site", "site_id", "site id", "publisher", "source", "media_source"]
DATE_COLUMN_PATTERNS = ["date", "day", "cohort_date", "install_date"]


# ── Helper Functions ──────────────────────────────────────────────────────────


def find_column(df: pd.DataFrame, patterns: list[str], required: bool = True) -> Optional[str]:
    """Find a column matching any of the given patterns (case-insensitive)."""
    df_cols_lower = {col.lower(): col for col in df.columns}
    
    for pattern in patterns:
        pattern_lower = pattern.lower()
        if pattern_lower in df_cols_lower:
            return df_cols_lower[pattern_lower]
        for col_lower, col_original in df_cols_lower.items():
            if pattern_lower in col_lower:
                return col_original
    
    if required:
        raise ValueError(f"Could not find column matching patterns: {patterns}")
    return None


def load_data(filepath: str) -> pd.DataFrame:
    """Load data from CSV or Excel file."""
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"File not found: {filepath}")
    
    ext = os.path.splitext(filepath)[1].lower()
    
    if ext == ".csv":
        return pd.read_csv(filepath)
    elif ext in [".xlsx", ".xls"]:
        return pd.read_excel(filepath)
    else:
        try:
            return pd.read_csv(filepath)
        except Exception:
            return pd.read_excel(filepath)


def calculate_roas(revenue: float, spend: float) -> float:
    """Calculate ROAS as a percentage."""
    if spend == 0 or pd.isna(spend):
        return 0.0
    return (revenue / spend) * 100


def format_currency(value: float) -> str:
    """Format value as currency."""
    return f"${value:,.2f}"


def format_percent(value: float) -> str:
    """Format value as percentage."""
    return f"{value:.2f}%"


def get_performance_tier(roas: float, goal: float = ROAS_D7_GOAL_PERCENT) -> str:
    """Categorize performance relative to goal."""
    if roas >= goal * 1.2:
        return "Excellent"
    elif roas >= goal:
        return "On Target"
    elif roas >= goal * 0.8:
        return "Below Target"
    elif roas >= goal * 0.5:
        return "Underperforming"
    else:
        return "Critical"


# ── Analysis Functions ────────────────────────────────────────────────────────


def analyze_client_data(df: pd.DataFrame) -> dict:
    """Analyze client (DT_DX) data for ROAS performance."""
    roas_col = find_column(df, [CLIENT_ROAS_COLUMN] + ROAS_COLUMN_PATTERNS)
    campaign_col = find_column(df, CAMPAIGN_COLUMN_PATTERNS, required=False)
    site_col = find_column(df, SITE_COLUMN_PATTERNS, required=False)
    spend_col = find_column(df, SPEND_COLUMN_PATTERNS, required=False)
    date_col = find_column(df, DATE_COLUMN_PATTERNS, required=False)
    
    df_clean = df.copy()
    df_clean[roas_col] = pd.to_numeric(df_clean[roas_col], errors='coerce')
    df_clean = df_clean.dropna(subset=[roas_col])
    
    if roas_col and df_clean[roas_col].max() > 1:
        pass
    elif roas_col and df_clean[roas_col].max() <= 1:
        df_clean[roas_col] = df_clean[roas_col] * 100
    
    results = {
        "total_rows": len(df_clean),
        "roas_column": roas_col,
        "avg_roas": df_clean[roas_col].mean(),
        "median_roas": df_clean[roas_col].median(),
        "min_roas": df_clean[roas_col].min(),
        "max_roas": df_clean[roas_col].max(),
        "std_roas": df_clean[roas_col].std(),
        "above_goal_count": len(df_clean[df_clean[roas_col] >= ROAS_D7_GOAL_PERCENT]),
        "below_goal_count": len(df_clean[df_clean[roas_col] < ROAS_D7_GOAL_PERCENT]),
    }
    
    if campaign_col:
        campaign_perf = df_clean.groupby(campaign_col).agg({
            roas_col: ['mean', 'count']
        }).round(2)
        campaign_perf.columns = ['avg_roas', 'count']
        campaign_perf = campaign_perf.sort_values('avg_roas', ascending=False)
        results["campaign_performance"] = campaign_perf.reset_index()
    
    if site_col:
        site_perf = df_clean.groupby(site_col).agg({
            roas_col: ['mean', 'count']
        }).round(2)
        site_perf.columns = ['avg_roas', 'count']
        site_perf = site_perf.sort_values('avg_roas', ascending=False)
        results["site_performance"] = site_perf.reset_index()
    
    return results


def analyze_internal_data(df: pd.DataFrame) -> dict:
    """Analyze internal site_performance data."""
    site_col = find_column(df, SITE_COLUMN_PATTERNS, required=False)
    spend_col = find_column(df, SPEND_COLUMN_PATTERNS, required=False)
    revenue_col = find_column(df, REVENUE_COLUMN_PATTERNS, required=False)
    roas_col = find_column(df, ROAS_COLUMN_PATTERNS, required=False)
    date_col = find_column(df, DATE_COLUMN_PATTERNS, required=False)
    
    df_clean = df.copy()
    
    if roas_col:
        df_clean[roas_col] = pd.to_numeric(df_clean[roas_col], errors='coerce')
        if df_clean[roas_col].max() <= 1:
            df_clean[roas_col] = df_clean[roas_col] * 100
    elif spend_col and revenue_col:
        df_clean[spend_col] = pd.to_numeric(df_clean[spend_col], errors='coerce')
        df_clean[revenue_col] = pd.to_numeric(df_clean[revenue_col], errors='coerce')
        df_clean['calculated_roas'] = (df_clean[revenue_col] / df_clean[spend_col]) * 100
        roas_col = 'calculated_roas'
    
    results = {
        "total_rows": len(df_clean),
        "columns_found": {
            "site": site_col,
            "spend": spend_col,
            "revenue": revenue_col,
            "roas": roas_col,
            "date": date_col,
        }
    }
    
    if roas_col:
        df_valid = df_clean.dropna(subset=[roas_col])
        results.update({
            "avg_roas": df_valid[roas_col].mean(),
            "median_roas": df_valid[roas_col].median(),
            "min_roas": df_valid[roas_col].min(),
            "max_roas": df_valid[roas_col].max(),
        })
        
        if site_col:
            site_stats = df_valid.groupby(site_col).agg({
                roas_col: ['mean', 'std', 'count'],
            }).round(2)
            site_stats.columns = ['avg_roas', 'std_roas', 'count']
            
            if spend_col:
                spend_by_site = df_valid.groupby(site_col)[spend_col].sum()
                site_stats['total_spend'] = spend_by_site
            
            site_stats = site_stats.sort_values('avg_roas', ascending=False)
            results["site_breakdown"] = site_stats.reset_index()
    
    if spend_col:
        results["total_spend"] = df_clean[spend_col].sum()
    
    if revenue_col:
        results["total_revenue"] = df_clean[revenue_col].sum()
    
    return results


def generate_optimization_suggestions(
    client_analysis: dict,
    internal_analysis: Optional[dict] = None
) -> list[dict]:
    """Generate actionable optimization suggestions based on analysis."""
    suggestions = []
    
    avg_roas = client_analysis.get("avg_roas", 0)
    goal_diff = avg_roas - ROAS_D7_GOAL_PERCENT
    goal_diff_pct = (goal_diff / ROAS_D7_GOAL_PERCENT) * 100 if ROAS_D7_GOAL_PERCENT else 0
    
    if avg_roas < ROAS_D7_GOAL_PERCENT:
        urgency = "HIGH" if avg_roas < ROAS_D7_GOAL_PERCENT * 0.7 else "MEDIUM"
        suggestions.append({
            "category": "Overall Performance",
            "urgency": urgency,
            "finding": f"Average D7 ROAS ({format_percent(avg_roas)}) is below goal ({format_percent(ROAS_D7_GOAL_PERCENT)})",
            "gap": f"{format_percent(abs(goal_diff))} below target ({abs(goal_diff_pct):.1f}% gap)",
            "recommendation": "Review campaign mix and site allocation to improve overall ROAS",
        })
    else:
        suggestions.append({
            "category": "Overall Performance",
            "urgency": "LOW",
            "finding": f"Average D7 ROAS ({format_percent(avg_roas)}) meets or exceeds goal ({format_percent(ROAS_D7_GOAL_PERCENT)})",
            "gap": f"{format_percent(goal_diff)} above target",
            "recommendation": "Continue monitoring; consider scaling high-performing segments",
        })
    
    if "site_performance" in client_analysis:
        site_df = client_analysis["site_performance"]
        
        underperforming = site_df[site_df['avg_roas'] < ROAS_D7_GOAL_PERCENT * 0.8]
        if len(underperforming) > 0:
            sites_list = underperforming.iloc[:5][site_df.columns[0]].tolist()
            suggestions.append({
                "category": "Site Optimization",
                "urgency": "HIGH",
                "finding": f"{len(underperforming)} sites performing below 80% of ROAS goal",
                "sites": sites_list,
                "recommendation": "Consider reducing spend or pausing these underperforming sites",
            })
        
        top_performers = site_df[site_df['avg_roas'] >= ROAS_D7_GOAL_PERCENT * 1.2]
        if len(top_performers) > 0:
            sites_list = top_performers.iloc[:5][site_df.columns[0]].tolist()
            suggestions.append({
                "category": "Site Scaling",
                "urgency": "MEDIUM",
                "finding": f"{len(top_performers)} sites performing 20%+ above ROAS goal",
                "sites": sites_list,
                "recommendation": "Increase budget allocation to these high-performing sites",
            })
    
    if "campaign_performance" in client_analysis:
        camp_df = client_analysis["campaign_performance"]
        
        underperforming = camp_df[camp_df['avg_roas'] < ROAS_D7_GOAL_PERCENT * 0.8]
        if len(underperforming) > 0:
            camps_list = underperforming.iloc[:5][camp_df.columns[0]].tolist()
            suggestions.append({
                "category": "Campaign Optimization",
                "urgency": "HIGH",
                "finding": f"{len(underperforming)} campaigns performing below 80% of ROAS goal",
                "campaigns": camps_list,
                "recommendation": "Review targeting and creatives for underperforming campaigns",
            })
    
    below_count = client_analysis.get("below_goal_count", 0)
    total = client_analysis.get("total_rows", 1)
    below_pct = (below_count / total) * 100 if total else 0
    
    if below_pct > 50:
        suggestions.append({
            "category": "Portfolio Health",
            "urgency": "HIGH",
            "finding": f"{below_pct:.1f}% of entries are below ROAS goal",
            "recommendation": "Significant portion of spend is inefficient; comprehensive review needed",
        })
    
    std_roas = client_analysis.get("std_roas", 0)
    if std_roas > ROAS_D7_GOAL_PERCENT * 0.5:
        suggestions.append({
            "category": "Performance Variance",
            "urgency": "MEDIUM",
            "finding": f"High ROAS variance detected (std: {format_percent(std_roas)})",
            "recommendation": "Large performance spread suggests optimization opportunities; focus on reducing underperformers",
        })
    
    if internal_analysis:
        if "site_breakdown" in internal_analysis:
            int_site_df = internal_analysis["site_breakdown"]
            if 'total_spend' in int_site_df.columns:
                total_spend = int_site_df['total_spend'].sum()
                underperf_sites = int_site_df[int_site_df['avg_roas'] < ROAS_D7_GOAL_PERCENT]
                if len(underperf_sites) > 0:
                    wasted_spend = underperf_sites['total_spend'].sum()
                    wasted_pct = (wasted_spend / total_spend) * 100 if total_spend else 0
                    if wasted_pct > 20:
                        suggestions.append({
                            "category": "Spend Efficiency",
                            "urgency": "HIGH",
                            "finding": f"{format_currency(wasted_spend)} ({wasted_pct:.1f}%) spent on sites below ROAS goal",
                            "recommendation": "Reallocate budget from underperforming to high-performing sites",
                        })
    
    return suggestions


def generate_report(
    client_analysis: dict,
    internal_analysis: Optional[dict],
    suggestions: list[dict],
    output_format: str = "text"
) -> str:
    """Generate a formatted report."""
    lines = []
    
    lines.append("=" * 80)
    lines.append("ROAS D7 OPTIMIZATION REPORT")
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"Goal: {format_percent(ROAS_D7_GOAL_PERCENT)} D7 ROAS")
    lines.append("=" * 80)
    lines.append("")
    
    lines.append("─" * 40)
    lines.append("CLIENT DATA SUMMARY (DT_DX)")
    lines.append("─" * 40)
    lines.append(f"ROAS Column: {client_analysis.get('roas_column', 'N/A')}")
    lines.append(f"Total Entries: {client_analysis.get('total_rows', 0):,}")
    lines.append(f"Average D7 ROAS: {format_percent(client_analysis.get('avg_roas', 0))}")
    lines.append(f"Median D7 ROAS: {format_percent(client_analysis.get('median_roas', 0))}")
    lines.append(f"Min ROAS: {format_percent(client_analysis.get('min_roas', 0))}")
    lines.append(f"Max ROAS: {format_percent(client_analysis.get('max_roas', 0))}")
    lines.append(f"Entries Above Goal: {client_analysis.get('above_goal_count', 0):,}")
    lines.append(f"Entries Below Goal: {client_analysis.get('below_goal_count', 0):,}")
    
    avg_roas = client_analysis.get('avg_roas', 0)
    tier = get_performance_tier(avg_roas)
    status_icon = "✓" if avg_roas >= ROAS_D7_GOAL_PERCENT else "✗"
    lines.append(f"Status: {status_icon} {tier}")
    lines.append("")
    
    if internal_analysis:
        lines.append("─" * 40)
        lines.append("INTERNAL DATA SUMMARY (site_performance)")
        lines.append("─" * 40)
        lines.append(f"Total Entries: {internal_analysis.get('total_rows', 0):,}")
        if 'avg_roas' in internal_analysis:
            lines.append(f"Average ROAS: {format_percent(internal_analysis.get('avg_roas', 0))}")
        if 'total_spend' in internal_analysis:
            lines.append(f"Total Spend: {format_currency(internal_analysis.get('total_spend', 0))}")
        if 'total_revenue' in internal_analysis:
            lines.append(f"Total Revenue: {format_currency(internal_analysis.get('total_revenue', 0))}")
        lines.append("")
    
    lines.append("─" * 40)
    lines.append("OPTIMIZATION SUGGESTIONS")
    lines.append("─" * 40)
    lines.append("")
    
    for i, sugg in enumerate(suggestions, 1):
        urgency = sugg.get('urgency', 'MEDIUM')
        urgency_icon = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}.get(urgency, "⚪")
        
        lines.append(f"{i}. [{urgency}] {sugg['category']}")
        lines.append(f"   {urgency_icon} Finding: {sugg['finding']}")
        if 'gap' in sugg:
            lines.append(f"   Gap: {sugg['gap']}")
        if 'sites' in sugg:
            lines.append(f"   Sites: {', '.join(str(s) for s in sugg['sites'][:5])}")
        if 'campaigns' in sugg:
            lines.append(f"   Campaigns: {', '.join(str(c) for c in sugg['campaigns'][:5])}")
        lines.append(f"   → Recommendation: {sugg['recommendation']}")
        lines.append("")
    
    if "site_performance" in client_analysis:
        lines.append("─" * 40)
        lines.append("TOP PERFORMING SITES")
        lines.append("─" * 40)
        site_df = client_analysis["site_performance"]
        top_sites = site_df.head(10)
        for _, row in top_sites.iterrows():
            site_name = row[site_df.columns[0]]
            roas = row['avg_roas']
            count = row['count']
            tier = get_performance_tier(roas)
            lines.append(f"  {site_name}: {format_percent(roas)} ({count:,} entries) - {tier}")
        lines.append("")
        
        lines.append("─" * 40)
        lines.append("UNDERPERFORMING SITES")
        lines.append("─" * 40)
        bottom_sites = site_df.tail(10)
        for _, row in bottom_sites.iterrows():
            site_name = row[site_df.columns[0]]
            roas = row['avg_roas']
            count = row['count']
            tier = get_performance_tier(roas)
            lines.append(f"  {site_name}: {format_percent(roas)} ({count:,} entries) - {tier}")
        lines.append("")
    
    lines.append("=" * 80)
    lines.append("END OF REPORT")
    lines.append("=" * 80)
    
    return "\n".join(lines)


# ── Main Entry Point ──────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="ROAS D7 Optimization Suggestions Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Configuration:
  - ROAS D7 Goal: {ROAS_D7_GOAL_PERCENT}%
  - Client ROAS Column: "{CLIENT_ROAS_COLUMN}"

Examples:
  # Analyze client data only
  python roas_optimizer.py --client-file DT_DX.csv

  # Analyze both client and internal data
  python roas_optimizer.py --client-file DT_DX.xlsx --internal-file site_performance.csv

  # Export report to file
  python roas_optimizer.py --client-file DT_DX.csv --output report.txt
        """,
    )
    parser.add_argument(
        "--client-file", "-c",
        required=True,
        help="Path to client data file (DT_DX) - CSV or Excel",
    )
    parser.add_argument(
        "--internal-file", "-i",
        required=False,
        help="Path to internal data file (site_performance) - CSV or Excel",
    )
    parser.add_argument(
        "--output", "-o",
        required=False,
        help="Output file path for the report (optional)",
    )
    parser.add_argument(
        "--goal",
        type=float,
        default=ROAS_D7_GOAL_PERCENT,
        help=f"ROAS D7 goal percentage (default: {ROAS_D7_GOAL_PERCENT})",
    )
    
    args = parser.parse_args()
    
    global ROAS_D7_GOAL_PERCENT, ROAS_D7_GOAL
    ROAS_D7_GOAL_PERCENT = args.goal
    ROAS_D7_GOAL = args.goal / 100
    
    print(f"\n{'=' * 60}")
    print(f"ROAS D7 Optimization Analysis")
    print(f"Goal: {format_percent(ROAS_D7_GOAL_PERCENT)}")
    print(f"{'=' * 60}\n")
    
    print("Loading client data (DT_DX)...")
    try:
        client_df = load_data(args.client_file)
        print(f"  ✓ Loaded {len(client_df):,} rows from {args.client_file}")
    except Exception as e:
        print(f"  ✗ Error loading client file: {e}")
        sys.exit(1)
    
    internal_df = None
    internal_analysis = None
    if args.internal_file:
        print("Loading internal data (site_performance)...")
        try:
            internal_df = load_data(args.internal_file)
            print(f"  ✓ Loaded {len(internal_df):,} rows from {args.internal_file}")
        except Exception as e:
            print(f"  ✗ Error loading internal file: {e}")
    
    print("\nAnalyzing client data...")
    try:
        client_analysis = analyze_client_data(client_df)
        print(f"  ✓ Analysis complete")
    except Exception as e:
        print(f"  ✗ Error analyzing client data: {e}")
        sys.exit(1)
    
    if internal_df is not None:
        print("Analyzing internal data...")
        try:
            internal_analysis = analyze_internal_data(internal_df)
            print(f"  ✓ Analysis complete")
        except Exception as e:
            print(f"  ✗ Error analyzing internal data: {e}")
    
    print("Generating optimization suggestions...")
    suggestions = generate_optimization_suggestions(client_analysis, internal_analysis)
    print(f"  ✓ Generated {len(suggestions)} suggestions")
    
    print("\nGenerating report...")
    report = generate_report(client_analysis, internal_analysis, suggestions)
    
    if args.output:
        with open(args.output, 'w') as f:
            f.write(report)
        print(f"  ✓ Report saved to {args.output}")
    
    print("\n" + report)


if __name__ == "__main__":
    main()
