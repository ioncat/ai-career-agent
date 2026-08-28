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
