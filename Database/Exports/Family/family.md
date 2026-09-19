# Family Relationships / خاندانی رشتے

Revision 6 — 2026-09-03

> Generated from `family.db`. Update the data file, then run `python3.11 build_family.py`.
> `family.md` and `family.html` are generated together from the same Mermaid diagram string.
>
> Reading guide:
> - Each married couple is one compact horizontal unit: spouses sit beside each other and the horizontal line between them is the marriage, with the recorded year where known.
> - Parent lines leave both actual parent cards, meet at a separate family junction, and fan out to the actual child cards; `parents / والدین` or `biological parents / حقیقی والدین` is written on the shared downward line.
> - A couple without recorded children has no child junction; `no children / کوئی اولاد نہیں` stays on the marriage line where recorded.
> - In this current master view, maternal-side pink units occupy the left and paternal-side blue units occupy the right. Irsa Naz + Mansoor Hussain remain the central bridge, using one pink card and one blue card inside a neutral boundary.
> - `[1]`, `[2]`, ... before a name record birth order within that sibling group.
> - Direct neutral dotted lines connect the existing person cards for other recorded sibling/cross-family relationships; the relationship wording appears on the line and person names are not repeated.
> - Derived cousin relationships (first/second cousin and once-removed terms with maternal/paternal sides) are calculated from biological links and full-sibling facts; they appear in the generated derived-relationships section, and a couple that is also a cousin pair gets a small annotation on its marriage line.

