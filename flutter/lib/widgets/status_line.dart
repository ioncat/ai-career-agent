import 'dart:async';
import 'package:flutter/material.dart';
import '../providers/vacancy_list_provider.dart';

class StatusLine extends StatefulWidget {
  final PollingStatus status;
  final DateTime? lastUpdatedAt;
  final int pollIntervalSeconds;
  final int newCount;
  final String? errorMessage;

  const StatusLine({
    super.key,
    required this.status,
    required this.pollIntervalSeconds,
    this.lastUpdatedAt,
    this.newCount = 0,
    this.errorMessage,
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

  String get _text {
    switch (widget.status) {
      case PollingStatus.polling:
        return '⏳ Проверяем новые вакансии...';
      case PollingStatus.found:
        return '✨ Найдено ${widget.newCount} новые вакансии · только что';
      case PollingStatus.empty:
        return '✓ Нет новых вакансий · только что';
      case PollingStatus.error:
        return '⚠️ Не удалось получить данные · повтор через ${_secondsUntilNext}с';
      case PollingStatus.idle:
        if (widget.lastUpdatedAt == null) return '🔄 Ожидание...';
        final ago = _secondsAgo < 60
            ? '${_secondsAgo}с назад'
            : '${(_secondsAgo / 60).round()} мин назад';
        return '🔄 Обновлено: $ago · следующее через ${_secondsUntilNext}с';
    }
  }

  @override
  Widget build(BuildContext context) {
    return Text(
      _text,
      style: Theme.of(context).textTheme.labelMedium?.copyWith(
            color: Theme.of(context)
                .colorScheme
                .onSurface
                .withOpacity(0.55),
          ),
    );
  }
}
