import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../providers/config_provider.dart';
import '../providers/settings_provider.dart';
// RemoteConfig used by _ModelDropdown

class SettingsScreen extends ConsumerStatefulWidget {
  const SettingsScreen({super.key});

  @override
  ConsumerState<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends ConsumerState<SettingsScreen> {
  late TextEditingController _urlController;
  late int _pollInterval;
  late bool _notifications;
  bool _saved = false;

  @override
  void initState() {
    super.initState();
    _urlController = TextEditingController();
    _pollInterval = 30;
    _notifications = true;
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final settings = ref.read(settingsProvider).valueOrNull;
    if (settings != null && _urlController.text.isEmpty) {
      _urlController.text = settings.apiUrl;
      _pollInterval = settings.pollIntervalSeconds;
      _notifications = settings.notificationsEnabled;
    }
  }

  @override
  void dispose() {
    _urlController.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    final notifier = ref.read(settingsProvider.notifier);
    await notifier.updateApiUrl(_urlController.text.trim());
    await notifier.updatePollInterval(_pollInterval);
    await notifier.updateNotifications(_notifications);
    if (mounted) {
      setState(() => _saved = true);
      Future.delayed(const Duration(seconds: 2), () {
        if (mounted) setState(() => _saved = false);
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;

    return Scaffold(
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(32),
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 560),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('Settings', style: Theme.of(context).textTheme.headlineSmall),
              const SizedBox(height: 32),

              // Backend URL
              _SectionLabel('Backend'),
              const SizedBox(height: 8),
              TextField(
                controller: _urlController,
                decoration: const InputDecoration(
                  labelText: 'API URL',
                  hintText: 'http://localhost:8080',
                  border: OutlineInputBorder(),
                  helperText: 'FastAPI server address',
                ),
                onChanged: (_) => setState(() => _saved = false),
              ),
              const SizedBox(height: 24),

              // Poll interval
              _SectionLabel('Polling'),
              const SizedBox(height: 4),
              Row(
                children: [
                  Text(
                    'Every $_pollInterval seconds',
                    style: Theme.of(context).textTheme.bodyMedium,
                  ),
                  const Spacer(),
                  Text(
                    '${(_pollInterval / 60).toStringAsFixed(0)} min',
                    style: Theme.of(context).textTheme.labelSmall?.copyWith(
                          color: cs.onSurfaceVariant,
                        ),
                  ),
                ],
              ),
              Slider(
                value: _pollInterval.toDouble(),
                min: 10,
                max: 300,
                divisions: 29,
                label: '${_pollInterval}s',
                onChanged: (v) =>
                    setState(() => _pollInterval = v.round()),
              ),
              const SizedBox(height: 16),

              // Notifications
              _SectionLabel('Notifications'),
              const SizedBox(height: 8),
              SwitchListTile(
                title: const Text('Windows toast on new vacancy'),
                subtitle: const Text('Shows a notification when RSS pipeline finds new matches'),
                value: _notifications,
                onChanged: (v) => setState(() => _notifications = v),
                contentPadding: EdgeInsets.zero,
              ),
              const SizedBox(height: 32),

              // AI Provider — model + effort (admin panel, read from /api/config)
              _SectionLabel('AI Provider'),
              const SizedBox(height: 12),
              const _AiProviderTile(),
              const SizedBox(height: 32),

              // Save button
              Row(
                children: [
                  FilledButton(
                    onPressed: _save,
                    child: const Text('Save'),
                  ),
                  const SizedBox(width: 12),
                  AnimatedOpacity(
                    opacity: _saved ? 1.0 : 0.0,
                    duration: const Duration(milliseconds: 300),
                    child: Row(
                      children: [
                        Icon(Icons.check_circle_outline,
                            size: 16, color: cs.primary),
                        const SizedBox(width: 4),
                        Text('Saved',
                            style: Theme.of(context)
                                .textTheme
                                .labelMedium
                                ?.copyWith(color: cs.primary)),
                      ],
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _SectionLabel extends StatelessWidget {
  final String label;

  const _SectionLabel(this.label);

  @override
  Widget build(BuildContext context) {
    return Text(
      label,
      style: Theme.of(context).textTheme.labelLarge?.copyWith(
            color: Theme.of(context).colorScheme.onSurfaceVariant,
            letterSpacing: 0.5,
          ),
    );
  }
}

// ── AI Provider tile — model dropdown + effort segmented control ──────────────

class _AiProviderTile extends ConsumerWidget {
  const _AiProviderTile();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final cs = Theme.of(context).colorScheme;
    final configAsync = ref.watch(remoteConfigProvider);

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: cs.surfaceContainer,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: cs.outlineVariant.withValues(alpha: 0.3)),
      ),
      child: configAsync.when(
        loading: () => const SizedBox(
            height: 40, child: Center(child: CircularProgressIndicator())),
        error: (e, _) => Text(
          'Unavailable — check backend: $e',
          style: Theme.of(context).textTheme.bodySmall?.copyWith(color: cs.error),
        ),
        data: (config) => Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Provider — switchable dropdown; analysis mode read-only
            _ProviderRow(config: config),
            const SizedBox(height: 8),
            _ConfigRow(label: 'Analysis mode', value: config.analysisMode),
            const Divider(height: 24),

            // Model — dropdown when supported, read-only label for Ollama
            Row(
              children: [
                _ConfigLabel('Model'),
                const Spacer(),
                const _RefreshModelsButton(),
              ],
            ),
            const SizedBox(height: 8),
            if (config.supportsModelSelection)
              _ModelDropdown(config: config)
            else
              Text(
                config.model.isNotEmpty ? config.model : '—',
                style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                      color: cs.onSurface,
                      fontWeight: FontWeight.w600,
                    ),
              ),

            // Effort — hidden for Ollama
            if (config.supportsEffort) ...[
              const SizedBox(height: 16),
              _ConfigLabel('Thinking effort'),
              const SizedBox(height: 4),
              Text(
                'Higher effort = more reasoning tokens, higher cost & latency',
                style: Theme.of(context)
                    .textTheme
                    .bodySmall
                    ?.copyWith(color: cs.onSurfaceVariant),
              ),
              const SizedBox(height: 10),
              _EffortControl(current: config.thinkingEffort),
            ],
          ],
        ),
      ),
    );
  }
}

class _ConfigLabel extends StatelessWidget {
  final String text;

  const _ConfigLabel(this.text);

  @override
  Widget build(BuildContext context) {
    return Text(
      text,
      style: Theme.of(context).textTheme.bodySmall?.copyWith(
            color: Theme.of(context).colorScheme.onSurfaceVariant,
          ),
    );
  }
}

class _ModelDropdown extends ConsumerWidget {
  final RemoteConfig config;

  const _ModelDropdown({required this.config});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final cs = Theme.of(context).colorScheme;
    final current = config.availableModels.contains(config.model)
        ? config.model
        : config.availableModels.firstOrNull;

    return DropdownButtonHideUnderline(
      child: DropdownButton<String>(
        value: current,
        isExpanded: true,
        borderRadius: BorderRadius.circular(8),
        style: Theme.of(context).textTheme.bodyMedium?.copyWith(
              color: cs.onSurface,
              fontWeight: FontWeight.w600,
            ),
        items: config.availableModels
            .map((m) => DropdownMenuItem(value: m, child: Text(m)))
            .toList(),
        onChanged: (m) {
          if (m != null) {
            ref.read(remoteConfigProvider.notifier).patchModel(m);
          }
        },
      ),
    );
  }
}

class _EffortControl extends ConsumerWidget {
  final String current;

  const _EffortControl({required this.current});

  static const _efforts = ['off', 'low', 'medium', 'high', 'xhigh', 'max'];
  static const _labels  = ['Off', 'Low', 'Med', 'High', 'xHigh', 'Max'];

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final selected = _efforts.contains(current) ? current : 'off';

    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: SegmentedButton<String>(
        segments: List.generate(
          _efforts.length,
          (i) => ButtonSegment<String>(
            value: _efforts[i],
            label: Text(_labels[i]),
          ),
        ),
        selected: {selected},
        onSelectionChanged: (s) {
          if (s.isNotEmpty) {
            ref.read(remoteConfigProvider.notifier).patchEffort(s.first);
          }
        },
        style: SegmentedButton.styleFrom(
          selectedBackgroundColor:
              Theme.of(context).colorScheme.primaryContainer,
        ),
      ),
    );
  }
}

