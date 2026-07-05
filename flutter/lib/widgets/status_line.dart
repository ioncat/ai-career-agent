import 'dart:async';
import 'package:flutter/material.dart';
import '../providers/vacancy_list_provider.dart';

class StatusLine extends StatefulWidget {
  final PollingStatus status;
  final DateTime? lastUpdatedAt;
  final int pollIntervalSeconds;
  final int newCount;
  final String? errorMessage;
  final bool fromCache;

  const StatusLine({
    super.key,
    required this.status,
    required this.pollIntervalSeconds,
    this.lastUpdatedAt,
    this.newCount = 0,
    this.errorMessage,
    this.fromCache = false,
  });

  @override
  State<StatusLine> createState() => _StatusLineState();
}

class _StatusLineState extends State<StatusLine> {
  Timer? _tick;
  int _secondsAgo = 0;
  int _secondsUntilNext = 0;

  @override
  void initState() {
    super.initState();
    _update();
    _tick = Timer.periodic(const Duration(seconds: 1), (_) {
      if (mounted) setState(_update);
    });
  }

  void _update() {
    final now = DateTime.now();
    if (widget.lastUpdatedAt != null) {
      _secondsAgo = now.difference(widget.lastUpdatedAt!).inSeconds;
      _secondsUntilNext =
          (widget.pollIntervalSeconds - _secondsAgo).clamp(0, widget.pollIntervalSeconds);
    }
  }

  @override
  void dispose() {
    _tick?.cancel();
    super.dispose();
  }

  String _ago(int seconds) {
    if (seconds < 60) return '${seconds}s ago';
    if (seconds < 3600) return '${(seconds / 60).round()}min ago';
    return '${(seconds / 3600).round()}h ago';
  }

  String get _text {
    if (widget.fromCache && widget.status == PollingStatus.polling) {
      if (widget.lastUpdatedAt == null) return '📦 Loading from cache...';
      return '📦 Offline · cache from ${_ago(_secondsAgo)} · reconnecting...';
    }
    switch (widget.status) {
      case PollingStatus.polling:
        return '⏳ Checking for new vacancies...';
      case PollingStatus.found:
        final n = widget.newCount;
        return '✨ Found $n new ${n == 1 ? 'vacancy' : 'vacancies'} · just now';
      case PollingStatus.empty:
        return '✓ No new vacancies · just now';
      case PollingStatus.error:
        if (widget.fromCache) {
          if (widget.lastUpdatedAt == null) return '📦 Offline · no cache';
          return '📦 Offline · cache from ${_ago(_secondsAgo)}';
        }
        return '⚠️ Failed to get data · retry in ${_secondsUntilNext}s';
      case PollingStatus.idle:
        if (widget.lastUpdatedAt == null) return '🔄 Waiting...';
        return '🔄 Updated ${_ago(_secondsAgo)} · next in ${_secondsUntilNext}s';
    }
  }

  @override
  Widget build(BuildContext context) {
    return Text(
      _text,
      style: Theme.of(context).textTheme.labelMedium?.copyWith(
            color: widget.fromCache && widget.status != PollingStatus.idle
                ? Theme.of(context).colorScheme.outline
                : Theme.of(context).colorScheme.secondary,
          ),
    );
  }
}
