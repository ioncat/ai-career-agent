import 'dart:convert';
import 'package:http/http.dart' as http;
import '../models/vacancy.dart';

class VacancyRepository {
  final String baseUrl;

  const VacancyRepository({required this.baseUrl});

  Future<List<VacancyListItem>> listVacancies({
    String? status,
    String? since,
  }) async {
    final params = <String, String>{};
    if (status != null) params['status'] = status;
    if (since != null) params['since'] = since;

    final uri = Uri.parse('$baseUrl/api/vacancies')
        .replace(queryParameters: params.isNotEmpty ? params : null);

    final response = await http.get(uri).timeout(const Duration(seconds: 10));
    if (response.statusCode != 200) {
      throw Exception('Failed to load vacancies: ${response.statusCode}');
    }

    final List<dynamic> data = jsonDecode(response.body) as List<dynamic>;
    return data
        .map((e) => VacancyListItem.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<VacancyAnalysis> getAnalysis(int vacancyId) async {
    final uri = Uri.parse('$baseUrl/api/vacancies/$vacancyId/analysis');
    final response = await http.get(uri).timeout(const Duration(seconds: 10));
    if (response.statusCode == 404) throw Exception('Vacancy not found');
    if (response.statusCode != 200) {
      throw Exception('Failed to load analysis: ${response.statusCode}');
    }
    return VacancyAnalysis.fromJson(
        jsonDecode(response.body) as Map<String, dynamic>);
  }
}
