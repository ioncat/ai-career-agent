import 'package:flutter/material.dart';
import '../models/health.dart';

class BackendStatusDot extends StatefulWidget {
  final HealthStatus status;

  const BackendStatusDot({super.key, required this.status});

  @override
  State<BackendStatusDot> createState() => _BackendStatusDotState();
}

class _BackendStatusDotState extends State<BackendStatusDot>
    with SingleTickerProviderStateMixin {
  late AnimationController _ctrl;
  late Animation<double> _anim;

  @override
  void initState() {
    super.initState();
    _ctrl = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1500),
    )..repeat(reverse: true);
    _anim = Tween<double>(begin: 0.5, end: 1.0).animate(_ctrl);
  }

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final (color, tooltip, animate) = switch (widget.status) {
      HealthStatus.online   => (const Color(0xFF4CAF50), 'Backend online', true),
      HealthStatus.offline  => (cs.error, 'Backend offline — check localhost:8080', false),
      HealthStatus.checking => (cs.outline, 'Checking...', true),
    };

    final dot = Container(
      width: 10,
      height: 10,
      decoration: BoxDecoration(shape: BoxShape.circle, color: color),
    );

    return Tooltip(
      message: tooltip,
      child: animate
          ? FadeTransition(opacity: _anim, child: dot)
          : dot,
    );
  }
}
