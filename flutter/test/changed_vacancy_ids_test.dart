import 'package:flutter_test/flutter_test.dart';
import 'package:career_agent/models/vacancy.dart';
import 'package:career_agent/providers/vacancy_list_provider.dart';

VacancyListItem _v(int id, String status, String updated) =>
    VacancyListItem.fromJson({
      'id': id,
      'title': 'PM',
      'company': 'Acme',
      'site': 'dou',
      'url': 'https://example.com/$id',
      'status': status,
      'updated_at': updated,
    });

void main() {
  test('a status change marks the vacancy as changed', () {
    final ids = changedVacancyIds(
      [_v(1, 'analyzing', 't1')],
      [_v(1, 'analyzed', 't2')],
    );
    expect(ids, {1});
  });

  test('an updated_at change alone marks it as changed', () {
    expect(
      changedVacancyIds([_v(1, 'analyzed', 't1')], [_v(1, 'analyzed', 't2')]),
      {1},
    );
  });

  test('an unchanged vacancy and a brand-new one are not marked', () {
    final ids = changedVacancyIds(
      [_v(1, 'analyzed', 't1')],
      [_v(1, 'analyzed', 't1'), _v(2, 'fetched', 't1')],
    );
    expect(ids, isEmpty);
  });

  test('the first poll (no previous list) marks nothing', () {
    expect(changedVacancyIds(const [], [_v(1, 'analyzed', 't1')]), isEmpty);
  });
}