```mermaid
flowchart TB
  %% Generated from family.db by build_family.py. Source of truth: family.db.
  %% Current master layout: maternal left, bridge center, paternal right.
  %% Couple clusters are colored visual units only. Junctions (j_*) are
  %% layout-only helpers: not people and never written back to family.db.
  classDef person fill:#fffefa,stroke:#7b817c,color:#202823;
  classDef matperson fill:#f8e9ed,stroke:#c99ead,color:#202823;
  classDef patperson fill:#e9f0f2,stroke:#96afb5,color:#202823;
  classDef focus stroke:#35695e,stroke-width:3px,color:#202823;
  classDef junc fill:none,stroke:none,color:none;
  classDef route fill:none,stroke:none,color:none;
    x_abrar_israr[" "]
  subgraph u_israr_hussain--IH01__shahnaz_israr--SI01[" "]
    direction LR
    p_israr_hussain__IH01["Israr Hussain<br/>Maternal grandfather / نانا"]
    p_shahnaz_israr__SI01["Shahnaz Israr<br/>Maternal grandmother / نانی"]
    p_israr_hussain__IH01 ---|"married / شادی شدہ"| p_shahnaz_israr__SI01
  end
  subgraph u_abrar_hussain--AH01__shaheen_abrar--SA01[" "]
    direction LR
    p_abrar_hussain__AH01["Abrar Hussain<br/>Paternal grandfather / دادا"]
    p_shaheen_abrar__SA01["Shaheen Abrar<br/>Paternal grandmother / دادی"]
    p_abrar_hussain__AH01 ---|"married / شادی شدہ"| p_shaheen_abrar__SA01
  end
  subgraph u_rubinna--R01__sohaib_hussain--SH01[" "]
    direction LR
    p_rubinna__R01["Rubinna<br/>Maternal uncle's wife / ممانی"]
    p_sohaib_hussain__SH01["[1] Sohaib Hussain<br/>Maternal uncle / ماموں"]
    p_rubinna__R01 ---|"married / شادی شدہ<br/>no children / کوئی اولاد نہیں"| p_sohaib_hussain__SH01
  end
  subgraph u_asif_qamar--AQ01__sadia_asif--SA01[" "]
    direction LR
    p_asif_qamar__AQ01["Asif Qamar<br/>Maternal aunt's husband / خالو"]
    p_sadia_asif__SA01["[2] Sadia Asif<br/>Maternal aunt / خالہ"]
    p_asif_qamar__AQ01 ---|"married / شادی شدہ"| p_sadia_asif__SA01
  end
  subgraph u_arsalan_israr--AI01__falak_naz--FN01[" "]
    direction LR
    p_arsalan_israr__AI01["[4] Arsalan Israr<br/>Maternal uncle / ماموں"]
    p_falak_naz__FN01["Falak Naz<br/>Maternal uncle's wife / ممانی"]
    p_arsalan_israr__AI01 ---|"married / شادی شدہ<br/>no children / کوئی اولاد نہیں"| p_falak_naz__FN01
  end
  subgraph u_ayesha_naeem--AN01__wahaj--W01[" "]
    direction LR
    p_ayesha_naeem__AN01["[5] Ayesha Naeem<br/>Maternal aunt / خالہ<br/>Given to another family after birth (exact arrangement not yet specified)<br/>پیدائش کے بعد دوسری فیملی کو دی گئیں (تفصیل ابھی غیر واضح ہے)"]
    p_wahaj__W01["Wahaj<br/>Maternal aunt's husband / خالو"]
    p_ayesha_naeem__AN01 ---|"married / شادی شدہ<br/>no children / کوئی اولاد نہیں"| p_wahaj__W01
  end
  subgraph u_irsa_naz--IN01__mansoor_hussain--MH01[" "]
    direction LR
    p_irsa_naz__IN01["[3] Irsa Naz<br/>Mother / والدہ"]
    p_mansoor_hussain__MH01["[1] Mansoor Hussain<br/>Father / والد"]
    p_irsa_naz__IN01 ---|"married 2003 / شادی 2003<br/>first cousins / پہلے کزن"| p_mansoor_hussain__MH01
  end
  subgraph u_hina--H01__zubair--Z01[" "]
    direction LR
    p_hina__H01["[2] Hina<br/>Paternal aunt / پھوپھی"]
    p_zubair__Z01["Zubair<br/>Paternal aunt's husband / پھوپھا"]
    p_hina__H01 ---|"married / شادی شدہ"| p_zubair__Z01
  end
  subgraph u_sajjad--S01__sana--S01[" "]
    direction LR
    p_sajjad__S01["Sajjad<br/>Paternal aunt's husband / پھوپھا"]
    p_sana__S01["[3] Sana<br/>Paternal aunt / پھوپھی"]
    p_sajjad__S01 ---|"married / شادی شدہ"| p_sana__S01
  end
  subgraph u_adeel_ahmad--AA01__afshan--A01[" "]
    direction LR
    p_adeel_ahmad__AA01["Adeel Ahmad<br/>Paternal aunt's husband / پھوپھا"]
    p_afshan__A01["[4] Afshan<br/>Paternal aunt / پھوپھی"]
    p_adeel_ahmad__AA01 ---|"married / شادی شدہ"| p_afshan__A01
  end
  subgraph u_aresha_zubair--AZ01__owais--O01[" "]
    direction LR
    p_aresha_zubair__AZ01["[1] Aresha Zubair<br/>Paternal cousin / پھوپھی زاد"]
    p_owais__O01["Owais<br/>Paternal cousin's husband / پھوپھی زاد کے شوہر"]
    p_aresha_zubair__AZ01 ---|"married / شادی شدہ"| p_owais__O01
  end
  subgraph u_fizza_zubair--FZ01__moiz--M01[" "]
    direction LR
    p_fizza_zubair__FZ01["[2] Fizza Zubair<br/>Paternal cousin / پھوپھی زاد"]
    p_moiz__M01["Moiz<br/>Paternal cousin's husband / پھوپھی زاد کے شوہر"]
    p_fizza_zubair__FZ01 ---|"married / شادی شدہ<br/>no children / کوئی اولاد نہیں"| p_moiz__M01
  end
    j_israr_hussain__IH01__shahnaz_israr__SI01[" "]
    j_abrar_hussain__AH01__shaheen_abrar__SA01[" "]
    j_asif_qamar__AQ01__sadia_asif__SA01[" "]
    j_irsa_naz__IN01__mansoor_hussain__MH01[" "]
    j_hina__H01__zubair__Z01[" "]
    j_sajjad__S01__sana__S01[" "]
    j_adeel_ahmad__AA01__afshan__A01[" "]
    j_aresha_zubair__AZ01__owais__O01[" "]
    x_rubinna_falak[" "]
    x_aresha_children[" "]
    p_ezan_asif__EA01["[1] Ezan Asif (2003)<br/>Maternal cousin / خالہ زاد بھائی"]
    p_fakhir_asif__FA01["[2] Fakhir Asif (2007)<br/>Maternal cousin / خالہ زاد بھائی"]
    p_mohammad_yahya_hussain__MYH01["[1] Mohammad Yahya Hussain (2004)<br/>Self / خود"]
    p_maham_mansoor__MM01["[2] Maham Mansoor (2006)<br/>Sister / بہن"]
    p_abdul_rafey__AR01["[3] Abdul Rafey (2003)<br/>Paternal cousin / پھوپھی زاد بھائی<br/>Single / غیر شادی شدہ"]
    p_muaaz__M01["[1] Muaaz / Maaz (2010)<br/>Paternal cousin / پھوپھی زاد بھائی"]
    p_barirah__B01["[2] Barirah (2015)<br/>Paternal cousin / پھوپھی زاد بہن"]
    p_musabiha__M01["[1] Musabiha<br/>Paternal cousin / پھوپھی زاد بہن"]
    p_musa__M01["[2] Musa<br/>Paternal cousin / پھوپھی زاد بھائی"]
    p_unnamed_daughter_a__UDA01["Unnamed daughter A<br/>Cousin's daughter / کزن کی بیٹی<br/>A is an identifier, not a birth-order claim<br/>A صرف شناخت ہے، پیدائشی ترتیب نہیں"]
    p_unnamed_daughter_b__UDB01["Unnamed daughter B<br/>Cousin's daughter / کزن کی بیٹی<br/>B is an identifier, not a birth-order claim<br/>B صرف شناخت ہے، پیدائشی ترتیب نہیں"]

    p_israr_hussain__IH01 -->|"biological parents / حقیقی والدین"| j_israr_hussain__IH01__shahnaz_israr__SI01
    p_shahnaz_israr__SI01 --> j_israr_hussain__IH01__shahnaz_israr__SI01
    j_israr_hussain__IH01__shahnaz_israr__SI01 --> p_sohaib_hussain__SH01
    j_israr_hussain__IH01__shahnaz_israr__SI01 --> p_arsalan_israr__AI01
    j_israr_hussain__IH01__shahnaz_israr__SI01 --> p_sadia_asif__SA01
    j_israr_hussain__IH01__shahnaz_israr__SI01 --> p_ayesha_naeem__AN01
    j_israr_hussain__IH01__shahnaz_israr__SI01 --> p_irsa_naz__IN01
    p_abrar_hussain__AH01 -->|"biological parents / حقیقی والدین"| j_abrar_hussain__AH01__shaheen_abrar__SA01
    p_shaheen_abrar__SA01 --> j_abrar_hussain__AH01__shaheen_abrar__SA01
    j_abrar_hussain__AH01__shaheen_abrar__SA01 --> p_mansoor_hussain__MH01
    j_abrar_hussain__AH01__shaheen_abrar__SA01 --> p_hina__H01
    j_abrar_hussain__AH01__shaheen_abrar__SA01 --> p_sana__S01
    j_abrar_hussain__AH01__shaheen_abrar__SA01 --> p_afshan__A01
    p_asif_qamar__AQ01 -->|"biological parents / حقیقی والدین"| j_asif_qamar__AQ01__sadia_asif__SA01
    p_sadia_asif__SA01 --> j_asif_qamar__AQ01__sadia_asif__SA01
    j_asif_qamar__AQ01__sadia_asif__SA01 --> p_ezan_asif__EA01
    j_asif_qamar__AQ01__sadia_asif__SA01 --> p_fakhir_asif__FA01
    p_irsa_naz__IN01 -->|"biological parents / حقیقی والدین"| j_irsa_naz__IN01__mansoor_hussain__MH01
    p_mansoor_hussain__MH01 --> j_irsa_naz__IN01__mansoor_hussain__MH01
    j_irsa_naz__IN01__mansoor_hussain__MH01 --> p_mohammad_yahya_hussain__MYH01
    j_irsa_naz__IN01__mansoor_hussain__MH01 --> p_maham_mansoor__MM01
    p_hina__H01 -->|"biological parents / حقیقی والدین"| j_hina__H01__zubair__Z01
    p_zubair__Z01 --> j_hina__H01__zubair__Z01
    j_hina__H01__zubair__Z01 --> p_aresha_zubair__AZ01
    j_hina__H01__zubair__Z01 --> p_fizza_zubair__FZ01
    j_hina__H01__zubair__Z01 --> p_abdul_rafey__AR01
    p_sajjad__S01 -->|"biological parents / حقیقی والدین"| j_sajjad__S01__sana__S01
    p_sana__S01 --> j_sajjad__S01__sana__S01
    j_sajjad__S01__sana__S01 --> p_muaaz__M01
    j_sajjad__S01__sana__S01 --> p_barirah__B01
    p_adeel_ahmad__AA01 -->|"biological parents / حقیقی والدین"| j_adeel_ahmad__AA01__afshan__A01
    p_afshan__A01 --> j_adeel_ahmad__AA01__afshan__A01
    j_adeel_ahmad__AA01__afshan__A01 --> p_musabiha__M01
    j_adeel_ahmad__AA01__afshan__A01 --> p_musa__M01
    p_aresha_zubair__AZ01 -->|"biological parents / حقیقی والدین"| j_aresha_zubair__AZ01__owais__O01
    p_owais__O01 --> j_aresha_zubair__AZ01__owais__O01
    j_aresha_zubair__AZ01__owais__O01 --> p_unnamed_daughter_a__UDA01
    j_aresha_zubair__AZ01__owais__O01 --> p_unnamed_daughter_b__UDB01
    x_abrar_israr -. "full brothers / سگے بھائی" .- p_israr_hussain__IH01
    x_abrar_israr -.- p_abrar_hussain__AH01
    p_rubinna__R01 -. "full sisters / سگی بہنیں" .- x_rubinna_falak
    p_falak_naz__FN01 -.- x_rubinna_falak
    p_unnamed_daughter_a__UDA01 -. "sisters; order not stated / بہنیں؛ ترتیب نامعلوم" .- x_aresha_children
    p_unnamed_daughter_b__UDB01 -.- x_aresha_children

    class p_mohammad_yahya_hussain__MYH01 person;
    class p_mohammad_yahya_hussain__MYH01 focus;
    class p_maham_mansoor__MM01 person;
    class p_shahnaz_israr__SI01 person;
    class p_israr_hussain__IH01 person;
    class p_sohaib_hussain__SH01 person;
    class p_rubinna__R01 person;
    class p_sadia_asif__SA01 person;
    class p_asif_qamar__AQ01 person;
    class p_ezan_asif__EA01 person;
    class p_fakhir_asif__FA01 person;
    class p_arsalan_israr__AI01 person;
    class p_falak_naz__FN01 person;
    class p_ayesha_naeem__AN01 person;
    class p_wahaj__W01 person;
    class p_abrar_hussain__AH01 person;
    class p_shaheen_abrar__SA01 person;
    class p_hina__H01 person;
    class p_zubair__Z01 person;
    class p_aresha_zubair__AZ01 person;
    class p_owais__O01 person;
    class p_unnamed_daughter_a__UDA01 person;
    class p_unnamed_daughter_b__UDB01 person;
    class p_fizza_zubair__FZ01 person;
    class p_moiz__M01 person;
    class p_abdul_rafey__AR01 person;
    class p_sana__S01 person;
    class p_sajjad__S01 person;
    class p_muaaz__M01 person;
    class p_barirah__B01 person;
    class p_afshan__A01 person;
    class p_adeel_ahmad__AA01 person;
    class p_musabiha__M01 person;
    class p_musa__M01 person;
    style u_israr_hussain--IH01__shahnaz_israr--SI01 fill:#FFF5F7,stroke:#E0B0BD,color:#111111;
    style u_abrar_hussain--AH01__shaheen_abrar--SA01 fill:#EEF4FF,stroke:#A8C3E6,color:#111111;
    style u_rubinna--R01__sohaib_hussain--SH01 fill:#FFE9EF,stroke:#DBA3B4,color:#111111;
    style u_asif_qamar--AQ01__sadia_asif--SA01 fill:#FFE1EA,stroke:#D88BA5,color:#111111;
    style u_arsalan_israr--AI01__falak_naz--FN01 fill:#F7E3E8,stroke:#C992A3,color:#111111;
    style u_ayesha_naeem--AN01__wahaj--W01 fill:#FFF0EA,stroke:#DCA18E,color:#111111;
    class p_irsa_naz__IN01 matperson;
    class p_mansoor_hussain__MH01 patperson;
    style u_irsa_naz--IN01__mansoor_hussain--MH01 fill:#F7F7FA,stroke:#B4B4CC,color:#111111;
    style u_hina--H01__zubair--Z01 fill:#E1EEFF,stroke:#97B6DE,color:#111111;
    style u_sajjad--S01__sana--S01 fill:#ECF0F7,stroke:#A5B2C7,color:#111111;
    style u_adeel_ahmad--AA01__afshan--A01 fill:#E0F2F5,stroke:#8EBECB,color:#111111;
    style u_aresha_zubair--AZ01__owais--O01 fill:#E3F1F8,stroke:#8FBBD5,color:#111111;
    style u_fizza_zubair--FZ01__moiz--M01 fill:#E7EDF6,stroke:#9FB3CD,color:#111111;
    class j_israr_hussain__IH01__shahnaz_israr__SI01 junc;
    class j_abrar_hussain__AH01__shaheen_abrar__SA01 junc;
    class j_asif_qamar__AQ01__sadia_asif__SA01 junc;
    class j_irsa_naz__IN01__mansoor_hussain__MH01 junc;
    class j_hina__H01__zubair__Z01 junc;
    class j_sajjad__S01__sana__S01 junc;
    class j_adeel_ahmad__AA01__afshan__A01 junc;
    class j_aresha_zubair__AZ01__owais__O01 junc;
    class x_rubinna_falak route;
    class x_abrar_israr route;
    class x_aresha_children route;
```

