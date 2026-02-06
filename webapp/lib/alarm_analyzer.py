#!/usr/bin/env python3
"""
Intelligent Alarm Pattern Analyzer
Generates human-readable analysis from tank alarm data without requiring an LLM
"""

from datetime import datetime, timedelta
from collections import defaultdict, Counter
import re

class AlarmAnalyzer:
    """Analyzes tank alarm patterns and generates insights"""

    # Alarm severity levels
    SEVERITY = {
        'CRITICAL': ['OVERFILL', 'MAJOR LEAK', 'SYSTEM FAILURE', 'TANK FAILURE'],
        'HIGH': ['HIGH WATER', 'LEAK DETECTED', 'SENSOR FAILURE', 'HIGH LEVEL'],
        'MEDIUM': ['LOW LEVEL', 'LOW LIMIT', 'TEMPERATURE HIGH', 'TEMPERATURE LOW'],
        'LOW': ['CALIBRATION NEEDED', 'MAINTENANCE DUE', 'WARNING']
    }

    # Known alarm patterns and their explanations
    PATTERN_EXPLANATIONS = {
        'seasonal': {
            'spring': 'Spring thaw and increased groundwater levels',
            'summer': 'High temperatures affecting tank pressure',
            'fall': 'Fall weather patterns and increased precipitation',
            'winter': 'Freezing temperatures and ground movement'
        },
        'recurring': 'Indicates a systemic issue requiring investigation',
        'cascade': 'Multiple related alarms suggest a chain reaction event',
        'isolated': 'Single incident, likely resolved'
    }

    def __init__(self, alarms):
        """
        Initialize with alarm data

        Args:
            alarms: List of alarm dicts with keys: tank, type, date
                   e.g. [{'tank': 'DSL', 'type': 'HIGH WATER', 'date': '2025-10-03'}, ...]
        """
        self.alarms = alarms
        self.analysis_results = {}

    def parse_dates(self):
        """Parse date strings into datetime objects"""
        for alarm in self.alarms:
            if isinstance(alarm['date'], str):
                alarm['date_obj'] = datetime.strptime(alarm['date'], '%Y-%m-%d')
            else:
                alarm['date_obj'] = alarm['date']

    def get_severity(self, alarm_type):
        """Determine alarm severity"""
        alarm_upper = alarm_type.upper()
        for severity, types in self.SEVERITY.items():
            if any(t in alarm_upper for t in types):
                return severity
        return 'LOW'

    def analyze_frequency(self):
        """Analyze alarm frequency patterns"""
        self.parse_dates()

        # Group alarms by type and tank
        by_type = defaultdict(list)
        by_tank = defaultdict(list)

        for alarm in self.alarms:
            by_type[alarm['type']].append(alarm)
            by_tank[alarm['tank']].append(alarm)

        results = {
            'by_type': {},
            'by_tank': {},
            'most_common_type': None,
            'most_problematic_tank': None
        }

        # Analyze by type
        for alarm_type, occurrences in by_type.items():
            results['by_type'][alarm_type] = {
                'count': len(occurrences),
                'severity': self.get_severity(alarm_type),
                'tanks': list(set(a['tank'] for a in occurrences))
            }

        # Analyze by tank
        for tank, occurrences in by_tank.items():
            results['by_tank'][tank] = {
                'count': len(occurrences),
                'types': Counter(a['type'] for a in occurrences)
            }

        # Find most common
        if by_type:
            results['most_common_type'] = max(by_type.items(), key=lambda x: len(x[1]))[0]
        if by_tank:
            results['most_problematic_tank'] = max(by_tank.items(), key=lambda x: len(x[1]))[0]

        self.analysis_results['frequency'] = results
        return results

    def analyze_patterns(self):
        """Detect temporal patterns (seasonal, recurring, etc.)"""
        self.parse_dates()

        patterns = {
            'seasonal': [],
            'recurring': [],
            'clusters': [],
            'time_spans': {}
        }

        # Group by type for pattern detection
        by_type = defaultdict(list)
        for alarm in self.alarms:
            by_type[alarm['type']].append(alarm)

        # Detect patterns for each alarm type
        for alarm_type, occurrences in by_type.items():
            if len(occurrences) < 2:
                continue

            # Sort by date
            sorted_alarms = sorted(occurrences, key=lambda x: x['date_obj'])
            dates = [a['date_obj'] for a in sorted_alarms]

            # Check for seasonal patterns (same month recurring)
            months = [d.month for d in dates]
            if len(set(months)) == 1 and len(months) >= 2:
                month_name = dates[0].strftime('%B')
                patterns['seasonal'].append({
                    'type': alarm_type,
                    'month': month_name,
                    'count': len(dates),
                    'years': [d.year for d in dates],
                    'season': self._get_season(dates[0].month)
                })

            # Check for recurring patterns (similar intervals)
            if len(dates) >= 3:
                intervals = [(dates[i+1] - dates[i]).days for i in range(len(dates)-1)]
                avg_interval = sum(intervals) / len(intervals)

                # Check if intervals are consistent (within 20% variance)
                if all(abs(i - avg_interval) / avg_interval < 0.2 for i in intervals):
                    patterns['recurring'].append({
                        'type': alarm_type,
                        'interval_days': int(avg_interval),
                        'count': len(dates)
                    })

            # Check for clusters (multiple alarms within short time)
            for i in range(len(dates) - 1):
                if (dates[i+1] - dates[i]).days <= 7:
                    patterns['clusters'].append({
                        'type': alarm_type,
                        'date': dates[i].strftime('%Y-%m-%d'),
                        'count': 2
                    })

            # Calculate time span
            if len(dates) >= 2:
                span = (dates[-1] - dates[0]).days
                patterns['time_spans'][alarm_type] = {
                    'days': span,
                    'first': dates[0].strftime('%Y-%m-%d'),
                    'last': dates[-1].strftime('%Y-%m-%d')
                }

        self.analysis_results['patterns'] = patterns
        return patterns

    def _get_season(self, month):
        """Determine season from month"""
        if month in [12, 1, 2]:
            return 'winter'
        elif month in [3, 4, 5]:
            return 'spring'
        elif month in [6, 7, 8]:
            return 'summer'
        else:
            return 'fall'

    def analyze_severity_distribution(self):
        """Analyze distribution of alarm severities"""
        severity_count = Counter()

        for alarm in self.alarms:
            severity = self.get_severity(alarm['type'])
            severity_count[severity] += 1

        self.analysis_results['severity'] = dict(severity_count)
        return dict(severity_count)

    def generate_recommendations(self):
        """Generate actionable recommendations based on analysis"""
        recommendations = []

        if 'frequency' not in self.analysis_results:
            self.analyze_frequency()
        if 'patterns' not in self.analysis_results:
            self.analyze_patterns()
        if 'severity' not in self.analysis_results:
            self.analyze_severity_distribution()

        freq = self.analysis_results['frequency']
        patterns = self.analysis_results['patterns']
        severity = self.analysis_results['severity']

        # Critical alarms
        if 'CRITICAL' in severity and severity['CRITICAL'] > 0:
            recommendations.append({
                'priority': 'CRITICAL',
                'title': 'Critical Alarms Detected',
                'description': f'{severity["CRITICAL"]} critical alarm(s) require immediate attention.',
                'action': 'Schedule emergency inspection and repair.'
            })

        # Seasonal patterns
        for seasonal in patterns.get('seasonal', []):
            recommendations.append({
                'priority': 'HIGH',
                'title': f'Seasonal Pattern Detected: {seasonal["type"]}',
                'description': f'This alarm occurs annually in {seasonal["month"]} ({seasonal["count"]} times over {len(seasonal["years"])} years).',
                'action': f'Schedule preventive maintenance before {seasonal["month"]} each year. Investigate {self.PATTERN_EXPLANATIONS["seasonal"].get(seasonal["season"], "seasonal factors")}.'
            })

        # Recurring patterns
        for recurring in patterns.get('recurring', []):
            recommendations.append({
                'priority': 'HIGH',
                'title': f'Recurring Pattern: {recurring["type"]}',
                'description': f'Alarm repeats every ~{recurring["interval_days"]} days ({recurring["count"]} occurrences).',
                'action': 'Indicates systemic issue. Conduct root cause analysis and implement permanent fix.'
            })

        # Cluster detection (cascade failures)
        clusters = patterns.get('clusters', [])
        if clusters:
            cluster_count = len(clusters)
            recommendations.append({
                'priority': 'MEDIUM',
                'title': 'Alarm Clusters Detected',
                'description': f'{cluster_count} instance(s) of multiple alarms within 7 days.',
                'action': 'Review operational procedures. Multiple alarms in short period suggest chain reaction or related issues.'
            })

        # Problematic tank
        if freq.get('most_problematic_tank'):
            tank = freq['most_problematic_tank']
            count = freq['by_tank'][tank]['count']
            recommendations.append({
                'priority': 'MEDIUM',
                'title': f'Tank {tank} Requires Attention',
                'description': f'This tank has generated {count} alarms, more than other tanks.',
                'action': f'Prioritize inspection and maintenance for Tank {tank}.'
            })

        # High water alarms (specific logic)
        high_water_count = freq['by_type'].get('HIGH WATER', {}).get('count', 0)
        if high_water_count >= 2:
            recommendations.append({
                'priority': 'HIGH',
                'title': 'Recurring Water Intrusion',
                'description': f'{high_water_count} HIGH WATER alarms detected.',
                'action': 'Inspect tank seals, containment, and drainage systems. Consider groundwater monitoring.'
            })

        self.analysis_results['recommendations'] = recommendations
        return recommendations

    def generate_summary_text(self):
        """Generate human-readable summary for PDF report"""
        if not self.analysis_results:
            self.analyze_frequency()
            self.analyze_patterns()
            self.analyze_severity_distribution()
            self.generate_recommendations()

        summary = []
        freq = self.analysis_results['frequency']
        patterns = self.analysis_results['patterns']

        # Overview
        total_alarms = len(self.alarms)
        summary.append(f"Total Alarms: {total_alarms}")

        if freq.get('most_common_type'):
            most_common = freq['most_common_type']
            count = freq['by_type'][most_common]['count']
            summary.append(f"Most Common: {most_common} ({count} occurrences)")

        # Patterns
        seasonal = patterns.get('seasonal', [])
        if seasonal:
            for s in seasonal:
                summary.append(
                    f"\nNotable Pattern: {s['type']} alarms occur seasonally in "
                    f"{s['month']} (detected in {', '.join(map(str, s['years']))}). "
                    f"This {s['season']} pattern suggests {self.PATTERN_EXPLANATIONS['seasonal'].get(s['season'], 'seasonal factors')}."
                )

        recurring = patterns.get('recurring', [])
        if recurring:
            for r in recurring:
                summary.append(
                    f"\nRecurring Issue: {r['type']} alarms repeat approximately every "
                    f"{r['interval_days']} days. {self.PATTERN_EXPLANATIONS['recurring']}."
                )

        clusters = patterns.get('clusters', [])
        if len(clusters) > 1:
            summary.append(
                f"\nCascade Events: {len(clusters)} instances of multiple alarms within a week. "
                "This suggests related incidents or chain reaction events."
            )

        return '\n'.join(summary)

    def generate_recommendations_text(self):
        """Generate formatted recommendations for PDF"""
        if 'recommendations' not in self.analysis_results:
            self.generate_recommendations()

        recommendations = self.analysis_results['recommendations']

        if not recommendations:
            return "No specific recommendations. Continue routine maintenance schedule."

        # Sort by priority
        priority_order = {'CRITICAL': 0, 'HIGH': 1, 'MEDIUM': 2, 'LOW': 3}
        sorted_recs = sorted(recommendations, key=lambda x: priority_order.get(x['priority'], 4))

        text_parts = []
        for i, rec in enumerate(sorted_recs, 1):
            text_parts.append(f"{i}. [{rec['priority']}] {rec['title']}")
            text_parts.append(f"   {rec['description']}")
            text_parts.append(f"   Action: {rec['action']}")
            text_parts.append("")

        return '\n'.join(text_parts)