class _RefreshModelsButton extends ConsumerStatefulWidget {
  const _RefreshModelsButton();

  @override
  ConsumerState<_RefreshModelsButton> createState() => _RefreshModelsButtonState();
}

class _RefreshModelsButtonState extends ConsumerState<_RefreshModelsButton> {
  bool _loading = false;

  Future<void> _refresh() async {
    setState(() => _loading = true);
    try {
      await ref.read(remoteConfigProvider.notifier).refreshModels();
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Model list refreshed'), duration: Duration(seconds: 2)),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Refresh failed: $e'), backgroundColor: Colors.red),
        );
      }
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Tooltip(
      message: 'Re-fetch available models from the provider (needed after ollama pull/rm)',
      child: TextButton.icon(
        onPressed: _loading ? null : _refresh,
        style: TextButton.styleFrom(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
          minimumSize: Size.zero,
          tapTargetSize: MaterialTapTargetSize.shrinkWrap,
          foregroundColor: cs.primary,
        ),
        icon: _loading
            ? const SizedBox(width: 12, height: 12, child: CircularProgressIndicator(strokeWidth: 2))
            : const Icon(Icons.refresh_rounded, size: 14),
        label: Text(_loading ? 'Refreshing…' : 'Refresh', style: Theme.of(context).textTheme.labelSmall),
      ),
    );
  }
}

