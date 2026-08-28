import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../providers/settings_provider.dart';
import '../repositories/vacancy_repository.dart';

/// Primary-tag distribution across all vacancies. Tags are stored
/// non-exclusive in the DB (a vacancy can carry several, e.g. igaming +
/// mobile — see core/vacancy_tags.py), but this screen picks one "primary"
/// tag per vacancy via _kPriority so the chart sums to the total instead of
/// overlapping — a clean single picture of what the market is mostly made
/// of, which is what this screen is for.
// Mirrors core/vacancy_tags.py PRIORITY — kept as plain Dart here since this
// screen can't import the Python taxonomy module directly. Update alongside
// any change to that list.
const _kPriority = [
  'deftech', 'igaming', 'fintech', 'studio', 'mobile', 'b2b_saas', 'outsourcing',
];

String? _primaryTag(List<String> tags) {
  final tagSet = tags.toSet();
  for (final cat in _kPriority) {
    if (tagSet.contains(cat)) return cat;
  }
  return tags.isNotEmpty ? tags.first : null;
}

class AnalyticsScreen extends ConsumerStatefulWidget {
  const AnalyticsScreen({super.key});

  @override
  ConsumerState<AnalyticsScreen> createState() => _AnalyticsScreenState();
}

class _AnalyticsScreenState extends ConsumerState<AnalyticsScreen> {
  bool _loaded = false;
  bool _loading = false;
  Object? _error;
  Map<String, int> _primaryCounts = {};
  int _total = 0;
  int _untagged = 0;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (!_loaded && !_loading) {
      _load();
    }
  }

  Future<void> _load() async {
    final settings = ref.read(settingsProvider).valueOrNull;
    if (settings == null) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final repo = VacancyRepository(baseUrl: settings.apiUrl);
      final vacancies = await repo.listVacancies(limit: 5000);
      final primaryCounts = <String, int>{};
      var untagged = 0;
      for (final v in vacancies) {
        final primary = _primaryTag(v.tags);
        if (primary == null) {
          untagged++;
        } else {
          primaryCounts[primary] = (primaryCounts[primary] ?? 0) + 1;
        }
      }
      if (!mounted) return;
      setState(() {
        _primaryCounts = primaryCounts;
        _total = vacancies.length;
        _untagged = untagged;
        _loaded = true;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e;
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(32),
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 640),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Text('Analytics', style: Theme.of(context).textTheme.headlineSmall),
                  IconButton(
                    tooltip: 'Refresh',
                    icon: const Icon(Icons.refresh),
                    onPressed: _loading ? null : _load,
                  ),
                ],
              ),
              const SizedBox(height: 24),
              if (_loading && !_loaded)
                const Padding(
                  padding: EdgeInsets.symmetric(vertical: 40),
                  child: Center(child: CircularProgressIndicator()),
                )
              else if (_error != null)
                Text(
                  'Failed to load: $_error',
                  style: TextStyle(color: Theme.of(context).colorScheme.error),
                )
              else
                _TagChart(
                  tagCounts: _primaryCounts,
                  total: _total,
                  untagged: _untagged,
                ),
            ],
          ),
        ),
      ),
    );
  }
}

class _TagChart extends StatelessWidget {
  final Map<String, int> tagCounts;
  final int total;
  final int untagged;

  const _TagChart({required this.tagCounts, required this.total, required this.untagged});

  static const _palette = [
    Color(0xFF6750A4), Color(0xFF386A20), Color(0xFF8C4A2F),
    Color(0xFF006874), Color(0xFF984061), Color(0xFF7C5800),
    Color(0xFF4A6363), Color(0xFF5C5D72),
  ];

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;

    if (total == 0) {
      return Text('No vacancies loaded yet.', style: TextStyle(color: cs.onSurfaceVariant));
    }

    final entries = tagCounts.entries.toList()
      ..sort((a, b) => b.value.compareTo(a.value));
    final maxCount = entries.isEmpty
        ? 1
        : [entries.first.value, untagged].reduce((a, b) => a > b ? a : b);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          '$total vacancies · one primary tag each, bars sum to $total',
          style: TextStyle(fontSize: 12, color: cs.onSurfaceVariant),
        ),
        const SizedBox(height: 20),
        for (var i = 0; i < entries.length; i++) ...[
          _BarRow(
            label: entries[i].key,
            count: entries[i].value,
            total: total,
            maxCount: maxCount,
            color: _palette[i % _palette.length],
          ),
          const SizedBox(height: 10),
        ],
        if (untagged > 0) ...[
          const SizedBox(height: 6),
          Divider(color: cs.outlineVariant.withValues(alpha: 0.3)),
          const SizedBox(height: 16),
          _BarRow(
            label: 'untagged',
            count: untagged,
            total: total,
            maxCount: maxCount,
            color: cs.onSurfaceVariant.withValues(alpha: 0.35),
          ),
        ],
      ],
    );
  }
}

// Mirrors the category intent from core/vacancy_tags.py — kept as plain
// text here since Dart can't import the Python taxonomy module directly.
// Update alongside any change to that file's _TAXONOMY comments.
const _kTagDescriptions = {
  'igaming': 'Gambling/betting products: casino, sportsbook, betting platforms.',
  'deftech': 'Defense/military technology: UAV, drones, defense systems.',
  'mobile': 'Mobile-native product: iOS/Android app.',
  'outsourcing': 'Client-services company (agency/outstaff/consulting) building for others, not its own product.',
  'b2b_saas': 'B2B SaaS platform or product.',
  'studio': 'Game development studio building its own games.',
  'fintech': 'Financial technology: payments, banking, crypto.',
  'untagged': 'JD text didn\'t match any known category keyword.',
};

class _BarRow extends StatelessWidget {
  final String label;
  final int count;
  final int total;
  final int maxCount;
  final Color color;

  const _BarRow({
    required this.label,
    required this.count,
    required this.total,
    required this.maxCount,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final pct = total == 0 ? 0.0 : count / total * 100;
    final fraction = maxCount == 0 ? 0.0 : count / maxCount;

    return Row(
      crossAxisAlignment: CrossAxisAlignment.center,
      children: [
        SizedBox(
          width: 110,
          child: Tooltip(
            message: _kTagDescriptions[label] ?? label,
            waitDuration: const Duration(milliseconds: 300),
            child: Text(
              label,
              style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600),
              overflow: TextOverflow.ellipsis,
            ),
          ),
        ),
        Expanded(
          child: LayoutBuilder(
            builder: (context, constraints) {
              return Stack(
                children: [
                  Container(
                    height: 22,
                    decoration: BoxDecoration(
                      color: cs.surfaceContainerHighest,
                      borderRadius: BorderRadius.circular(4),
                    ),
                  ),
                  Container(
                    height: 22,
                    width: constraints.maxWidth * fraction.clamp(0.02, 1.0),
                    decoration: BoxDecoration(
                      color: color,
                      borderRadius: BorderRadius.circular(4),
                    ),
                  ),
                ],
              );
            },
          ),
        ),
        const SizedBox(width: 10),
        SizedBox(
          width: 80,
          child: Text(
            '$count (${pct.toStringAsFixed(1)}%)',
            style: TextStyle(fontSize: 12, color: cs.onSurfaceVariant),
            textAlign: TextAlign.right,
          ),
        ),
      ],
    );
  }
}
