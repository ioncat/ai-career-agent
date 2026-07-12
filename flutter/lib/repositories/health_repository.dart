import 'dart:convert';
import 'package:http/http.dart' as http;
import '../models/health.dart';

class HealthRepository {
  final String baseUrl;

  const HealthRepository({required this.baseUrl});

  Future<HealthStatus> check() async {
    try {
      final response = await http
          .get(Uri.parse('$baseUrl/api/health'))
          .timeout(const Duration(seconds: 5));
      if (response.statusCode != 200) return HealthStatus.offline;
      final data = jsonDecode(response.body) as Map<String, dynamic>;
      final workerOk = data['worker_available'] as bool? ?? false;
      return workerOk ? HealthStatus.online : HealthStatus.degraded;
    } catch (_) {
      return HealthStatus.offline;
    }
  }
}
