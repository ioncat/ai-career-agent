import 'dart:convert';
import 'dart:typed_data';
import 'package:http/http.dart' as http;
import '../models/vacancy.dart';
// ActivityEntry is defined in vacancy.dart

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

  Future<void> generateCv(int vacancyId, {String language = 'en'}) async {
    final uri = Uri.parse('$baseUrl/api/vacancies/$vacancyId/generate-cv');
    final response = await http.post(
      uri,
      headers: {'Content-Type': 'application/json'},
      body: '{"language":"$language"}',
    ).timeout(const Duration(seconds: 10));
    if (response.statusCode == 404) throw Exception('Vacancy not found');
    if (response.statusCode != 200) throw Exception('Generate CV failed: ${response.statusCode}');
  }

  Future<void> generateCover(int vacancyId) async {
    final uri = Uri.parse('$baseUrl/api/vacancies/$vacancyId/generate-cover');
    final response = await http.post(uri).timeout(const Duration(seconds: 10));
    if (response.statusCode == 404) throw Exception('Vacancy not found');
    if (response.statusCode == 409) throw Exception('Already in progress');
    if (response.statusCode != 200) throw Exception('Generate cover failed: ${response.statusCode}');
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

  Future<void> setStarred(int vacancyId, bool starred) async {
    final uri = Uri.parse('$baseUrl/api/vacancies/$vacancyId/starred');
    final response = await http
        .patch(uri,
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({'starred': starred}))
        .timeout(const Duration(seconds: 5));
    if (response.statusCode != 200) throw Exception('Set starred failed: ${response.statusCode}');
  }

  Future<void> updateSalary(int vacancyId, String salary) async {
    final uri = Uri.parse('$baseUrl/api/vacancies/$vacancyId/salary');
    final response = await http
        .patch(uri,
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({'salary': salary}))
        .timeout(const Duration(seconds: 5));
    if (response.statusCode == 404) throw Exception('Vacancy not found');
    if (response.statusCode != 200) throw Exception('Update salary failed: ${response.statusCode}');
  }

  Future<void> setApplied(int vacancyId, bool applied) async {
    final uri = Uri.parse('$baseUrl/api/vacancies/$vacancyId/applied');
    final response = await http
        .patch(uri,
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({'applied': applied}))
        .timeout(const Duration(seconds: 5));
    if (response.statusCode != 200) throw Exception('Set applied failed: ${response.statusCode}');
  }

  Future<Map<String, dynamic>> getConfig() async {
    final uri = Uri.parse('$baseUrl/api/config');
    final response = await http.get(uri).timeout(const Duration(seconds: 5));
    if (response.statusCode != 200) throw Exception('Config unavailable');
    return jsonDecode(response.body) as Map<String, dynamic>;
  }

  Future<({List<PipelineRun> runs, List<ActivityEntry> entries})> getActivity(int vacancyId) async {
    final uri = Uri.parse('$baseUrl/api/vacancies/$vacancyId/activity');
    final response = await http.get(uri).timeout(const Duration(seconds: 10));
    if (response.statusCode == 404) throw Exception('Vacancy not found');
    if (response.statusCode != 200) throw Exception('Failed to load activity: ${response.statusCode}');
    final data = jsonDecode(response.body) as Map<String, dynamic>;
    final runs = (data['pipeline_runs'] as List<dynamic>)
        .map((e) => PipelineRun.fromJson(e as Map<String, dynamic>))
        .toList();
    final entries = (data['entries'] as List<dynamic>)
        .map((e) => ActivityEntry.fromJson(e as Map<String, dynamic>))
        .toList();
    return (runs: runs, entries: entries);
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

  Future<Uint8List> getCvPdfBytes(int vacancyId) async {
    final uri = Uri.parse('$baseUrl/api/vacancies/$vacancyId/cv-pdf');
    final response = await http.get(uri).timeout(const Duration(seconds: 60));
    if (response.statusCode == 404) throw Exception('CV not yet generated');
    if (response.statusCode == 503) throw Exception('PDF service unavailable');
    if (response.statusCode != 200) throw Exception('PDF download failed: ${response.statusCode}');
    return response.bodyBytes;
  }

  Future<Uint8List> getCoverPdfBytes(int vacancyId) async {
    final uri = Uri.parse('$baseUrl/api/vacancies/$vacancyId/cover-pdf');
    final response = await http.get(uri).timeout(const Duration(seconds: 60));
    if (response.statusCode == 404) throw Exception('Cover not yet generated');
    if (response.statusCode == 503) throw Exception('PDF service unavailable');
    if (response.statusCode != 200) throw Exception('PDF download failed: ${response.statusCode}');
    return response.bodyBytes;
  }
}
