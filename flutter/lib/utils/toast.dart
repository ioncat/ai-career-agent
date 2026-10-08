import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

/// App-wide toast, shown at the top of the window. Replaces the bottom
/// SnackBar: the owner's eyes are at the top of the screen, a bottom toast
/// went unnoticed (2026-10-08).
///
/// One host per root overlay keeps a stack of at most [_maxToasts]; the
/// newest is on top. Every toast has a close button; hovering pauses its
/// timer. An error toast stays until closed.
enum ToastKind {
  /// Routine confirmation ("ID copied", "Analysis queued").
  info,

  /// An event worth noticing (a vacancy moved folder, a pipeline event).
  notice,

  /// Something was off but handled ("settings refreshed").
  warning,

  /// A failure; stays until the user closes it.
  error,
}

const _maxToasts = 3;
const _infoBackground = Color(0xFF5F5C66);

Duration? _defaultDuration(ToastKind kind) => switch (kind) {
  ToastKind.info => const Duration(seconds: 3),
  ToastKind.notice => const Duration(seconds: 10),
  ToastKind.warning => const Duration(seconds: 6),
  ToastKind.error => null,
};

/// A shown toast; [dismiss] closes it early (e.g. "Preparing PDF..." once
/// the PDF is saved). Safe to call more than once.
class ToastHandle {
  final VoidCallback _dismiss;
  ToastHandle._(this._dismiss);
  void dismiss() => _dismiss();
}

/// Captures the overlay and theme up front, so a toast can be shown after an
/// `await` without touching a possibly unmounted `BuildContext`.
class Toaster {
  final _ToastHost _host;
  final ColorScheme _cs;

  Toaster._(this._host, this._cs);

  factory Toaster.of(BuildContext context) {
    final overlay = Overlay.of(context, rootOverlay: true);
    return Toaster._(_ToastHost.of(overlay), Theme.of(context).colorScheme);
  }

  ToastHandle show(
    String message, {
    ToastKind kind = ToastKind.info,
    Duration? duration,
    String? actionLabel,
    VoidCallback? onAction,
  }) {
    return _host.add(
      _ToastData(
        message: message,
        kind: kind,
        cs: _cs,
        duration: duration ?? _defaultDuration(kind),
        actionLabel: actionLabel,
        onAction: onAction,
      ),
    );
  }
}

ToastHandle showToast(
  BuildContext context,
  String message, {
  ToastKind kind = ToastKind.info,
  Duration? duration,
  String? actionLabel,
  VoidCallback? onAction,
}) => Toaster.of(context).show(
  message,
  kind: kind,
  duration: duration,
  actionLabel: actionLabel,
  onAction: onAction,
);

class _ToastData {
  final String message;
  final ToastKind kind;
  final ColorScheme cs;
  final Duration? duration;
  final String? actionLabel;
  final VoidCallback? onAction;
  final Key key = UniqueKey();

  _ToastData({
    required this.message,
    required this.kind,
    required this.cs,
    required this.duration,
    this.actionLabel,
    this.onAction,
  });
}

class _ToastHost {
  static final _hosts = Expando<_ToastHost>();

  final OverlayState _overlay;
  final _toasts = ValueNotifier<List<_ToastData>>(const []);
  OverlayEntry? _entry;

  // Hovering any toast pauses the whole stack: otherwise an older toast
  // expires above the hovered one, the stack shifts up and the hovered toast
  // slides out from under the cursor. The short delay on leave bridges the
  // gap between two toasts.
  final paused = ValueNotifier<bool>(false);
  final _hoveredKeys = <Key>{};
  Timer? _resume;

  void setHovered(Key key, bool hovered) {
    final changed = hovered ? _hoveredKeys.add(key) : _hoveredKeys.remove(key);
    if (!changed) return;
    _resume?.cancel();
    if (_hoveredKeys.isNotEmpty) {
      paused.value = true;
    } else {
      _resume = Timer(
        const Duration(milliseconds: 150),
        () => paused.value = false,
      );
    }
  }

  _ToastHost(this._overlay);

  static _ToastHost of(OverlayState overlay) =>
      _hosts[overlay] ??= _ToastHost(overlay);

  ToastHandle add(_ToastData data) {
    final next = [data, ..._toasts.value];
    _toasts.value = next.length > _maxToasts
        ? next.sublist(0, _maxToasts)
        : next;
    _ensureEntry();
    return ToastHandle._(() => remove(data));
  }

  void remove(_ToastData data) {
    if (!_toasts.value.contains(data)) return;
    _toasts.value = _toasts.value.where((t) => t != data).toList();
  }

