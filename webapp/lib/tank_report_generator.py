#!/usr/bin/env python3
"""
Tank Data Report Generator
Creates a professional PDF report with charts and analysis
Includes location-aware compliance standards reporting
"""

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, Circle, Wedge
import numpy as np
from datetime import datetime
from fpdf import FPDF
import os
import json
import logging
from pathlib import Path
from .alarm_analyzer import analyze_alarms

logger = logging.getLogger(__name__)

# Output directory will be configured dynamically
OUTPUT_DIR = Path(os.getenv('TANK_REPORTS_PATH', '/app/data/tank_reports'))
OUTPUT_DIR.mkdir(exist_ok=True, parents=True)

def get_output_path(filename):
    """Get full path for output file"""
    return str(OUTPUT_DIR / filename)

# ============================================================================
# COMPLIANCE DATA LOADING
# ============================================================================

COMPLIANCE_FILE = Path(__file__).parent / 'compliance.json'


def load_compliance_data(state_code='ID'):
    """
    Load compliance data and filter for federal + specified state requirements.

    Args:
        state_code: Two-letter state code (e.g., 'CA' for California)

    Returns:
        dict with filtered compliance requirements for federal and state-specific rules
    """
    try:
        with open(COMPLIANCE_FILE, 'r') as f:
            compliance = json.load(f)
    except FileNotFoundError:
        print(f"[WARNING] Compliance file not found: {COMPLIANCE_FILE}")
        return None
    except json.JSONDecodeError as e:
        print(f"[WARNING] Error parsing compliance file: {e}")
        return None

    # Filter reports for federal and state-specific requirements
    filtered_reports = []
    for report in compliance.get('reports', []):
        filtered_report = {
            'id': report['id'],
            'name': report['name'],
            'description': report['description'],
            'frequency': report['frequency'],
            'trigger': report['trigger'],
            'min_fields': report['min_fields'],
            'retention_months': report['retention_months'],
            'federal_citations': [],
            'state_citations': [],
            'state_notes': None
        }

        # Extract federal citations
        for citation in report.get('citations', []):
            if 'federal' in citation:
                filtered_report['federal_citations'].append(citation['federal'])

        # Extract state-specific citations
        for citation in report.get('citations', []):
            if state_code in citation:
                filtered_report['state_citations'].append(citation[state_code])

        # Get state-specific notes
        jurisdiction_notes = report.get('jurisdiction_notes', {})
        if state_code in jurisdiction_notes:
            filtered_report['state_notes'] = jurisdiction_notes[state_code]
        for key, value in jurisdiction_notes.items():
            if state_code in key.split('/'):
                filtered_report['state_notes'] = value
                break

        filtered_reports.append(filtered_report)

    return {
        'state_code': state_code,
        'baseline_regulation': compliance.get('baseline_regulation', {}),
        'reports': filtered_reports
    }


def get_compliance_summary(state_code='ID'):
    """
    Get a summary of applicable compliance requirements categorized by frequency.
    """
    compliance = load_compliance_data(state_code)
    if not compliance:
        return None

    summary = {
        'state_code': state_code,
        'federal_baseline': compliance['baseline_regulation'],
        'monthly_reports': [],
        'annual_reports': [],
        'triennial_reports': [],
        'event_driven_reports': [],
        'retention_requirements': {}
    }

    for report in compliance['reports']:
        freq = report['frequency'].lower()
        report_summary = {
            'id': report['id'],
            'name': report['name'],
            'description': report['description'],
            'retention_months': report['retention_months'],
            'federal_citations': report['federal_citations'],
            'state_citations': report['state_citations'],
            'state_notes': report['state_notes']
        }

        if 'monthly' in freq:
            summary['monthly_reports'].append(report_summary)
        elif 'annual' in freq:
            summary['annual_reports'].append(report_summary)
        elif '3_year' in freq or 'every_3' in freq or 'triennial' in freq:
            summary['triennial_reports'].append(report_summary)
        elif 'event' in freq:
            summary['event_driven_reports'].append(report_summary)
        else:
            summary['annual_reports'].append(report_summary)

        summary['retention_requirements'][report['id']] = report['retention_months']

    return summary


# ============================================================================
# DYNAMIC DATA - Passed as function parameters
# ============================================================================
# Data structures are now passed to functions instead of using globals
# This allows generating reports for any store with real-time data

# ============================================================================
# CHART GENERATION
# ============================================================================

def create_tank_gauge_chart(tank_inventory, output_dir):
    """Create tank level gauge visualization

    Args:
        tank_inventory: List of tank dicts with volume, capacity, etc.
        output_dir: Directory to save chart image
    """
    if not tank_inventory:
        logger.warning("No tank inventory data - skipping tank gauge chart")
        return

    num_tanks = len(tank_inventory)
    fig, axes = plt.subplots(1, num_tanks, figsize=(3.5 * num_tanks, 4))
    fig.suptitle('Real-Time Tank Levels', fontsize=16, fontweight='bold', y=1.02)

    # Handle single tank case (axes won't be array)
    if num_tanks == 1:
        axes = [axes]

    colors = ['#f39c12', '#3498db', '#2ecc71', '#e74c3c']

    for idx, (ax, tank) in enumerate(zip(axes, tank_inventory)):
        # Calculate fill percentage
        fill_pct = tank['volume'] / tank['capacity'] * 100

        # Create tank visualization
        tank_color = colors[idx]

        # Draw tank outline
        tank_rect = FancyBboxPatch((0.1, 0.1), 0.8, 0.8,
                                    boxstyle="round,pad=0.02,rounding_size=0.05",
                                    facecolor='#ecf0f1', edgecolor='#2c3e50', linewidth=3)
        ax.add_patch(tank_rect)

        # Draw fuel level
        fill_height = 0.8 * (fill_pct / 100)
        fuel_rect = FancyBboxPatch((0.12, 0.12), 0.76, fill_height,
                                    boxstyle="round,pad=0.01,rounding_size=0.03",
                                    facecolor=tank_color, edgecolor='none', alpha=0.8)
        ax.add_patch(fuel_rect)

        # Add percentage text
        ax.text(0.5, 0.5, f'{fill_pct:.0f}%', ha='center', va='center',
                fontsize=24, fontweight='bold', color='#2c3e50')

        # Add volume text
        ax.text(0.5, 0.25, f'{tank["volume"]:,} gal', ha='center', va='center',
                fontsize=10, color='#7f8c8d')

        # Add tank name
        ax.set_title(f'{tank["name"]}\n({tank["full_name"]})', fontsize=11, fontweight='bold')

        # Add temperature badge
        ax.text(0.5, -0.08, f'{tank["temp"]}°F', ha='center', va='center',
                fontsize=9, color='#e74c3c', fontweight='bold',
                bbox=dict(boxstyle='round', facecolor='#fadbd8', edgecolor='#e74c3c'))

        ax.set_xlim(0, 1)
        ax.set_ylim(-0.15, 1)
        ax.set_aspect('equal')
        ax.axis('off')

    plt.tight_layout()
    plt.savefig(f'{output_dir}/tank_gauges.png', dpi=150, bbox_inches='tight',
                facecolor='white', edgecolor='none')
    plt.close()


