import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'theme/app_theme.dart';
import 'screens/app_shell.dart';

void main() {
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
