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

  Future<String> getJd(int vacancyId) async {
    final uri = Uri.parse('$baseUrl/api/vacancies/$vacancyId/jd');
    final response = await http.get(uri).timeout(const Duration(seconds: 10));
    if (response.statusCode == 404) throw Exception('JD not found');
    if (response.statusCode != 200) throw Exception('Failed to load JD: ${response.statusCode}');
    final data = jsonDecode(response.body) as Map<String, dynamic>;
    return data['jd_md'] as String? ?? '';
  }

  Future<void> restore(int vacancyId) async {
    final uri = Uri.parse('$baseUrl/api/vacancies/$vacancyId/restore');
    final response = await http.patch(uri).timeout(const Duration(seconds: 10));
    if (response.statusCode == 404) {
      final body = jsonDecode(response.body) as Map<String, dynamic>?;
      final detail = body?['detail'] as String? ?? '';
      throw Exception(detail.isNotEmpty ? detail : 'Not found — restart the backend');
    }
    if (response.statusCode != 200) throw Exception('Restore failed: ${response.statusCode}');
  }

  Future<void> analyze(int vacancyId) async {
    final uri = Uri.parse('$baseUrl/api/vacancies/$vacancyId/analyze');
    final response = await http.post(uri).timeout(const Duration(seconds: 10));
    if (response.statusCode == 404) throw Exception('Vacancy not found');
    if (response.statusCode == 409) throw Exception('Already in progress');
    if (response.statusCode != 202) throw Exception('Analyze failed: ${response.statusCode}');
  }

  Future<Map<String, dynamic>> getConfig() async {
    final uri = Uri.parse('$baseUrl/api/config');
    final response = await http.get(uri).timeout(const Duration(seconds: 5));
    if (response.statusCode != 200) throw Exception('Config unavailable');
    return jsonDecode(response.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> patchConfig({
    String? model,
    String? thinkingEffort,
  }) async {
    final uri = Uri.parse('$baseUrl/api/config');
    final body = <String, dynamic>{};
    if (model != null) body['model'] = model;
    if (thinkingEffort != null) body['thinking_effort'] = thinkingEffort;
    final response = await http
        .patch(uri,
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode(body))
        .timeout(const Duration(seconds: 5));
    if (response.statusCode != 200) {
      throw Exception('Config update failed: ${response.statusCode}');
    }
    return jsonDecode(response.body) as Map<String, dynamic>;
  }
}