def create_sales_pie_chart(sales_data, output_dir):
    """Create sales distribution pie chart

    Args:
        sales_data: List of sales dicts with revenue, volume, etc.
        output_dir: Directory to save chart image
    """
    if not sales_data:
        logger.warning("No sales data - skipping sales pie chart")
        return

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
    fig.suptitle('Current Shift Sales Distribution', fontsize=16, fontweight='bold', y=1.02)

    # Revenue pie chart
    revenues = [s['revenue'] for s in sales_data]
    labels = [s['full_name'] for s in sales_data]
    colors = [s['color'] for s in sales_data]

    # Dynamic explode based on number of products
    explode_tuple = tuple([0.02] * len(sales_data))

    wedges, texts, autotexts = ax1.pie(revenues, labels=labels, colors=colors,
                                        autopct=lambda pct: f'${pct/100*sum(revenues):,.0f}\n({pct:.1f}%)',
                                        startangle=90, explode=explode_tuple)
    ax1.set_title('Revenue Distribution', fontsize=12, fontweight='bold')

    for autotext in autotexts:
        autotext.set_fontsize(9)
        autotext.set_fontweight('bold')

    # Volume pie chart
    volumes = [s['volume'] for s in sales_data]

    # Dynamic explode based on number of products
    explode_tuple = tuple([0.02] * len(sales_data))

    wedges2, texts2, autotexts2 = ax2.pie(volumes, labels=labels, colors=colors,
                                           autopct=lambda pct: f'{pct/100*sum(volumes):,.0f} gal\n({pct:.1f}%)',
                                           startangle=90, explode=explode_tuple)
    ax2.set_title('Volume Distribution', fontsize=12, fontweight='bold')

    for autotext in autotexts2:
        autotext.set_fontsize(9)
        autotext.set_fontweight('bold')

    plt.tight_layout()
    plt.savefig(f'{output_dir}/sales_pie.png', dpi=150, bbox_inches='tight',
                facecolor='white', edgecolor='none')
    plt.close()


def create_sales_bar_chart(sales_data, output_dir):
    """Create sales bar chart

    Args:
        sales_data: List of sales dicts with transactions, revenue, volume
        output_dir: Directory to save chart image
    """
    if not sales_data:
        logger.warning("No sales data - skipping sales bar chart")
        return

    fig, axes = plt.subplots(1, 3, figsize=(14, 5))
    fig.suptitle('Sales Metrics by Fuel Type', fontsize=16, fontweight='bold', y=1.02)

    names = [s['full_name'] for s in sales_data]
    colors = [s['color'] for s in sales_data]

    # Transactions
    transactions = [s['transactions'] for s in sales_data]
    bars1 = axes[0].bar(names, transactions, color=colors, edgecolor='white', linewidth=2)
    axes[0].set_title('Transactions', fontsize=12, fontweight='bold')
    axes[0].set_ylabel('Count')
    for bar, val in zip(bars1, transactions):
        axes[0].text(bar.get_x() + bar.get_width()/2, bar.get_height() + max(transactions)*0.02,
                     str(val), ha='center', va='bottom', fontweight='bold')
    axes[0].set_ylim(0, max(transactions) * 1.15)

    # Revenue
    revenues = [s['revenue'] for s in sales_data]
    bars2 = axes[1].bar(names, revenues, color=colors, edgecolor='white', linewidth=2)
    axes[1].set_title('Revenue ($)', fontsize=12, fontweight='bold')
    axes[1].set_ylabel('Dollars')
    for bar, val in zip(bars2, revenues):
        axes[1].text(bar.get_x() + bar.get_width()/2, bar.get_height() + max(revenues)*0.02,
                     f'${val:,.0f}', ha='center', va='bottom', fontweight='bold', fontsize=9)
    axes[1].set_ylim(0, max(revenues) * 1.15)

    # Volume
    volumes = [s['volume'] for s in sales_data]
    bars3 = axes[2].bar(names, volumes, color=colors, edgecolor='white', linewidth=2)
    axes[2].set_title('Volume (gallons)', fontsize=12, fontweight='bold')
    axes[2].set_ylabel('Gallons')
    for bar, val in zip(bars3, volumes):
        axes[2].text(bar.get_x() + bar.get_width()/2, bar.get_height() + max(volumes)*0.02,
                     f'{val:,.0f}', ha='center', va='bottom', fontweight='bold', fontsize=9)
    axes[2].set_ylim(0, max(volumes) * 1.15)

    for ax in axes:
        ax.tick_params(axis='x', rotation=15)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)

    plt.tight_layout()
    plt.savefig(f'{output_dir}/sales_bars.png', dpi=150, bbox_inches='tight',
                facecolor='white', edgecolor='none')
    plt.close()


