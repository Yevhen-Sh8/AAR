# NATO Lessons Learned ↔ AAR Platform

Методологічна основа платформи — **NATO Lessons Learned Handbook, 4th Edition**
(JALLC, 2022) та **JALLC Analysis Handbook** (2024). Нижче — мапа термінів
NATO LL на сутності нашої системи.

## Мапа термінів

| NATO LL | AAR Platform | Коментар |
|---|---|---|
| **Observation** | `UsageEvent` або запис у `IndividualReport` | Сире спостереження |
| **Issue** | Поле `issue` у `AARCase` | Згрупована проблема |
| **Discussion / Analysis** | `AARCase.analysis` (LLM-драфт + правки менеджера) | Чому це сталося |
| **Lesson Identified (LI)** | `AARCase.lesson_identified` | Кандидат на урок |
| **Remedial Action (RA)** | `Recommendation` (статус: proposed/in_progress/done) | Що зробити |
| **Lesson Learned (LL)** | `KnowledgeEntry` (validated = true) | Підтверджено впровадженням |
| **Validation** | `Recommendation.validated_at` + докази (events після RA) | Перевірка ефективності |
| **Institutionalization** | Запис у `KnowledgeEntry` з тегом «процедура / СОП» | Закріплення в практику |

## Процес у нашій термінології

```
Подія → Спостереження → Кейс AAR (Issue + Analysis) → LI → RA →
        → Виконання RA → Validation → LL → Institutionalization
```

## Що це означає на практиці

1. **Спостереження не зникають**: усі `UsageEvent` доступні для майбутніх кейсів.
2. **Кожна рекомендація має життєвий цикл**: запропонована → у роботі →
   виконана → провалідована (повторне спрацювання тригера через 30 діб
   автоматично «опускає» статус назад).
3. **База знань — це лише валідовані LL**. Усе невалідоване — у кейсах і
   рекомендаціях, не «забруднює» знання.

## Посилання

- NATO LL Handbook 4: <https://nllp.jallc.nato.int/iks/sharing%20public/jallc_ll_handbook_update_-_4th_edition_final_14072022.pdf>
- JALLC Analysis Handbook 2024: <https://nllp.jallc.nato.int/news/Documents/JALLC_Analysis_Handbook_2024.pdf>
- JALLC: <https://www.jallc.nato.int/>