class _ProviderRow extends ConsumerWidget {
  final RemoteConfig config;

  const _ProviderRow({required this.config});

  static const _labels = {
    'claude_api': 'Claude API (billed)',
    'ollama_api': 'Ollama (local)',
    'claude_cli': 'Claude CLI (\$0)',
  };

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final cs = Theme.of(context).colorScheme;
    // Fall back to a single-item list if backend didn't send valid_providers.
    final providers = config.validProviders.isNotEmpty
        ? config.validProviders
        : [config.llmProvider];
    final current =
        providers.contains(config.llmProvider) ? config.llmProvider : providers.first;

    return Row(
      children: [
        SizedBox(
          width: 120,
          child: Text(
            'Provider',
            style: Theme.of(context)
                .textTheme
                .bodySmall
                ?.copyWith(color: cs.onSurfaceVariant),
          ),
        ),
        Expanded(
          child: DropdownButtonHideUnderline(
            child: DropdownButton<String>(
              value: current,
              isExpanded: true,
              isDense: true,
              borderRadius: BorderRadius.circular(8),
              style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                    color: cs.onSurface,
                    fontWeight: FontWeight.w600,
                  ),
              items: providers
                  .map((p) => DropdownMenuItem(
                        value: p,
                        child: Text(_labels[p] ?? p),
                      ))
                  .toList(),
              onChanged: (p) {
                if (p != null && p != config.llmProvider) {
                  ref.read(remoteConfigProvider.notifier).patchProvider(p);
                }
              },
            ),
          ),
        ),
      ],
    );
  }
}

class _ConfigRow extends StatelessWidget {
  final String label;
  final String value;

  const _ConfigRow({required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Row(
      children: [
        SizedBox(
          width: 120,
          child: Text(
            label,
            style: Theme.of(context)
                .textTheme
                .bodySmall
                ?.copyWith(color: cs.onSurfaceVariant),
          ),
        ),
        Expanded(
          child: Text(
            value.isNotEmpty ? value : '—',
            style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                  fontWeight: FontWeight.w600,
                  color: cs.onSurface,
                ),
          ),
        ),
      ],
    );
  }
}