def create_delivery_history_chart(deliveries, output_dir):
    """Create delivery history visualization

    Args:
        deliveries: Dict mapping tank names to list of (before, after) tuples
        output_dir: Directory to save chart image
    """
    if not deliveries:
        logger.warning("No delivery history data - skipping delivery chart")
        return

    num_tanks = len(deliveries)
    if num_tanks == 0:
        return

    # Determine grid size based on number of tanks
    if num_tanks == 1:
        fig, axes = plt.subplots(1, 1, figsize=(8, 6))
        axes = [axes]
    elif num_tanks == 2:
        fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    elif num_tanks <= 4:
        fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    else:
        fig, axes = plt.subplots(2, 3, figsize=(14, 8))

    fig.suptitle('Fuel Delivery History (Last 5 Deliveries)', fontsize=16, fontweight='bold', y=1.02)

    colors = ['#f39c12', '#3498db', '#2ecc71', '#9b59b6', '#e74c3c', '#1abc9c']

    for idx, (ax, (tank_name, tank_deliveries)) in enumerate(zip(axes.flat, deliveries.items())):
        if len(tank_deliveries) == 0:
            ax.axis('off')
            continue

        x = range(1, len(tank_deliveries) + 1)
        starts = [d[0] for d in tank_deliveries]
        ends = [d[1] for d in tank_deliveries]
        delivered = [e - s for s, e in tank_deliveries]

        # Plot before/after levels
        width = 0.35
        bars1 = ax.bar([i - width/2 for i in x], starts, width, label='Before Delivery',
                       color='#bdc3c7', edgecolor='white')
        bars2 = ax.bar([i + width/2 for i in x], ends, width, label='After Delivery',
                       color=colors[idx % len(colors)], edgecolor='white')

        # Add delivery amount annotations
        max_val = max(ends) if ends else 1
        for i, (s, e, d) in enumerate(zip(starts, ends, delivered)):
            ax.annotate(f'+{d:,}', xy=(i+1, e), xytext=(i+1, e + max_val*0.05),
                       ha='center', fontsize=8, fontweight='bold', color=colors[idx % len(colors)])

        ax.set_title(tank_name, fontsize=11, fontweight='bold')
        ax.set_xlabel('Delivery #')
        ax.set_ylabel('Volume (gal)')
        ax.set_xticks(x)
        ax.legend(loc='upper right', fontsize=8)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)

    # Hide unused subplots
    for idx in range(len(deliveries), len(axes.flat)):
        axes.flat[idx].axis('off')

    plt.tight_layout()
    plt.savefig(f'{output_dir}/delivery_history.png', dpi=150, bbox_inches='tight',
                facecolor='white', edgecolor='none')
    plt.close()


def create_alarm_timeline(alarms, output_dir):
    """Create alarm history timeline

    Args:
        alarms: List of alarm dicts with tank, type, date
        output_dir: Directory to save chart image
    """
    if not alarms:
        logger.warning("No alarm data - skipping alarm timeline chart")
        return

    fig, ax = plt.subplots(figsize=(12, 4))

    alarm_colors = {
        'HIGH WATER': '#3498db',
        'OVERFILL': '#e74c3c',
        'LOW LIMIT': '#f39c12',
        'LEAK': '#9b59b6',
        'HIGH PRODUCT': '#e67e22'
    }

    # Parse dates and create timeline
    dates = []
    types = []
    for a in alarms:
        try:
            date = datetime.strptime(a['date'], '%Y-%m-%d')
            dates.append(date)
            types.append(a['type'])
        except:
            logger.warning(f"Could not parse alarm date: {a.get('date', 'unknown')}")

    if not dates:
        logger.warning("No valid alarm dates - skipping alarm timeline")
        return

    # Sort by date
    sorted_data = sorted(zip(dates, types), key=lambda x: x[0])
    dates, types = zip(*sorted_data)

    # Plot timeline
    ax.axhline(y=0, color='#bdc3c7', linewidth=3, zorder=1)

    for i, (date, atype) in enumerate(zip(dates, types)):
        color = alarm_colors.get(atype, '#95a5a6')
        y_offset = 0.3 if i % 2 == 0 else -0.3

        ax.scatter(date, 0, s=200, c=color, zorder=2, edgecolor='white', linewidth=2)
        ax.annotate(f'{atype}\n{date.strftime("%Y-%m-%d")}',
                   xy=(date, 0), xytext=(date, y_offset),
                   ha='center', va='center' if y_offset > 0 else 'top',
                   fontsize=9, fontweight='bold',
                   arrowprops=dict(arrowstyle='->', color=color),
                   bbox=dict(boxstyle='round,pad=0.3', facecolor=color, alpha=0.2))

    # Legend
    unique_types = list(set(types))
    legend_elements = [mpatches.Patch(facecolor=alarm_colors.get(t, '#95a5a6'),
                                      label=t, edgecolor='white')
                      for t in unique_types]
    ax.legend(handles=legend_elements, loc='upper right', fontsize=9)

    ax.set_title('Tank Alarm History', fontsize=14, fontweight='bold')
    ax.set_ylim(-0.8, 0.8)
    # Convert dates to matplotlib date numbers for proper axis handling
    from matplotlib.dates import date2num
    date_nums = [date2num(d) for d in dates]
    ax.set_xlim(min(date_nums) - 60, max(date_nums) + 60)  # 60 days padding
    ax.axis('off')

    plt.tight_layout()
    plt.savefig(f'{output_dir}/alarm_timeline.png', dpi=150, bbox_inches='tight',
                facecolor='white', edgecolor='none')
    plt.close()


