"""Tests for core/vacancy_tags.py — keyword-based segment classification."""

from core.vacancy_tags import PRIORITY, classify, merge_tags, primary_tag


class TestClassify:
    def test_empty_text_returns_no_tags(self):
        assert classify("") == []
        assert classify(None) == []

    def test_igaming_keyword(self):
        assert classify("We are a leading iGaming company") == ["igaming"]

    def test_casino_keyword_maps_to_igaming(self):
        assert "igaming" in classify("Join our Casino product team")

    def test_deftech_keyword(self):
        assert classify("We build military drone systems") == ["deftech"]

    def test_mobile_keyword(self):
        assert classify("Looking for a Product Manager for our mobile app") == ["mobile"]

    def test_ios_word_boundary_no_false_positive_on_portfolios(self):
        # "portfolios" contains the substring "ios" — must not match \bios\b.
        assert classify("Review candidate portfolios before the interview") == []

    def test_ios_matches_as_standalone_word(self):
        assert "mobile" in classify("Experience shipping iOS apps required")

    def test_b2b_saas_keyword(self):
        assert classify("We are a B2B SaaS platform for enterprise") == ["b2b_saas"]

    def test_saas_word_boundary(self):
        assert classify("We are a SaaS company") == ["b2b_saas"]

    def test_outsourcing_keyword(self):
        assert "outsourcing" in classify("We are an IT outsourcing company")

    def test_fintech_keyword(self):
        assert classify("We are a leading fintech company") == ["fintech"]

    def test_studio_keyword(self):
        assert classify("Join our game studio building the next hit") == ["studio"]

    def test_multiple_tags_can_match(self):
        text = "We are a B2B SaaS fintech platform serving mobile app users"
        tags = classify(text)
        assert set(tags) == {"b2b_saas", "fintech", "mobile"}

    def test_generic_text_has_no_tags(self):
        assert classify("We are hiring a Product Manager to own our roadmap") == []

    def test_case_insensitive(self):
        assert classify("IGAMING COMPANY LOOKING FOR PM") == ["igaming"]

    def test_deftech_strong_keyword_matches_regardless(self):
        assert classify("We are a deftech startup building UAV software") == ["deftech"]

    def test_deftech_miltech_keyword(self):
        assert "deftech" in classify("Join our miltech recruitment agency")


class TestDeftechCsrBoilerplate:
    """Regression for 2026-08-31: an audit of applied vacancies found 5 of 10
    "deftech"-tagged companies were false positives — the ubiquitous Ukrainian
    job-posting CSR/DEI paragraph ("we support the armed forces", "we hire
    military veterans", "we collect drones for charity") triggered the old
    bare-substring keywords regardless of what the company actually builds."""

    def test_support_armed_forces_boilerplate_does_not_tag_deftech(self):
        text = "Ми системно підтримуємо сили оборони та долучаємось до ініціатив."
        assert "deftech" not in classify(text)

    def test_military_veterans_hiring_statement_does_not_tag_deftech(self):
        text = "We proudly support diverse talent and military veterans."
        assert "deftech" not in classify(text)

    def test_volunteer_drone_collection_does_not_tag_deftech(self):
        text = "Допомагаємо ЗСУ, збираємо дрони, підтримуємо дитячі будинки."
        assert "deftech" not in classify(text)

    def test_fundraising_for_armed_forces_does_not_tag_deftech(self):
        text = "Кожен може приєднатися до збору коштів на збройні сили України."
        assert "deftech" not in classify(text)

    def test_real_deftech_still_matches_alongside_csr_boilerplate(self):
        # A genuine defense-tech company can ALSO carry the same CSR
        # paragraph — the strong keyword must still win.
        text = (
            "We are a deftech company building UAV systems. "
            "We proudly support diverse talent and military veterans."
        )
        assert "deftech" in classify(text)

    def test_weak_keyword_outside_boilerplate_still_matches(self):
        # "military" used to actually describe the product, not CSR filler.
        assert classify("We build military drone systems") == ["deftech"]


