import 'dart:async';
import 'package:flutter/material.dart';
import '../providers/vacancy_list_provider.dart';

class PollingProgressBar extends StatefulWidget {
  final PollingStatus status;
  final int pollIntervalSeconds;
  final DateTime? lastUpdatedAt;

  const PollingProgressBar({
    super.key,
    required this.status,
    required this.pollIntervalSeconds,
    this.lastUpdatedAt,
  });

  @override
  State<PollingProgressBar> createState() => _PollingProgressBarState();
}

class _PollingProgressBarState extends State<PollingProgressBar> {
  Timer? _tick;
  double _progress = 0.0;

  @override
  void initState() {
    super.initState();
    _tick = Timer.periodic(const Duration(seconds: 1), (_) {
      if (mounted && widget.status == PollingStatus.idle) {
        setState(_updateProgress);
      }
    });
  }

  void _updateProgress() {
    if (widget.lastUpdatedAt == null) return;
    final elapsed =
        DateTime.now().difference(widget.lastUpdatedAt!).inSeconds;
    _progress = (elapsed / widget.pollIntervalSeconds).clamp(0.0, 1.0);
  }

  @override
  void dispose() {
    _tick?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final primary = Theme.of(context).colorScheme.primary;

    if (widget.status == PollingStatus.polling) {
      return LinearProgressIndicator(
        minHeight: 2,
        backgroundColor: Colors.transparent,
        valueColor: AlwaysStoppedAnimation<Color>(primary),
      );
    }

    return LinearProgressIndicator(
      value: _progress,
      minHeight: 2,
      backgroundColor: Colors.transparent,
      valueColor: AlwaysStoppedAnimation<Color>(primary.withOpacity(0.3)),
    );
  }
}
