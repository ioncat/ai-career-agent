import 'package:http/http.dart' as http;
import '../models/health.dart';

class HealthRepository {
  final String baseUrl;

  const HealthRepository({required this.baseUrl});

  Future<HealthStatus> check() async {
    try {
      final response = await http
          .get(Uri.parse('$baseUrl/api/vacancies?limit=0'))
          .timeout(const Duration(seconds: 5));
      return response.statusCode == 200 ? HealthStatus.online : HealthStatus.offline;
    } catch (_) {
      return HealthStatus.offline;
    }
  }
}