def create_inventory_summary(tank_inventory, sales_data, store_info, output_dir):
    """Create inventory summary dashboard

    Args:
        tank_inventory: List of tank dicts
        sales_data: List of sales dicts
        store_info: Store info dict
        output_dir: Directory to save chart image
    """
    if not tank_inventory:
        logger.warning("No tank inventory - skipping dashboard")
        return

    fig = plt.figure(figsize=(12, 6))

    # Create grid
    gs = fig.add_gridspec(2, 4, hspace=0.4, wspace=0.3)

    # Total inventory gauge (large)
    ax_main = fig.add_subplot(gs[:, :2])
    total_volume = sum(t['volume'] for t in tank_inventory)
    total_capacity = sum(t['capacity'] for t in tank_inventory)
    fill_pct = total_volume / total_capacity * 100 if total_capacity > 0 else 0

    # Draw donut chart
    sizes = [fill_pct, 100 - fill_pct]
    colors_donut = ['#27ae60', '#ecf0f1']
    wedges, _ = ax_main.pie(sizes, colors=colors_donut, startangle=90,
                            wedgeprops=dict(width=0.4, edgecolor='white'))

    # Center text
    ax_main.text(0, 0.1, f'{fill_pct:.1f}%', ha='center', va='center',
                 fontsize=36, fontweight='bold', color='#27ae60')
    ax_main.text(0, -0.15, f'{total_volume:,} / {total_capacity:,} gal',
                 ha='center', va='center', fontsize=12, color='#7f8c8d')
    ax_main.set_title('Total Inventory Level', fontsize=14, fontweight='bold', pad=20)

    # KPI boxes - handle case with no sales data
    if sales_data:
        total_revenue = sum(s['revenue'] for s in sales_data)
        total_transactions = sum(s['transactions'] for s in sales_data)
        total_volume_sold = sum(s['volume'] for s in sales_data)
        avg_per_txn = total_revenue / total_transactions if total_transactions > 0 else 0

        kpis = [
            ('Total Revenue', f'${total_revenue:,.2f}', '#27ae60'),
            ('Transactions', f'{total_transactions}', '#3498db'),
            ('Volume Sold', f'{total_volume_sold:,.0f} gal', '#9b59b6'),
            ('Avg $/Transaction', f'${avg_per_txn:.2f}', '#e67e22'),
        ]
    else:
        kpis = [
            ('Total Revenue', 'No Data', '#95a5a6'),
            ('Transactions', 'No Data', '#95a5a6'),
            ('Volume Sold', 'No Data', '#95a5a6'),
            ('Avg $/Transaction', 'No Data', '#95a5a6'),
        ]

    for i, (label, value, color) in enumerate(kpis):
        row = i // 2
        col = 2 + i % 2
        ax = fig.add_subplot(gs[row, col])

        ax.text(0.5, 0.6, value, ha='center', va='center', fontsize=18,
                fontweight='bold', color=color, transform=ax.transAxes)
        ax.text(0.5, 0.25, label, ha='center', va='center', fontsize=10,
                color='#7f8c8d', transform=ax.transAxes)

        # Add colored bar at top
        ax.axhline(y=1, color=color, linewidth=8, xmin=0.1, xmax=0.9)
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis('off')

    store_label = store_info.get('store_id', 'Unknown')
    fig.suptitle(f'Store {store_label} - Inventory & Sales Dashboard', fontsize=16, fontweight='bold', y=1.02)

    plt.savefig(f'{output_dir}/dashboard.png', dpi=150, bbox_inches='tight',
                facecolor='white', edgecolor='none')
    plt.close()


def create_compliance_overview_chart(compliance_data, store_info, output_dir):
    """Create compliance requirements overview chart

    Args:
        compliance_data: Dict with compliance requirements
        store_info: Store info dict
        output_dir: Directory to save chart image
    """
    if not compliance_data:
        logger.warning("No compliance data - skipping compliance chart")
        return

    try:
        fig, axes = plt.subplots(1, 2, figsize=(14, 6))
        state_name = store_info.get('state_name', 'Unknown State')
        fig.suptitle(f'Regulatory Compliance Overview - Federal & {state_name}',
                     fontsize=16, fontweight='bold', y=1.02)
    except Exception as e:
        logger.error(f"Error in compliance chart setup: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return

    try:
        # Left: Compliance requirements by frequency
        ax1 = axes[0]
        categories = ['Monthly', 'Annual', 'Triennial', 'Event-Driven']
        counts = [
            len(compliance_data.get('monthly_reports', [])),
            len(compliance_data.get('annual_reports', [])),
            len(compliance_data.get('triennial_reports', [])),
            len(compliance_data.get('event_driven_reports', []))
        ]
        colors = ['#e74c3c', '#f39c12', '#3498db', '#9b59b6']

        bars = ax1.barh(categories, counts, color=colors, edgecolor='white', linewidth=2)
        ax1.set_xlabel('Number of Required Reports', fontweight='bold')
        ax1.set_title('Compliance Requirements by Frequency', fontsize=12, fontweight='bold')

        for bar, count in zip(bars, counts):
            ax1.text(bar.get_width() + 0.1, bar.get_y() + bar.get_height()/2,
                     str(count), ha='left', va='center', fontweight='bold', fontsize=12)

        ax1.set_xlim(0, max(counts) * 1.3 if max(counts) > 0 else 10)
        ax1.spines['top'].set_visible(False)
        ax1.spines['right'].set_visible(False)

        # Right: Retention requirements pie chart
        ax2 = axes[1]
        retention_periods = {}
        all_reports = (compliance_data.get('monthly_reports', []) +
                       compliance_data.get('annual_reports', []) +
                       compliance_data.get('triennial_reports', []) +
                       compliance_data.get('event_driven_reports', []))

        for report in all_reports:
            months = report.get('retention_months', 12)
            if months <= 12:
                period = '1 Year'
            elif months <= 36:
                period = '3 Years'
            else:
                period = '5+ Years'
            retention_periods[period] = retention_periods.get(period, 0) + 1

        if retention_periods:
            labels = list(retention_periods.keys())
            sizes = list(retention_periods.values())
            retention_colors = ['#27ae60', '#f39c12', '#e74c3c'][:len(labels)]

            wedges, texts, autotexts = ax2.pie(sizes, labels=labels, colors=retention_colors,
                                                autopct='%1.0f%%', startangle=90,
                                                explode=[0.02] * len(labels))
            ax2.set_title('Record Retention Requirements', fontsize=12, fontweight='bold')

            for autotext in autotexts:
                autotext.set_fontsize(11)
                autotext.set_fontweight('bold')
        else:
            # No retention data to display
            ax2.text(0.5, 0.5, 'No Retention Data Available',
                    ha='center', va='center', fontsize=14, color='#95a5a6',
                    transform=ax2.transAxes)
            ax2.set_title('Record Retention Requirements', fontsize=12, fontweight='bold')
            ax2.axis('off')

        plt.tight_layout()
        plt.savefig(f'{output_dir}/compliance_overview.png', dpi=150, bbox_inches='tight',
                    facecolor='white', edgecolor='none')
        plt.close()
    except Exception as e:
        logger.error(f"Error creating compliance charts: {e}")
        import traceback
        logger.error(traceback.format_exc())
        plt.close('all')  # Clean up any open figures
        raise


# ============================================================================
# PDF REPORT GENERATION
# ============================================================================

def clean_text(text):
    """Replace problematic Unicode characters with ASCII-safe equivalents."""
    if not isinstance(text, str):
        return text
    
    replacements = {
        '\u2011': '-',  # Non-breaking hyphen
        '\u2013': '-',  # En dash
        '\u2014': '--', # Em dash
        '\u2026': '...', # Ellipsis
        '\u2018': "'",  # Left single quotation mark
        '\u2019': "'",  # Right single quotation mark
        '\u201c': '"',  # Left double quotation mark
        '\u201d': '"',  # Right double quotation mark
        '\u00a0': ' ',  # No-break space
        '\u202f': ' ',  # Narrow no-break space
    }
    for unicode_char, ascii_char in replacements.items():
        text = text.replace(unicode_char, ascii_char)
    
    return text.encode('latin-1', 'ignore').decode('latin-1')


class TankReport(FPDF):
    def __init__(self, store_id):
        super().__init__()
        self.store_id = store_id
        self.set_auto_page_break(auto=True, margin=15)

    def header(self):
        self.set_font('Helvetica', 'B', 10)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, f'Tank Monitoring Report - Store {self.store_id}', 0, 0, 'L')
        self.cell(0, 10, datetime.now().strftime('%Y-%m-%d %H:%M'), 0, 1, 'R')
        self.line(10, 18, 200, 18)
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('Helvetica', 'I', 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, f'Page {self.page_no()}/{{nb}}', 0, 0, 'C')

    def chapter_title(self, title):
        self.set_font('Helvetica', 'B', 14)
        self.set_text_color(44, 62, 80)
        self.set_fill_color(236, 240, 241)
        self.cell(0, 10, title, 0, 1, 'L', fill=True)
        self.ln(4)

    def section_title(self, title):
        self.set_font('Helvetica', 'B', 11)
        self.set_text_color(52, 73, 94)
        self.cell(0, 8, title, 0, 1, 'L')
        self.ln(2)

    def body_text(self, text):
        self.set_font('Helvetica', '', 10)
        self.set_text_color(0, 0, 0)
        self.multi_cell(0, 5, text)
        self.ln(2)


