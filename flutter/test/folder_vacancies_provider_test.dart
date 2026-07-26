import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:career_agent/models/vacancy.dart';
import 'package:career_agent/providers/vacancy_list_provider.dart';

// folderVacanciesProvider per-folder sort (2026-07-26, explicit user ask):
// Analyzed/Processed rank by our own last action (updated_at — analysis
// finished / CV+cover generated), not by how recently the JD was posted.
// Inbox/Applied/Archive keep the backend's default published_at order
// (JD freshness on the market matters more there than when we touched it).

String _utc(DateTime local) => local.toUtc().toIso8601String();

VacancyListItem _item(
  int id, {
  required String stage,
  String? publishedAt,
  String? updatedAt,
}) =>
    VacancyListItem(
      id: id,
      role: 'Role $id',
      company: 'Company $id',
      site: 'djinni',
      url: 'https://example.com/$id',
      status: stage,
      stage: stage,
      publishedAt: publishedAt,
      updatedAt: updatedAt,
    );

class _FakeVacancyListNotifier extends VacancyListNotifier {
  final List<VacancyListItem> _items;
  _FakeVacancyListNotifier(this._items);

  @override
  Future<PollingState> build() async {
    // Skip the real build() entirely (settings/timer/cache) — just seed state.
    return PollingState(vacancies: _items, status: PollingStatus.idle);
  }
}

ProviderContainer _containerFor(List<VacancyListItem> items) {
  final container = ProviderContainer(
    overrides: [
      vacancyListProvider.overrideWith(() => _FakeVacancyListNotifier(items)),
    ],
  );
  addTearDown(container.dispose);
  return container;
}

void main() {
  test('analyzed folder sorts by updated_at descending, not published_at', () async {
    final now = DateTime.now();
    final items = [
      // Published newest-first, but analyzed (updated) in the opposite order.
      _item(1, stage: 'analyzed', publishedAt: _utc(now), updatedAt: _utc(now.subtract(const Duration(hours: 3)))),
      _item(2, stage: 'analyzed', publishedAt: _utc(now.subtract(const Duration(days: 1))), updatedAt: _utc(now)),
    ];
    final container = _containerFor(items);
    await container.read(vacancyListProvider.future);

    final result = container.read(folderVacanciesProvider('analyzed'));
    expect(result.map((v) => v.id).toList(), [2, 1]); // id 2 updated most recently
  });

  test('processed folder sorts by updated_at descending too', () async {
    final now = DateTime.now();
    final items = [
      _item(10, stage: 'processed', updatedAt: _utc(now.subtract(const Duration(hours: 5)))),
      _item(11, stage: 'processed', updatedAt: _utc(now)),
      _item(12, stage: 'processed', updatedAt: _utc(now.subtract(const Duration(hours: 1)))),
    ];
    final container = _containerFor(items);
    await container.read(vacancyListProvider.future);

    final result = container.read(folderVacanciesProvider('processed'));
    expect(result.map((v) => v.id).toList(), [11, 12, 10]);
  });

  test('inbox folder keeps the backend-provided order (no re-sort)', () async {
    final now = DateTime.now();
    final items = [
      // Backend order is published_at DESC — deliberately NOT re-sorted here
      // by updated_at, which would put id 21 first if it were.
      _item(20, stage: 'inbox', publishedAt: _utc(now), updatedAt: _utc(now.subtract(const Duration(hours: 2)))),
      _item(21, stage: 'inbox', publishedAt: _utc(now.subtract(const Duration(hours: 1))), updatedAt: _utc(now)),
    ];
    final container = _containerFor(items);
    await container.read(vacancyListProvider.future);

    final result = container.read(folderVacanciesProvider('inbox'));
    expect(result.map((v) => v.id).toList(), [20, 21]); // unchanged from input order
  });

  test('applied and archive folders are also left in backend order', () async {
    final now = DateTime.now();
    final applied = [
      _item(30, stage: 'applied', updatedAt: _utc(now.subtract(const Duration(hours: 2)))),
      _item(31, stage: 'applied', updatedAt: _utc(now)),
    ];
    final archive = [
      _item(40, stage: 'archive', updatedAt: _utc(now.subtract(const Duration(hours: 2)))),
      _item(41, stage: 'archive', updatedAt: _utc(now)),
    ];
    final container = _containerFor([...applied, ...archive]);
    await container.read(vacancyListProvider.future);

    expect(container.read(folderVacanciesProvider('applied')).map((v) => v.id).toList(), [30, 31]);
    expect(container.read(folderVacanciesProvider('archive')).map((v) => v.id).toList(), [40, 41]);
  });

  test('items with a null updated_at sort to the end within an updated_at-sorted folder', () async {
    final now = DateTime.now();
    final items = [
      _item(50, stage: 'analyzed', updatedAt: null),
      _item(51, stage: 'analyzed', updatedAt: _utc(now)),
    ];
    final container = _containerFor(items);
    await container.read(vacancyListProvider.future);

    final result = container.read(folderVacanciesProvider('analyzed'));
    expect(result.map((v) => v.id).toList(), [51, 50]);
  });
}
