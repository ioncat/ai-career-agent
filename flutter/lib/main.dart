import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:google_fonts/google_fonts.dart';
import 'theme/app_theme.dart';
import 'screens/app_shell.dart';
import 'services/notification_service.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  // Allow cached fonts; if cache miss and no internet — fall back gracefully
  GoogleFonts.config.allowRuntimeFetching = true;
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