## Derived cousin relationships / اخذ کردہ کزن رشتے

Calculated from the biological parent-child graph and full-sibling facts in family.db; these are not stored as user-stated facts.

Side labels (maternal / paternal) show which of the focus person's parents the path runs through. Simple terms: first cousin / پہلے کزن، second cousin / دوسرے کزن.

### For Mohammad Yahya Hussain (focus) / مرکزی شخص کے لیے

- **Maham Mansoor** — maternal second cousin; paternal second cousin
- **Irsa Naz** — paternal first cousin once removed
- **Mansoor Hussain** — maternal first cousin once removed
- **Sohaib Hussain** — paternal first cousin once removed
- **Sadia Asif** — paternal first cousin once removed
- **Ezan Asif** — maternal first cousin; paternal second cousin
- **Fakhir Asif** — maternal first cousin; paternal second cousin
- **Arsalan Israr** — paternal first cousin once removed
- **Ayesha Naeem** — paternal first cousin once removed
- **Hina** — maternal first cousin once removed
- **Aresha Zubair** — paternal first cousin; maternal second cousin
- **Unnamed daughter A** — paternal first cousin once removed; maternal second cousin once removed
- **Unnamed daughter B** — paternal first cousin once removed; maternal second cousin once removed
- **Fizza Zubair** — paternal first cousin; maternal second cousin
- **Abdul Rafey** — paternal first cousin; maternal second cousin
- **Sana** — maternal first cousin once removed
- **Muaaz** — paternal first cousin; maternal second cousin
- **Barirah** — paternal first cousin; maternal second cousin
- **Afshan** — maternal first cousin once removed
- **Musabiha** — paternal first cousin; maternal second cousin
- **Musa** — paternal first cousin; maternal second cousin

## Open review notes / زیرِ جائزہ نکات

- None / کوئی نہیں

## Deferred / on-hold items / زیرِ التوا

- **R9** — Whether Shahnaz Israr and Shaheen Abrar have any relationship to each other is ON HOLD. No relationship is inferred, neither person is removed, and this is not asked again during the current revision.

## Preserved placeholders / محفوظ نامکمل معلومات

- **R5** — Aresha and Owais's two daughters remain Unnamed daughter A and B until their names and birth order are provided. A/B do not assert birth order.
- **R6** — Ayesha's arrangement with the other family remains an unspecified placeholder. No legal status is inferred.

## Validation summary

- People: 35
- Parent-child facts: 44
- Marriages: 12
- Sibling groups: 10
- Duplicate IDs, missing references, duplicate edges, and ancestry cycles: checked
- Parent kinds, marital status, marriage children_status, sibling-group types, and no-children conflicts: checked
- Derived cousin relationships: calculated from the explicit graph and audited at build time