class TestDeftechExtendedFalseContext:
    """Regression for 2026-08-31 (external audit): the first CSR-boilerplate
    fix only closed one false-positive class — 30 of 51 deftech-tagged
    vacancies were still wrong via HR/EEO boilerplate, the cybersecurity
    homonym, construction-drone use, and agency/recruiting mentions that
    don't describe the posting company's own product."""

    def test_english_veteran_hiring_boilerplate_does_not_tag(self):
        text = "Our veteran career and empowerment program ensures veterans and active military personnel receive support."
        assert "deftech" not in classify(text)

    def test_military_leave_benefit_does_not_tag(self):
        text = "Benefits include military leave policy and special health insurance options."
        assert "deftech" not in classify(text)

    def test_donation_to_defense_forces_does_not_tag(self):
        text = "The company is among the top 10 largest donors to Ukraine's defense forces and humanitarian initiatives."
        assert "deftech" not in classify(text)

    def test_generic_defense_forces_charity_does_not_tag(self):
        text = "Total contributions to the defense forces, social initiatives, and charitable projects have exceeded UAH 30M."
        assert "deftech" not in classify(text)

    def test_cyber_defense_homonym_does_not_tag(self):
        text = "The customer is a one-stop-shop for online cyber defense solutions in information security."
        assert "deftech" not in classify(text)

    def test_client_defense_business_idiom_does_not_tag(self):
        text = "Their team of experts put the client's defense ahead in order to solve the issue."
        assert "deftech" not in classify(text)

    def test_curly_apostrophe_still_strips_correctly(self):
        # Same idiom as above, curly apostrophe (’, U+2019) — common in
        # professionally typeset JD text, silently bypassed the ASCII-only
        # pattern before text normalization was added.
        text = "Their team of experts put the client’s defense ahead of everything."
        assert "deftech" not in classify(text)

    def test_construction_drone_scan_does_not_tag(self):
        text = "AI-powered construction platform that connects lidar scans, drone scans, and 360 site capture."
        assert "deftech" not in classify(text)

    def test_dronedeploy_product_name_does_not_tag(self):
        # Bare "drone" substring inside a construction-tech product name.
        text = "Integrates with openspace, buildots, doxel, and dronedeploy for site management."
        assert "deftech" not in classify(text)

    def test_brave1_hackathon_mention_does_not_tag(self):
        # Exact shape observed live (Artellence, ×4 postings) — Ukrainian
        # phrasing, not translated, since that's the only form seen so far.
        text = "Відвідуємо osint-конференції та хакатони, співпрацюємо з defensetech об'єднанням Brave1."
        assert "deftech" not in classify(text)

    def test_client_vertical_list_does_not_tag(self):
        text = "We serve clients across several verticals, including healthcare, fintech, telecom, logistics, and defence."
        assert "deftech" not in classify(text)

    def test_miltech_domain_nice_to_have_does_not_tag(self):
        text = "Nice to have: experience in the miltech domain; experience in edtech and fintech domains."
        assert "deftech" not in classify(text)

    def test_military_reservation_perk_does_not_tag(self):
        text = "Benefits: full-remote work environment, military reservation, 20 business days of paid vacation."
        assert "deftech" not in classify(text)

    def test_serving_in_the_military_support_does_not_tag(self):
        text = "Ongoing care and support for employees serving in the military."
        assert "deftech" not in classify(text)

    def test_military_teammates_support_does_not_tag(self):
        text = "Since the invasion, our foundation has supported Ukraine and our military teammates."
        assert "deftech" not in classify(text)

    def test_real_deftech_still_matches_recruiting_agency_client_role(self):
        # Contrast: an agency describing a SPECIFIC real defense-tech
        # client's actual work still counts — only generic capability/
        # networking mentions (tested above) are excluded.
        text = (
            "We are Everstar, the first recruiting agency in MilTech. "
            "Our client builds technology for Ukraine's defense and is scaling fast — "
            "looking for an AI Product Manager to grow internal products."
        )
        assert "deftech" in classify(text)


class TestOutsourcingFalseContext:
    """Regression for 2026-08-30: a full-DB audit found 6 of 162
    outsourcing-tagged vacancies were false positives — bare "agency"/
    "outsourc" matched a JD contrasting ITSELF against agency work, or a
    client-side/vendor mention unrelated to the hiring company."""

    def test_negation_vs_agency_does_not_tag_outsourcing(self):
        text = "Product company background (vs agency/outsource)"
        assert "outsourcing" not in classify(text)

    def test_negation_not_agency_does_not_tag_outsourcing(self):
        text = "Experience working on product platform development (not agency or client delivery projects)."
        assert "outsourcing" not in classify(text)

    def test_agency_fees_client_mention_does_not_tag_outsourcing(self):
        text = "Automate localization and free up budget buried in agency fees and manual process."
        assert "outsourcing" not in classify(text)

    def test_partner_law_agency_benefit_does_not_tag_outsourcing(self):
        text = "Law agency support through our partner law agency, regular performance reviews."
        assert "outsourcing" not in classify(text)

    def test_real_agency_company_still_matches(self):
        assert "outsourcing" in classify("Come Back Agency supports US software and tech companies.")

    def test_real_outsourcing_company_still_matches(self):
        assert "outsourcing" in classify("Glorium Technologies is an innovative outsourcing company.")


