import 'dart:math' as math;
import 'package:flutter/material.dart';
import '../utils/active_status.dart';

/// Wraps any widget with a snake border animation + phase overlay
/// whenever [status] is an active processing status.
///
/// If status is not in [kActiveStatuses], renders [child] unchanged.
/// Add new statuses to active_status.dart — this widget updates automatically.
class ProcessingWrapper extends StatefulWidget {
  final String status;
  final Widget child;
  final double borderRadius;

  const ProcessingWrapper({
    super.key,
    required this.status,
    required this.child,
    this.borderRadius = 12,
  });

  @override
  State<ProcessingWrapper> createState() => _ProcessingWrapperState();
}

class _ProcessingWrapperState extends State<ProcessingWrapper>
    with SingleTickerProviderStateMixin {
  late AnimationController _ctrl;

  @override
  void initState() {
    super.initState();
    _ctrl = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 2200),
    )..repeat();
  }

  @override
  void didUpdateWidget(ProcessingWrapper old) {
    super.didUpdateWidget(old);
    if (isActiveStatus(widget.status) && !_ctrl.isAnimating) {
      _ctrl.repeat();
    } else if (!isActiveStatus(widget.status) && _ctrl.isAnimating) {
      _ctrl.stop();
    }
  }

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final label = kActiveStatuses[widget.status];
    if (label == null) return widget.child;

    final cs = Theme.of(context).colorScheme;

    return Stack(
      children: [
        widget.child,

        // Snake border animation
        Positioned.fill(
          child: IgnorePointer(
            child: AnimatedBuilder(
              animation: _ctrl,
              builder: (_, _) => CustomPaint(
                painter: _SnakePainter(
                  progress: _ctrl.value,
                  color: cs.primary,
                  radius: widget.borderRadius,
                ),
              ),
            ),
          ),
        ),

        // Phase overlay — semi-transparent, shows what's happening
        Positioned.fill(
          child: IgnorePointer(
            child: ClipRRect(
              borderRadius: BorderRadius.circular(widget.borderRadius),
              child: Container(
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    begin: Alignment.topCenter,
                    end: Alignment.bottomCenter,
                    colors: [
                      cs.surface.withValues(alpha: 0.0),
                      cs.surface.withValues(alpha: 0.72),
                    ],
                    stops: const [0.3, 1.0],
                  ),
                ),
                alignment: Alignment.bottomCenter,
                padding: const EdgeInsets.only(bottom: 14, left: 16, right: 16),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    SizedBox(
                      width: 11,
                      height: 11,
                      child: CircularProgressIndicator(
                        strokeWidth: 1.5,
                        color: cs.primary,
                      ),
                    ),
                    const SizedBox(width: 8),
                    Text(
                      label,
                      style: Theme.of(context).textTheme.labelSmall?.copyWith(
                            color: cs.primary,
                            fontWeight: FontWeight.w600,
                            letterSpacing: 0.1,
                          ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ],
    );
  }
}

// ─── Snake border painter ─────────────────────────────────────────────────────

class _SnakePainter extends CustomPainter {
  final double progress; // 0.0..1.0, repeating
  final Color color;
  final double radius;

  static const _snakeFraction = 0.28; // snake = 28% of perimeter
  static const _strokeWidth = 2.0;
  static const _steps = 20; // gradient segments

  const _SnakePainter({
    required this.progress,
    required this.color,
    required this.radius,
  });

  @override
  void paint(Canvas canvas, Size size) {
    if (size.isEmpty) return;

    final rrect = RRect.fromRectAndRadius(
      Rect.fromLTWH(
        _strokeWidth / 2,
        _strokeWidth / 2,
        size.width - _strokeWidth,
        size.height - _strokeWidth,
      ),
      Radius.circular(radius - 1),
    );
    final path = Path()..addRRect(rrect);
    final metric = path.computeMetrics().first;
    final total = metric.length;
    final snakeLen = total * _snakeFraction;
    final headPos = (progress * total) % total;

    for (int i = 0; i < _steps; i++) {
      final frac = i / _steps;
      final nextFrac = (i + 1) / _steps;

      final segStart = (headPos - snakeLen + frac * snakeLen + total) % total;
      final segEnd = (headPos - snakeLen + nextFrac * snakeLen + total) % total;

      // Opacity: 0 at tail → 1 at head
      final opacity = math.pow(frac, 1.5).toDouble();

      final paint = Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = _strokeWidth + frac * 0.8
        ..strokeCap = StrokeCap.round
        ..color = color.withValues(alpha: opacity * 0.9);

      if (segEnd >= segStart) {
        final extract = metric.extractPath(segStart, segEnd);
        canvas.drawPath(extract, paint);
      } else {
        // Wraps around the perimeter
        canvas.drawPath(metric.extractPath(segStart, total), paint);
        if (segEnd > 0) canvas.drawPath(metric.extractPath(0, segEnd), paint);
      }
    }
  }

  @override
  bool shouldRepaint(_SnakePainter old) =>
      old.progress != progress || old.color != color;
}