def analyze_alarms(alarms):
    """
    Main entry point for alarm analysis

    Args:
        alarms: List of alarm dicts

    Returns:
        Tuple of (summary_text, recommendations_text, full_analysis_dict)
    """
    analyzer = AlarmAnalyzer(alarms)

    # Run all analyses
    analyzer.analyze_frequency()
    analyzer.analyze_patterns()
    analyzer.analyze_severity_distribution()
    analyzer.generate_recommendations()

    # Generate text outputs
    summary = analyzer.generate_summary_text()
    recommendations = analyzer.generate_recommendations_text()

    return summary, recommendations, analyzer.analysis_results


# Example usage
if __name__ == '__main__':
    # Test with sample data
    test_alarms = [
        {'tank': 'DSL', 'type': 'HIGH WATER', 'date': '2025-10-03'},
        {'tank': 'DSL', 'type': 'OVERFILL', 'date': '2024-10-06'},
        {'tank': 'DSL', 'type': 'HIGH WATER', 'date': '2024-10-06'},
        {'tank': 'DSL', 'type': 'LOW LIMIT', 'date': '2025-09-18'},
        {'tank': 'DSL', 'type': 'HIGH WATER', 'date': '2023-10-04'},
    ]

    summary, recommendations, full_analysis = analyze_alarms(test_alarms)

    print("="*80)
    print("ALARM ANALYSIS SUMMARY")
    print("="*80)
    print(summary)
    print("\n" + "="*80)
    print("RECOMMENDATIONS")
    print("="*80)
    print(recommendations)
