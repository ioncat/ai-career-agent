// Per-phase LLM routing UI (EPIC-27) — parameterized clone of
// SettingsScreen's _AiProviderTile: same provider/model/effort shape, applied
// per phase instead of globally. Each phase independently follows the global
// default (config_provider.dart) until explicitly pinned here.

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../providers/phase_config_provider.dart';

/// Runs a phase config_provider patch and surfaces drift/failure to the user.
/// Same contract as settings_screen.dart's _patchConfigAndReport.
Future<void> _patchPhaseAndReport(BuildContext context, Future<void> Function() patch) async {
  try {
    await patch();
  } on ConfigDriftException catch (e) {
    if (context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('$e — settings refreshed'), backgroundColor: Colors.orange.shade700),
      );
    }
  } catch (e) {
    if (context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Failed to update: $e'), backgroundColor: Colors.red),
      );
    }
  }
}

/// Collapsible "Advanced: Per-Phase Routing" section — one card per pipeline
/// phase. Meant to sit below SettingsScreen's existing "AI Provider" block.
class PhaseRoutingSection extends ConsumerStatefulWidget {
  const PhaseRoutingSection({super.key});

  @override
  ConsumerState<PhaseRoutingSection> createState() => _PhaseRoutingSectionState();
}

class _PhaseRoutingSectionState extends ConsumerState<PhaseRoutingSection> {
  bool _expanded = false;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        InkWell(
          onTap: () => setState(() => _expanded = !_expanded),
          borderRadius: BorderRadius.circular(8),
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: 4),
            child: Row(
              children: [
                Icon(
                  _expanded ? Icons.expand_less_rounded : Icons.expand_more_rounded,
                  size: 18,
                  color: cs.onSurfaceVariant,
                ),
                const SizedBox(width: 4),
                Text(
                  'Advanced: Per-Phase Routing',
                  style: Theme.of(context).textTheme.labelLarge?.copyWith(
                        color: cs.onSurfaceVariant,
                        letterSpacing: 0.5,
                      ),
                ),
              ],
            ),
          ),
        ),
        if (_expanded) ...[
          const SizedBox(height: 8),
          Text(
            'Override provider/model/effort for individual pipeline phases. '
            'Unpinned phases follow the AI Provider setting above.',
            style: Theme.of(context).textTheme.bodySmall?.copyWith(color: cs.onSurfaceVariant),
          ),
          const SizedBox(height: 12),
          for (final phase in kPhaseOrder) ...[
            PhaseLlmConfigTile(phase: phase),
            const SizedBox(height: 8),
          ],
        ],
      ],
    );
  }
}

class PhaseLlmConfigTile extends ConsumerWidget {
  final String phase;

  const PhaseLlmConfigTile({super.key, required this.phase});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final cs = Theme.of(context).colorScheme;
    final phasesAsync = ref.watch(phaseConfigProvider);

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: cs.surfaceContainer,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: cs.outlineVariant.withValues(alpha: 0.3)),
      ),
      child: phasesAsync.when(
        loading: () => const SizedBox(height: 32, child: Center(child: CircularProgressIndicator(strokeWidth: 2))),
        error: (e, _) => Text(
          'Unavailable — check backend: $e',
          style: Theme.of(context).textTheme.bodySmall?.copyWith(color: cs.error),
        ),
        data: (phases) {
          final config = phases[phase];
          if (config == null) {
            return Text('Unknown phase: $phase', style: Theme.of(context).textTheme.bodySmall);
          }
          return Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(
                      kPhaseLabels[phase] ?? phase,
                      style: Theme.of(context).textTheme.bodyMedium?.copyWith(fontWeight: FontWeight.w600),
                    ),
                  ),
                  if (config.isOverride)
                    _ResetButton(phase: phase)
                  else
                    Text(
                      'Using default',
                      style: Theme.of(context).textTheme.labelSmall?.copyWith(
                            color: cs.onSurfaceVariant.withValues(alpha: 0.7),
                            fontStyle: FontStyle.italic,
                          ),
                    ),
                ],
              ),
              const SizedBox(height: 10),
              _PhaseProviderRow(phase: phase, config: config),
              const SizedBox(height: 8),
              if (config.supportsModelSelection)
                _PhaseModelDropdown(phase: phase, config: config)
              else
                Text(
                  config.model.isNotEmpty ? config.model : '—',
                  style: Theme.of(context).textTheme.bodyMedium?.copyWith(fontWeight: FontWeight.w600),
                ),
              if (config.supportsEffort) ...[
                const SizedBox(height: 10),
                _PhaseEffortControl(phase: phase, current: config.thinkingEffort),
              ],
            ],
          );
        },
      ),
    );
  }
}

