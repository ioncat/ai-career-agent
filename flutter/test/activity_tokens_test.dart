import 'package:flutter_test/flutter_test.dart';
import 'package:career_agent/models/vacancy.dart';

ActivityEntry _e(Map<String, dynamic> extra) => ActivityEntry.fromJson({
  'phase': 'p1p2',
  'provider': 'claude_cli',
  'model': 'sonnet',
  'elapsed_ms': 1000,
  'created_at': '2026-10-09T10:00:00Z',
  ...extra,
});

void main() {
  test('CLI row with an estimate shows ~input and unknown output', () {
    final e = _e({
      'input_tokens': 0,
      'output_tokens': 0,
      'profile_tokens': 6000,
      'prompt_tokens': 4000,
      'user_tokens': 2300,
      'input_tokens_estimate': 12300,
      'input_is_estimate': true,
    });
    expect(e.tokensText, '~12.3k→?');
    expect(e.tokensHint, contains('Estimate'));
    expect(e.tokensHint, contains('profile 6.0k'));
  });

  test('estimate flagged but zero shows a dash', () {
    final e = _e({'input_tokens_estimate': 0, 'input_is_estimate': true});
    expect(e.tokensText, '—');
    expect(e.tokensHint, isNull);
  });

  test('exact usage shows in→out with no hint', () {
    final e = _e({
      'provider': 'claude_api',
      'input_tokens': 15000,
      'output_tokens': 800,
      'input_tokens_estimate': 14000,
      'input_is_estimate': false,
    });
    expect(e.tokensText, '15.0k→800');
    expect(e.tokensHint, isNull);
  });

  test('old CLI row without any numbers shows a dash', () {
    expect(_e({}).tokensText, '—');
  });
}
