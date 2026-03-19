# ROAS D7 Optimization Tool

Analyzes marketing campaign performance data to provide optimization suggestions based on D7 ROAS goals.

## Configuration

- **ROAS D7 Goal**: 2.18%
- **Internal file**: `site_performance` (CSV or Excel)
- **Client file**: `DT_DX` (CSV or Excel)
- **Client ROAS column**: "Domino Dreams Marketing Campaigns Daily Metrics Full ROAS D7"

## Installation

```bash
pip install -r requirements.txt
```

## Usage

### Basic Usage (Client Data Only)

```bash
python roas_optimizer.py --client-file DT_DX.csv
```

### Full Analysis (Client + Internal Data)

```bash
python roas_optimizer.py --client-file DT_DX.xlsx --internal-file site_performance.csv
```

### Custom ROAS Goal

```bash
python roas_optimizer.py --client-file DT_DX.csv --goal 2.5
```

### Export Report

```bash
python roas_optimizer.py --client-file DT_DX.csv --output report.txt
```

## Input File Requirements

### Client File (DT_DX)
Must contain a ROAS column. The tool will search for:
- "Domino Dreams Marketing Campaigns Daily Metrics Full ROAS D7" (exact match)
- Or columns containing: "roas", "roas_d7", "d7 roas"

Optional columns for detailed analysis:
- Campaign name/ID
- Site/Publisher/Source
- Date

### Internal File (site_performance)
Can contain any combination of:
- Site/Publisher identifier
- Spend/Cost data
- Revenue data
- ROAS data (or will be calculated from spend/revenue)
- Date

## Output

The tool generates a comprehensive report including:

1. **Summary Statistics**: Average, median, min/max ROAS
2. **Goal Comparison**: Performance vs. 2.18% target
3. **Optimization Suggestions**: Prioritized recommendations
4. **Site Rankings**: Top and underperforming sites
5. **Spend Efficiency Analysis**: Budget allocation insights

## Suggestion Categories

| Urgency | Description |
|---------|-------------|
| HIGH 🔴 | Immediate action required |
| MEDIUM 🟡 | Should address soon |
| LOW 🟢 | Monitoring/scaling opportunities |

## Performance Tiers

| Tier | ROAS vs Goal |
|------|--------------|
| Excellent | ≥120% of goal |
| On Target | ≥100% of goal |
| Below Target | 80-99% of goal |
| Underperforming | 50-79% of goal |
| Critical | <50% of goal |
