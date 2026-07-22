# بوابات المراحل والإصدار

| البوابة | متطلبات الخروج |
|---|---|
| G0 Architecture | ADRs، CI، security baseline، DB/API skeleton |
| G1 Domain | migrations والقيود والحالات واختبارات التزامن |
| G2 Booking | تدفق كامل دون دفع + PNR + Snapshot |
| G3 Payment/Ticket | مصالحة وLedger وتذكرة وإشعارات |
| G4 Operations | boarding/change/cancel/support |
| G5 Admin/Finance | settlement/violations/policies/reports |
| G6 Pilot Ready | AT matrix، security، DR، visual review، training |
| G7 Expansion | KPI، 14 يوم استقرار، لا حادث حرج، تسويات مغلقة |

## الإصدار

Semantic version للتطبيق ونسخة مستقلة للمخطط والسياسات. Release notes تذكر migrations وflags والتغييرات التشغيلية وخطة الرجوع.
