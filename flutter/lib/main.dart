import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'theme/app_theme.dart';
import 'screens/app_shell.dart';
import 'services/notification_service.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await NotificationService.init();
  runApp(const ProviderScope(child: CareerAgentApp()));
}

class CareerAgentApp extends StatelessWidget {
  const CareerAgentApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Career Agent',
      theme: AppTheme.light,
      debugShowCheckedModeBanner: false,
      home: const AppShell(),
    );
  }
}
