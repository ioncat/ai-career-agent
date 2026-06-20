import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../providers/settings_provider.dart';

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