def clean_text(text):
    """Replace problematic Unicode characters with ASCII-safe equivalents."""
    if not isinstance(text, str):
        return text

    replacements = {
        '\u2011': '-',  # Non-breaking hyphen
        '\u2013': '-',  # En dash
        '\u2014': '--', # Em dash
        '\u2026': '...', # Ellipsis
        '\u2018': "'",  # Left single quotation mark
        '\u2019': "'",  # Right single quotation mark
        '\u201c': '"',  # Left double quotation mark
        '\u201d': '"',  # Right double quotation mark
        '\u00a0': ' ',  # No-break space
        '\u202f': ' ',  # Narrow no-break space
        '\u2060': '',   # Word joiner
        '\ufeff': '',   # Zero-width no-break space
    }
    for unicode_char, ascii_char in replacements.items():
        text = text.replace(unicode_char, ascii_char)

    # Final pass: encode to latin-1, dropping any remaining problematic characters
    return text.encode('latin-1', 'ignore').decode('latin-1')

def generate_pdf_report(store_info, tank_inventory, sales_data, alarms, deliveries, output_dir):
    """Generate the complete PDF report

    Args:
        store_info: Dict with store metadata (store_id, location, brand, etc.)
        tank_inventory: List of tank dicts
        sales_data: List of sales dicts
        alarms: List of alarm dicts
        deliveries: Dict of delivery history
        output_dir: Directory to save PDF and chart images

    Returns:
        str: Path to generated PDF file
    """
    logger.info(f"Generating PDF report for Store {store_info.get('store_id', 'Unknown')}")

    # First, generate all charts
    logger.info("Creating tank gauge chart...")
    create_tank_gauge_chart(tank_inventory, output_dir)

    logger.info("Creating sales pie chart...")
    create_sales_pie_chart(sales_data, output_dir)

    logger.info("Creating sales bar chart...")
    create_sales_bar_chart(sales_data, output_dir)

    logger.info("Creating delivery history chart...")
    create_delivery_history_chart(deliveries, output_dir)

    logger.info("Creating alarm timeline...")
    create_alarm_timeline(alarms, output_dir)

    logger.info("Creating inventory summary dashboard...")
    create_inventory_summary(tank_inventory, sales_data, store_info, output_dir)

    # Get compliance data
    state_code = store_info.get('state_code', 'ID')
    compliance_data = get_compliance_summary(state_code)

    logger.info("Creating compliance overview chart...")
    create_compliance_overview_chart(compliance_data, store_info, output_dir)

    # Now generate PDF
    pdf = TankReport(store_info.get('store_id', 'Unknown'))
    pdf.alias_nb_pages()

    # ========== COVER PAGE ==========
    pdf.add_page()
    pdf.set_font('Helvetica', 'B', 28)
    pdf.set_text_color(44, 62, 80)
    pdf.ln(40)
    pdf.cell(0, 15, 'Tank Monitoring Report', 0, 1, 'C')

    pdf.set_font('Helvetica', '', 18)
    pdf.set_text_color(127, 140, 141)
    pdf.cell(0, 10, f'Store {store_info.get("store_id", "Unknown")} - {store_info.get("location", "Unknown")}', 0, 1, 'C')
    pdf.cell(0, 10, store_info.get('brand', 'Unknown'), 0, 1, 'C')

    pdf.ln(20)
    pdf.set_font('Helvetica', 'B', 12)
    pdf.set_text_color(44, 62, 80)
    pdf.cell(0, 8, 'Report Generated:', 0, 1, 'C')
    pdf.set_font('Helvetica', '', 12)
    pdf.cell(0, 8, datetime.now().strftime('%B %d, %Y at %H:%M:%S'), 0, 1, 'C')

    pdf.ln(10)
    pdf.cell(0, 8, 'Data Source:', 0, 1, 'C')
    pdf.cell(0, 8, f'Veeder-Root TLS @ {store_info.get("ip", "Unknown")}', 0, 1, 'C')
    pdf.cell(0, 8, f'Last Reading: {store_info.get("last_reading", "Unknown")}', 0, 1, 'C')

    # ========== EXECUTIVE SUMMARY ==========
    pdf.add_page()
    pdf.chapter_title('Executive Summary')

    # Add dashboard image
    dashboard_path = get_output_path('dashboard.png')
    if os.path.exists(dashboard_path):
        pdf.image(dashboard_path, x=10, w=190)

    pdf.ln(5)
    pdf.body_text(
        f'This report provides a comprehensive analysis of tank monitoring data for Store {store_info.get("store_id", "Unknown")} '
        f'located in {store_info.get("location", "Unknown")}. The data is collected in real-time from the {store_info.get("tank_monitor", "Unknown")} '
        f'automatic tank gauge system.\n\n'
        f'Key Findings:\n'
        f'- Total inventory across all tanks: {sum(t["volume"] for t in tank_inventory):,} gallons\n'
        f'- Current shift revenue: ${sum(s["revenue"] for s in sales_data):,.2f}\n'
        f'- Total transactions: {sum(s["transactions"] for s in sales_data)}\n'
        f'- Volume dispensed: {sum(s["volume"] for s in sales_data):,.1f} gallons\n'
        f'- All water levels nominal (0.0 inches)'
    )

    # ========== TANK LEVELS ==========
    pdf.add_page()
    pdf.chapter_title('Real-Time Tank Levels')

    tank_gauges_path = get_output_path('tank_gauges.png')
    if os.path.exists(tank_gauges_path):
        pdf.image(tank_gauges_path, x=10, w=190)

    pdf.ln(5)
    pdf.section_title('Tank Inventory Details')

    # Create table
    pdf.set_font('Helvetica', 'B', 9)
    pdf.set_fill_color(52, 73, 94)
    pdf.set_text_color(255, 255, 255)

    col_widths = [25, 35, 30, 30, 25, 25, 20]
    headers = ['Tank', 'Product', 'Volume (gal)', 'Capacity', 'Fill %', 'Temp (F)', 'Water']

    for i, header in enumerate(headers):
        pdf.cell(col_widths[i], 8, header, 1, 0, 'C', fill=True)
    pdf.ln()

    pdf.set_font('Helvetica', '', 9)
    pdf.set_text_color(0, 0, 0)

    for tank in tank_inventory:
        fill_pct = tank['volume'] / tank['capacity'] * 100
        row_data = [
            tank['name'],
            tank['full_name'],
            f'{tank["volume"]:,}',
            f'{tank["capacity"]:,}',
            f'{fill_pct:.1f}%',
            f'{tank["temp"]}',
            f'{tank["water"]}"'
        ]
        for i, data in enumerate(row_data):
            pdf.cell(col_widths[i], 7, str(data), 1, 0, 'C')
        pdf.ln()

    # ========== SALES ANALYSIS ==========
    pdf.add_page()
    pdf.chapter_title('Sales Analysis - Current Shift')

    sales_pie_path = get_output_path('sales_pie.png')
    if os.path.exists(sales_pie_path):
        pdf.image(sales_pie_path, x=10, w=190)

    pdf.ln(5)

    sales_bars_path = get_output_path('sales_bars.png')
    if os.path.exists(sales_bars_path):
        pdf.image(sales_bars_path, x=10, w=190)

    pdf.ln(5)
    pdf.section_title('Sales Breakdown by Product')

    # Sales table
    pdf.set_font('Helvetica', 'B', 9)
    pdf.set_fill_color(52, 73, 94)
    pdf.set_text_color(255, 255, 255)

    col_widths = [40, 35, 35, 40, 40]
    headers = ['Product', 'Transactions', 'Volume (gal)', 'Revenue', 'Avg $/Trans']

    for i, header in enumerate(headers):
        pdf.cell(col_widths[i], 8, header, 1, 0, 'C', fill=True)
    pdf.ln()

    pdf.set_font('Helvetica', '', 9)
    pdf.set_text_color(0, 0, 0)

    for sale in sales_data:
        avg_trans = sale['revenue'] / sale['transactions']
        row_data = [
            sale['full_name'],
            str(sale['transactions']),
            f'{sale["volume"]:,.1f}',
            f'${sale["revenue"]:,.2f}',
            f'${avg_trans:.2f}'
        ]
        for i, data in enumerate(row_data):
            pdf.cell(col_widths[i], 7, str(data), 1, 0, 'C')
        pdf.ln()

    # Totals row
    pdf.set_font('Helvetica', 'B', 9)
    pdf.set_fill_color(236, 240, 241)
    total_trans = sum(s['transactions'] for s in sales_data)
    total_vol = sum(s['volume'] for s in sales_data)
    total_rev = sum(s['revenue'] for s in sales_data)
    avg_per_trans = f'${total_rev/total_trans:.2f}' if total_trans > 0 else 'N/A'
    totals = ['TOTAL', str(total_trans), f'{total_vol:,.1f}', f'${total_rev:,.2f}', avg_per_trans]
    for i, data in enumerate(totals):
        pdf.cell(col_widths[i], 7, str(data), 1, 0, 'C', fill=True)
    pdf.ln()

    # ========== DELIVERY HISTORY ==========
    pdf.add_page()
    pdf.chapter_title('Fuel Delivery History')

    delivery_history_path = get_output_path('delivery_history.png')
    if os.path.exists(delivery_history_path):
        pdf.image(delivery_history_path, x=10, w=190)

    pdf.ln(5)
    pdf.body_text(
        'The charts above show the last 5 fuel deliveries for each tank. '
        'The gray bars represent tank volume before delivery, while the colored bars show '
        'volume after delivery. The annotations indicate the delivery amount.\n\n'
        'Delivery patterns can be used to:\n'
        '- Optimize delivery schedules\n'
        '- Predict reorder points\n'
        '- Identify consumption trends\n'
        '- Verify delivery accuracy'
    )

    # ========== ALARM HISTORY ==========
    pdf.add_page()
    pdf.chapter_title('Alarm History & Compliance')

    alarm_timeline_path = get_output_path('alarm_timeline.png')
    if os.path.exists(alarm_timeline_path):
        pdf.image(alarm_timeline_path, x=10, w=190)

    pdf.ln(5)
    pdf.section_title('Alarm Log')

    # Alarm table
    pdf.set_font('Helvetica', 'B', 9)
    pdf.set_fill_color(52, 73, 94)
    pdf.set_text_color(255, 255, 255)

    col_widths = [40, 60, 50, 40]
    headers = ['Tank', 'Alarm Type', 'Date', 'Status']

    for i, header in enumerate(headers):
        pdf.cell(col_widths[i], 8, header, 1, 0, 'C', fill=True)
    pdf.ln()

    pdf.set_font('Helvetica', '', 9)
    pdf.set_text_color(0, 0, 0)

    if alarms:
        for alarm in alarms:
            row_data = [alarm['tank'], alarm['type'], alarm['date'], 'Cleared']
            for i, data in enumerate(row_data):
                pdf.cell(col_widths[i], 7, str(data), 1, 0, 'C')
            pdf.ln()

        pdf.ln(5)
        pdf.section_title('Analysis & Recommendations')

        # Use intelligent alarm analyzer
        try:
            alarm_summary, alarm_recommendations, _ = analyze_alarms(alarms)
            pdf.body_text(alarm_summary + '\n\n' + alarm_recommendations)
        except Exception as e:
            # Fallback to basic message if analysis fails
            pdf.body_text(
                f'Alarm analysis encountered an issue: {str(e)}\n\n'
                'Manual review of alarm log recommended.'
            )
    else:
        pdf.cell(0, 7, 'No alarm data available for this reporting period.', 1, 1, 'C')
        pdf.ln(5)

    # ========== COMPLIANCE STANDARDS ==========
    pdf.add_page()
    pdf.chapter_title(f'Regulatory Compliance - Federal & {store_info.get("state_name", "Unknown")}')

    # Load compliance data
    compliance = get_compliance_summary(store_info.get('state_code', 'ID'))

    if compliance:
        # Compliance overview chart
        compliance_overview_path = get_output_path('compliance_overview.png')
        if os.path.exists(compliance_overview_path):
            pdf.image(compliance_overview_path, x=10, w=190)
            pdf.ln(5)

        # Federal baseline
        baseline = compliance['federal_baseline']
        pdf.section_title('Federal Regulatory Baseline')
        pdf.body_text(
            f"Primary Regulation: {clean_text(baseline.get('name', 'EPA UST'))}\n"
            f"Citation: {clean_text(baseline.get('citation', '40 CFR Part 280'))}\n"
            f"All underground storage tank (UST) systems must comply with federal EPA "
            f"regulations as the baseline standard. State-specific requirements may exceed "
            f"federal minimums."
        )

        # Monthly requirements
        pdf.section_title(f'Monthly Requirements ({len(compliance["monthly_reports"])} reports)')
        for report in compliance['monthly_reports']:
            pdf.set_font('Helvetica', 'B', 9)
            pdf.cell(0, 5, f"- {clean_text(report['name'])}", 0, 1)
            pdf.set_font('Helvetica', '', 8)
            if report['federal_citations']:
                pdf.cell(0, 4, f"  Federal: {clean_text(', '.join(report['federal_citations']))}", 0, 1)
            if report['state_notes']:
                pdf.set_font('Helvetica', 'I', 8)
                pdf.cell(0, 4, f"  {store_info.get('state_code', 'ID')} Note: {clean_text(report['state_notes'][:80])}...", 0, 1)
            pdf.ln(1)

        # Add new page for annual/triennial requirements
        pdf.add_page()
        pdf.chapter_title('Periodic Compliance Requirements')

        # Annual requirements
        pdf.section_title(f'Annual Requirements ({len(compliance["annual_reports"])} reports)')
        for report in compliance['annual_reports']:
            pdf.set_font('Helvetica', 'B', 9)
            pdf.cell(0, 5, f"- {clean_text(report['name'])}", 0, 1)
            pdf.set_font('Helvetica', '', 8)
            if report['federal_citations']:
                pdf.cell(0, 4, f"  Federal: {clean_text(', '.join(report['federal_citations']))}", 0, 1)
            if report['state_notes']:
                pdf.set_font('Helvetica', 'I', 8)
                notes = report['state_notes'][:100] + '...' if len(report['state_notes']) > 100 else report['state_notes']
                pdf.cell(0, 4, f"  {store_info.get('state_code', 'ID')} Note: {clean_text(notes)}", 0, 1)
            pdf.ln(1)

        # Triennial requirements
        pdf.section_title(f'Triennial (3-Year) Requirements ({len(compliance["triennial_reports"])} reports)')
        for report in compliance['triennial_reports']:
            pdf.set_font('Helvetica', 'B', 9)
            pdf.cell(0, 5, f"- {clean_text(report['name'])}", 0, 1)
            pdf.set_font('Helvetica', '', 8)
            if report['federal_citations']:
                pdf.cell(0, 4, f"  Federal: {clean_text(', '.join(report['federal_citations']))}", 0, 1)
            if report['state_notes']:
                pdf.set_font('Helvetica', 'I', 8)
                notes = report['state_notes'][:100] + '...' if len(report['state_notes']) > 100 else report['state_notes']
                pdf.cell(0, 4, f"  {store_info.get('state_code', 'ID')} Note: {clean_text(notes)}", 0, 1)
            pdf.ln(1)

        # Event-driven requirements
        pdf.section_title(f'Event-Driven Requirements ({len(compliance["event_driven_reports"])} reports)')
        for report in compliance['event_driven_reports']:
            pdf.set_font('Helvetica', 'B', 9)
            pdf.cell(0, 5, f"- {clean_text(report['name'])}", 0, 1)
            pdf.set_font('Helvetica', '', 8)
            description_text = clean_text(report['description'][:120]) + '...'
            pdf.multi_cell(0, 4, f"  Trigger: {description_text}")
            if report['state_notes']:
                pdf.set_font('Helvetica', 'I', 8)
                pdf.cell(0, 4, f"  {store_info.get('state_code', '')} Note: {clean_text(report['state_notes'])}", 0, 1)
            pdf.ln(1)

        # State-specific summary
        pdf.add_page()
        state_code = store_info.get('state_code', '')
        state_name = store_info.get('state_name', 'Unknown')
        pdf.chapter_title(f'{state_name} ({state_code}) Specific Requirements')

        pdf.body_text(
            f"The following {state_name}-specific compliance notes apply to Store {store_info.get('store_id', 'Unknown')}:\n\n"
            "KEY STATE DEQ REQUIREMENTS:\n\n"
            "1. RELEASE NOTIFICATION: Notify state DEQ within 24 hours of any suspected "
            "release. Initial response actions are required immediately.\n\n"
            "2. INSTALLATION/MODIFICATION: 30-day prior notice required for tank installations; "
            "24-hour notice for certain piping work. Compatibility notice required for fuels "
            "exceeding E10 or B20 blends.\n\n"
            "3. TRIENNIAL INSPECTIONS: State DEQ conducts inspections every 3 years. "
            "Walk-through records will be reviewed during these inspections.\n\n"
            "4. RECORD RETENTION: Maintain all monthly ATG test results, interstitial monitoring "
            "logs, and inspection records for inspector review.\n\n"
            "5. OPERATOR TRAINING: Maintain Class A/B/C operator certificates per state DEQ "
            "program requirements."
        )

        # Compliance checklist table
        pdf.ln(5)
        pdf.section_title('Compliance Record Retention Summary')

        pdf.set_font('Helvetica', 'B', 9)
        pdf.set_fill_color(52, 73, 94)
        pdf.set_text_color(255, 255, 255)

        col_widths = [80, 50, 60]
        headers = ['Report Type', 'Retention Period', 'Frequency']

        for i, header in enumerate(headers):
            pdf.cell(col_widths[i], 8, header, 1, 0, 'C', fill=True)
        pdf.ln()

        pdf.set_font('Helvetica', '', 8)
        pdf.set_text_color(0, 0, 0)

        retention_data = [
            ('Release Detection Records', '12 months', 'Monthly'),
            ('Walkthrough Inspections', '12 months', 'Monthly'),
            ('ATG Static Leak Tests', '12 months', 'Monthly'),
            ('Line Leak Detection Tests', '36 months', 'Annual'),
            ('Spill Bucket Tests', '36 months', 'Every 3 years'),
            ('Overfill Device Inspections', '36 months', 'Every 3 years'),
            ('Cathodic Protection Tests', '36 months', 'Every 3 years'),
            ('Release Notifications', '60 months', 'As needed'),
            ('Operator Training Records', '60 months', 'As needed'),
            ('Financial Responsibility', '60 months', 'Annual'),
        ]

        for row in retention_data:
            for i, data in enumerate(row):
                pdf.cell(col_widths[i], 6, str(data), 1, 0, 'C')
            pdf.ln()
    else:
        pdf.body_text('Compliance data could not be loaded. Please verify compliance.json file.')

    # ========== APPENDIX ==========
    pdf.add_page()
    pdf.chapter_title('Appendix: System Information')

    pdf.section_title('Data Source Details')
    pdf.body_text(
        f'Store ID: {store_info.get("store_id", "Unknown")}\n'
        f'Location: {store_info.get("location", "Unknown")}\n'
        f'Brand: {store_info.get("brand", "Unknown")}\n'
        f'Commander IP: {store_info.get("ip", "Unknown")}\n'
        f'Tank Monitor Type: {store_info.get("tank_monitor", "Unknown")}\n'
        f'Last Data Reading: {store_info.get("last_reading", "Unknown")}\n\n'
        'API Endpoints Used:\n'
        '- vtlssite (Tank Level Sensor Configuration)\n'
        '- vfuelcfg (Fuel Configuration)\n'
        '- vrubyrept/tank (Tank Sales Report)\n'
        '- vrubyrept/tankMonitor (Real-time Tank Levels)\n'
        '- vrubyrept/tankRec (Tank Reconciliation)\n'
    )

    pdf.section_title('Fuel Product Configuration')
    products = [
        ('DIESEL 2', 'Tank 1 (DSL)', '100%'),
        ('REG E10', 'Tank 5 (UNL)', '100%'),
        ('PREM E10', 'Tank 6 (PRM)', '100%'),
        ('PLUS E10', 'Tank 5 + Tank 6', '67% / 33% blend'),
        ('E00', 'Tank 7', '100%'),
    ]

    pdf.set_font('Helvetica', 'B', 9)
    pdf.set_fill_color(52, 73, 94)
    pdf.set_text_color(255, 255, 255)

    col_widths = [50, 60, 50]
    headers = ['Product', 'Source Tank(s)', 'Blend Ratio']

    for i, header in enumerate(headers):
        pdf.cell(col_widths[i], 8, header, 1, 0, 'C', fill=True)
    pdf.ln()

    pdf.set_font('Helvetica', '', 9)
    pdf.set_text_color(0, 0, 0)

    for product in products:
        for i, data in enumerate(product):
            pdf.cell(col_widths[i], 7, str(data), 1, 0, 'C')
        pdf.ln()

    # Save PDF with dynamic filename
    store_id = store_info.get('store_id', 'Unknown')
    pdf_filename = f'Tank_Report_Store{store_id}.pdf'
    pdf_path = f'{output_dir}/{pdf_filename}'
    pdf.output(pdf_path)
    logger.info(f'PDF report generated: {pdf_path}')
    return pdf_path