class _ResetButton extends ConsumerWidget {
  final String phase;
  const _ResetButton({required this.phase});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final cs = Theme.of(context).colorScheme;
    return TextButton.icon(
      onPressed: () => _patchPhaseAndReport(
        context,
        () => ref.read(phaseConfigProvider.notifier).resetToDefault(phase),
      ),
      style: TextButton.styleFrom(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
        minimumSize: Size.zero,
        tapTargetSize: MaterialTapTargetSize.shrinkWrap,
        foregroundColor: cs.onSurfaceVariant,
      ),
      icon: const Icon(Icons.restart_alt_rounded, size: 14),
      label: Text('Reset to default', style: Theme.of(context).textTheme.labelSmall),
    );
  }
}

class _PhaseProviderRow extends ConsumerWidget {
  final String phase;
  final PhaseConfig config;
  const _PhaseProviderRow({required this.phase, required this.config});

  static const _labels = {
    'claude_api': 'Claude API (billed)',
    'ollama_api': 'Ollama (local)',
    'claude_cli': 'Claude CLI (\$0)',
  };
  static const _allProviders = ['claude_api', 'ollama_api', 'claude_cli'];

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final cs = Theme.of(context).colorScheme;
    final current = _allProviders.contains(config.provider) ? config.provider : _allProviders.first;

    return Row(
      children: [
        SizedBox(
          width: 90,
          child: Text('Provider', style: Theme.of(context).textTheme.bodySmall?.copyWith(color: cs.onSurfaceVariant)),
        ),
        Expanded(
          child: DropdownButtonHideUnderline(
            child: DropdownButton<String>(
              value: current,
              isExpanded: true,
              isDense: true,
              borderRadius: BorderRadius.circular(8),
              style: Theme.of(context).textTheme.bodyMedium?.copyWith(color: cs.onSurface, fontWeight: FontWeight.w600),
              items: _allProviders.map((p) => DropdownMenuItem(value: p, child: Text(_labels[p] ?? p))).toList(),
              onChanged: (p) {
                if (p != null && p != config.provider) {
                  _patchPhaseAndReport(
                    context,
                    () => ref.read(phaseConfigProvider.notifier).patchProvider(phase, p),
                  );
                }
              },
            ),
          ),
        ),
      ],
    );
  }
}

class _PhaseModelDropdown extends ConsumerWidget {
  final String phase;
  final PhaseConfig config;
  const _PhaseModelDropdown({required this.phase, required this.config});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final cs = Theme.of(context).colorScheme;
    final saved = config.availableModels.contains(config.model);
    final current = saved ? config.model : config.availableModels.firstOrNull;

    if (!saved && current != null) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        _patchPhaseAndReport(
          context,
          () => ref.read(phaseConfigProvider.notifier).patchModel(phase, current),
        );
      });
    }

    return DropdownButtonHideUnderline(
      child: DropdownButton<String>(
        value: current,
        isExpanded: true,
        isDense: true,
        borderRadius: BorderRadius.circular(8),
        style: Theme.of(context).textTheme.bodyMedium?.copyWith(color: cs.onSurface, fontWeight: FontWeight.w600),
        items: config.availableModels.map((m) => DropdownMenuItem(value: m, child: Text(m))).toList(),
        onChanged: (m) {
          if (m != null) {
            _patchPhaseAndReport(
              context,
              () => ref.read(phaseConfigProvider.notifier).patchModel(phase, m),
            );
          }
        },
      ),
    );
  }
}

class _PhaseEffortControl extends ConsumerWidget {
  final String phase;
  final String current;
  const _PhaseEffortControl({required this.phase, required this.current});

  static const _efforts = ['off', 'low', 'medium', 'high', 'xhigh', 'max'];
  static const _labels = ['Off', 'Low', 'Med', 'High', 'xHigh', 'Max'];

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final selected = _efforts.contains(current) ? current : 'off';
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: SegmentedButton<String>(
        segments: List.generate(
          _efforts.length,
          (i) => ButtonSegment<String>(value: _efforts[i], label: Text(_labels[i])),
        ),
        selected: {selected},
        onSelectionChanged: (s) {
          if (s.isNotEmpty) {
            _patchPhaseAndReport(
              context,
              () => ref.read(phaseConfigProvider.notifier).patchEffort(phase, s.first),
            );
          }
        },
        style: SegmentedButton.styleFrom(selectedBackgroundColor: Theme.of(context).colorScheme.primaryContainer),
      ),
    );
  }
}