class TestMobileFalseContext:
    """Regression for 2026-09-02: user flagged vacancy #1432 ("Product
    Manager (web)") as wrongly tagged mobile. A full-DB audit of all 199
    mobile-tagged vacancies found 17 were false positives — bare "мобільн"
    matching a corporate phone-plan benefit, a "subsidiary of mobile
    operator X" domain descriptor, or a travel/flexibility requirement, none
    of which say the product itself is mobile."""

    def test_mobile_phone_benefit_does_not_tag_mobile(self):
        text = "Медичне страхування та корпоративний мобільний зв'язок, сучасний офіс."
        assert "mobile" not in classify(text)

    def test_mobile_phone_benefit_instrumental_case_does_not_tag_mobile(self):
        text = "Забезпечення технікою, мобільним зв'язком, корпоративні трансфери до офісу."
        assert "mobile" not in classify(text)

    def test_curly_apostrophe_still_strips_correctly(self):
        text = "Медичне страхування та корпоративний мобільний зв’язок."
        assert "mobile" not in classify(text)

    def test_mobile_operator_subsidiary_does_not_tag_mobile(self):
        text = "Ми ІТ компанія, заснована як дочірня компанія провідного мобільного оператора Vodafone Ukraine."
        assert "mobile" not in classify(text)

    def test_travel_flexibility_requirement_does_not_tag_mobile(self):
        text = "Треба проявляти свій талант і рости разом із проєктами. Обов'язково бути мобільним та мати змогу відвідувати часті міжнародні відрядження."
        assert "mobile" not in classify(text)

    def test_real_mobile_product_still_matches(self):
        text = "Шукаємо Product Manager, який відповідатиме за розвиток мобільного застосунку на двох платформах."
        assert "mobile" in classify(text)

    def test_ios_android_strong_keywords_unaffected_by_mobile_weak_list(self):
        # ios/android stay in the always-on strong list — no false-positive
        # context found for them in the audit, unlike bare "мобільн".
        assert "mobile" in classify("Experience shipping iOS apps required")
        assert "mobile" in classify("3+ years building Android products")


class TestMergeTags:
    def test_merge_into_empty(self):
        assert merge_tags(None, ["igaming"]) == "igaming"
        assert merge_tags("", ["igaming"]) == "igaming"

    def test_merge_preserves_existing(self):
        assert merge_tags("deftech", ["mobile"]) == "deftech,mobile"

    def test_merge_dedupes_case_insensitive(self):
        assert merge_tags("deftech", ["deftech"]) == "deftech"
        assert merge_tags("DefTech", ["deftech"]) == "DefTech"

    def test_merge_no_new_tags_returns_existing_unchanged(self):
        assert merge_tags("deftech,mobile", []) == "deftech,mobile"

    def test_merge_strips_whitespace_in_existing(self):
        assert merge_tags("deftech, mobile", ["fintech"]) == "deftech,mobile,fintech"


class TestPrimaryTag:
    def test_empty_list_returns_none(self):
        assert primary_tag([]) is None

    def test_single_tag_returns_itself(self):
        assert primary_tag(["mobile"]) == "mobile"

    def test_deftech_wins_over_everything(self):
        assert primary_tag(["mobile", "b2b_saas", "deftech", "outsourcing"]) == "deftech"

    def test_igaming_wins_over_mobile_and_b2b_saas(self):
        assert primary_tag(["mobile", "b2b_saas", "igaming"]) == "igaming"

    def test_outsourcing_only_wins_when_nothing_else_matched(self):
        assert primary_tag(["outsourcing"]) == "outsourcing"
        assert primary_tag(["outsourcing", "mobile"]) == "mobile"

    def test_unknown_tag_falls_back_to_first(self):
        # A manually-set tag not in the taxonomy at all (e.g. "deftech" set
        # by hand before the auto-classifier existed) still needs a primary.
        assert primary_tag(["some-custom-tag"]) == "some-custom-tag"

    def test_priority_order_is_internally_consistent(self):
        # Every PRIORITY entry should independently win a two-way tie against
        # every entry that comes after it in the list.
        for i, higher in enumerate(PRIORITY):
            for lower in PRIORITY[i + 1 :]:
                assert primary_tag([lower, higher]) == higher