# ============================================================================
# MAIN
# ============================================================================

def main():
    print('='*60)
    print('  TANK DATA REPORT GENERATOR')
    print(f'  Store {store_info.get("store_id", "Unknown")} - {store_info.get("state_name", "Unknown")}')
    print('='*60)

    print('\nGenerating visualizations...')

    print('  - Creating tank gauge chart...')
    create_tank_gauge_chart()

    print('  - Creating sales pie charts...')
    create_sales_pie_chart()

    print('  - Creating sales bar charts...')
    create_sales_bar_chart()

    print('  - Creating delivery history chart...')
    create_delivery_history_chart()

    print('  - Creating alarm timeline...')
    create_alarm_timeline()

    print('  - Creating dashboard summary...')
    create_inventory_summary()

    print('  - Creating compliance overview chart...')
    create_compliance_overview_chart()

    print('\nGenerating PDF report with compliance data...')
    print(f'  Location: {store_info.get("state_name", "Unknown")} ({store_info.get("state_code", "ID")})')
    print(f'  Applicable standards: Federal (EPA UST) + {store_info.get("state_code", "ID")} DEQ')
    generate_pdf_report()

    print('\n' + '='*60)
    print('  REPORT GENERATION COMPLETE')
    print('='*60)
    print('\nOutput files:')
    for f in os.listdir(OUTPUT_DIR):
        size = os.path.getsize(OUTPUT_DIR / f)
        print(f'  - {f} ({size:,} bytes)')


if __name__ == '__main__':
    main()