  void _ensureEntry() {
    // Inserted once per overlay; `mounted` is false until the first frame,
    // so checking it would insert a second layer for a burst of toasts.
    if (_entry != null) return;
    _entry = OverlayEntry(
      builder: (_) => Positioned(
        top: 12,
        left: 16,
        right: 16,
        child: ValueListenableBuilder<List<_ToastData>>(
          valueListenable: _toasts,
          builder: (_, toasts, _) => Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              for (final t in toasts)
                _ToastView(
                  key: t.key,
                  data: t,
                  paused: paused,
                  onHover: (h) => setHovered(t.key, h),
                  onClose: () => remove(t),
                ),
            ],
          ),
        ),
      ),
    );
    _overlay.insert(_entry!);
  }
}

class _ToastView extends StatefulWidget {
  final _ToastData data;
  final ValueListenable<bool> paused;
  final ValueChanged<bool> onHover;
  final VoidCallback onClose;

  const _ToastView({
    super.key,
    required this.data,
    required this.paused,
    required this.onHover,
    required this.onClose,
  });

  @override
  State<_ToastView> createState() => _ToastViewState();
}

class _ToastViewState extends State<_ToastView>
    with SingleTickerProviderStateMixin {
  late final AnimationController _anim = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 180),
  )..forward();
  Timer? _timer;
  Duration? _remaining;
  DateTime? _startedAt;

  @override
  void initState() {
    super.initState();
    _remaining = widget.data.duration;
    widget.paused.addListener(_onPausedChanged);
    if (!widget.paused.value) _startTimer();
  }

  void _onPausedChanged() {
    if (widget.paused.value) {
      _pauseTimer();
    } else if (_timer == null) {
      _startTimer();
    }
  }

  void _startTimer() {
    final left = _remaining;
    if (left == null) return;
    _startedAt = DateTime.now();
    _timer = Timer(left, widget.onClose);
  }

  void _pauseTimer() {
    if (_timer == null || _startedAt == null || _remaining == null) return;
    _timer!.cancel();
    _timer = null;
    _remaining = _remaining! - DateTime.now().difference(_startedAt!);
    if (_remaining!.isNegative) _remaining = Duration.zero;
  }

  @override
  void dispose() {
    widget.paused.removeListener(_onPausedChanged);
    // A closed toast gets no exit event; release its hover so the rest of
    // the stack does not stay paused.
    widget.onHover(false);
    _timer?.cancel();
    _anim.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final d = widget.data;
    final cs = d.cs;
    final (Color bg, Color fg, Color actionColor) = switch (d.kind) {
      ToastKind.info => (_infoBackground, Colors.white, cs.secondaryContainer),
      ToastKind.notice => (
        cs.primaryContainer,
        cs.onPrimary,
        cs.secondaryContainer,
      ),
      ToastKind.warning => (Colors.orange.shade700, Colors.white, Colors.white),
      ToastKind.error => (cs.error, cs.onError, cs.onError),
    };
    return FadeTransition(
      opacity: _anim,
      child: SlideTransition(
        position: Tween(
          begin: const Offset(0, -0.3),
          end: Offset.zero,
        ).animate(CurvedAnimation(parent: _anim, curve: Curves.easeOut)),
        child: MouseRegion(
          onEnter: (_) => widget.onHover(true),
          onExit: (_) => widget.onHover(false),
          child: Center(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 560),
              child: Padding(
                padding: const EdgeInsets.only(bottom: 8),
                child: Material(
                  color: bg,
                  elevation: 6,
                  borderRadius: BorderRadius.circular(10),
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(16, 6, 4, 6),
                    child: Row(
                      children: [
                        Expanded(
                          child: Padding(
                            padding: const EdgeInsets.symmetric(vertical: 6),
                            child: Text(
                              d.message,
                              style: TextStyle(color: fg, fontSize: 14),
                            ),
                          ),
                        ),
                        if (d.actionLabel != null)
                          TextButton(
                            onPressed: () {
                              d.onAction?.call();
                              widget.onClose();
                            },
                            style: TextButton.styleFrom(
                              foregroundColor: actionColor,
                            ),
                            child: Text(
                              d.actionLabel!.toUpperCase(),
                              style: const TextStyle(
                                fontWeight: FontWeight.w700,
                              ),
                            ),
                          ),
                        IconButton(
                          tooltip: 'Close',
                          icon: Icon(Icons.close, size: 18, color: fg),
                          onPressed: widget.onClose,
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
