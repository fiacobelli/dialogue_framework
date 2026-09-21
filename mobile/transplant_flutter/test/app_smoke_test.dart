import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:transplant_flutter/main.dart';

void main() {
  testWidgets('boots into the microsite wrapper shell', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      const TransplantApp(home: Scaffold(body: Text('shell-test-home'))),
    );
    await tester.pump();

    expect(find.byType(MaterialApp), findsOneWidget);
    expect(find.text('shell-test-home'), findsOneWidget);

    final materialApp = tester.widget<MaterialApp>(find.byType(MaterialApp));
    expect(materialApp.title, 'Ludi Donor');
    expect(materialApp.debugShowCheckedModeBanner, isFalse);
  });
}
