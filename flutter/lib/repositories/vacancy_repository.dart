import 'dart:convert';
import 'package:http/http.dart' as http;
import '../models/vacancy.dart';

class VacancyRepository {
  final String baseUrl;

  const VacancyRepository({required this.baseUrl});

  Future<List<VacancyListItem>> listVacancies({
    String? status,
    String? since,
    int limit = 1000,
  }) async {
    final params = <String, String>{'limit': '$limit'};
    if (status != null) params['status'] = status;
    if (since != null) params['since'] = since;

    final uri = Uri.parse('$baseUrl/api/vacancies')
        .replace(queryParameters: params);

    final response = await http.get(uri).timeout(const Duration(seconds: 10));
    if (response.statusCode != 200) {
      throw Exception('Failed to load vacancies: ${response.statusCode}');
    }

    final List<dynamic> data = jsonDecode(response.body) as List<dynamic>;
    return data
        .map((e) => VacancyListItem.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<void> decline(int vacancyId) async {
    final uri = Uri.parse('$baseUrl/api/vacancies/$vacancyId/decline');
    final response = await http.patch(uri).timeout(const Duration(seconds: 10));
    if (response.statusCode == 404) throw Exception('Vacancy not found');
    if (response.statusCode != 200) throw Exception('Decline failed: ${response.statusCode}');
  }

  Future<void> generateCv(int vacancyId) async {
    final uri = Uri.parse('$baseUrl/api/vacancies/$vacancyId/generate-cv');
    final response = await http.post(uri).timeout(const Duration(seconds: 10));
    if (response.statusCode == 404) throw Exception('Vacancy not found');
    if (response.statusCode != 200) throw Exception('Generate CV failed: ${response.statusCode}');
  }

  Future<VacancyCv> getCv(int vacancyId) async {
    final uri = Uri.parse('$baseUrl/api/vacancies/$vacancyId/cv');
    final response = await http.get(uri).timeout(const Duration(seconds: 10));
    if (response.statusCode == 404) throw Exception('Vacancy not found');
    if (response.statusCode != 200) throw Exception('Failed to load CV: ${response.statusCode}');
    return VacancyCv.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
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
