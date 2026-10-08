import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:career_agent/utils/toast.dart';

late BuildContext _ctx;

Future<void> _pumpApp(WidgetTester tester) async {
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: Builder(
          builder: (context) {
            _ctx = context;
            return const SizedBox.expand();
          },
        ),
      ),
    ),
  );
}

void main() {
  testWidgets('shows at the top of the window', (tester) async {
    await _pumpApp(tester);
    showToast(_ctx, 'Hello');
    await tester.pumpAndSettle();
    final top = tester.getTopLeft(find.text('Hello')).dy;
    expect(top, lessThan(100));
  });

  testWidgets('info hides after its duration', (tester) async {
    await _pumpApp(tester);
    showToast(_ctx, 'Routine');
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.text('Routine'), findsOneWidget);
    await tester.pump(const Duration(seconds: 3));
    await tester.pump();
    expect(find.text('Routine'), findsNothing);
  });

  testWidgets('error stays until closed', (tester) async {
    await _pumpApp(tester);
    showToast(_ctx, 'Boom', kind: ToastKind.error);
    await tester.pump(const Duration(minutes: 5));
    expect(find.text('Boom'), findsOneWidget);
    await tester.tap(find.byTooltip('Close'));
    await tester.pump();
    expect(find.text('Boom'), findsNothing);
  });

  testWidgets('action runs and closes the toast', (tester) async {
    await _pumpApp(tester);
    var tapped = false;
    showToast(
      _ctx,
      'Moved',
      kind: ToastKind.notice,
      actionLabel: 'Show in Inbox',
      onAction: () => tapped = true,
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('SHOW IN INBOX'));
    await tester.pump();
    expect(tapped, isTrue);
    expect(find.text('Moved'), findsNothing);
  });

  testWidgets('keeps at most three, newest first', (tester) async {
    await _pumpApp(tester);
    for (var i = 1; i <= 4; i++) {
      showToast(_ctx, 'T$i', kind: ToastKind.error);
    }
    await tester.pumpAndSettle();
    expect(find.text('T1'), findsNothing);
    expect(
      tester.getTopLeft(find.text('T4')).dy,
      lessThan(tester.getTopLeft(find.text('T2')).dy),
    );
  });

  testWidgets('handle dismiss closes it early', (tester) async {
    await _pumpApp(tester);
    final h = showToast(
      _ctx,
      'Preparing',
      duration: const Duration(minutes: 1),
    );
    await tester.pumpAndSettle();
    h.dismiss();
    h.dismiss();
    await tester.pump();
    expect(find.text('Preparing'), findsNothing);
  });

  testWidgets('hovering a lower toast pauses the whole stack', (tester) async {
    await _pumpApp(tester);
    showToast(_ctx, 'Older');
    await tester.pump(const Duration(seconds: 1));
    showToast(_ctx, 'Newer');
    await tester.pumpAndSettle();
    final mouse = await tester.createGesture(kind: PointerDeviceKind.mouse);
    await mouse.addPointer(location: tester.getCenter(find.text('Older')));
    await tester.pump();
    await tester.pump(const Duration(seconds: 10));
    expect(find.text('Older'), findsOneWidget);
    expect(find.text('Newer'), findsOneWidget);
    await mouse.moveTo(const Offset(5, 590));
    await tester.pump(const Duration(milliseconds: 200));
    await tester.pump(const Duration(seconds: 4));
    await tester.pump();
    expect(find.text('Older'), findsNothing);
    expect(find.text('Newer'), findsNothing);
    await mouse.removePointer();
  });
}
