"""Skill taxonomy is the semantic backbone of matching with no LLM in the loop
(ADR 0002) -- these pin its contract, not just its current content."""

from __future__ import annotations

import pytest

from placeinator.skills.taxonomy import Skill, Taxonomy, get_taxonomy


def test_taxonomy_loads_and_has_real_coverage():
    taxonomy = get_taxonomy()
    assert len(taxonomy) > 50


def test_common_aliases_normalize_to_the_same_canonical_id():
    taxonomy = get_taxonomy()
    for alias in ("javascript", "JS", "  js  ", "ECMAScript"):
        assert taxonomy.normalize(alias) == "javascript"


def test_unrecognised_surface_form_returns_none():
    taxonomy = get_taxonomy()
    assert taxonomy.normalize("cobol-77-enterprise-edition") is None


def test_extract_prefers_the_longer_alias():
    taxonomy = get_taxonomy()
    found = taxonomy.extract("Built services with Spring Boot and deployed to AWS")
    assert "spring-boot" in found
    # "spring" alone must not also fire as a separate id once "spring boot"
    # (mapping to the same canonical id) has already matched.
    assert "spring" not in found
    assert "aws" in found


def test_extract_is_case_and_punctuation_insensitive():
    taxonomy = get_taxonomy()
    assert "nodejs" in taxonomy.extract("Experience with NODE.JS and Express")


def test_duplicate_skill_id_is_rejected():
    with pytest.raises(ValueError, match="duplicate skill id"):
        Taxonomy(
            [
                Skill(id="x", category="language", aliases=("x", "xx")),
                Skill(id="x", category="language", aliases=("xxx",)),
            ]
        )


def test_conflicting_alias_ownership_is_rejected():
    with pytest.raises(ValueError, match="claimed by both"):
        Taxonomy(
            [
                Skill(id="a", category="language", aliases=("shared",)),
                Skill(id="b", category="language", aliases=("shared",)),
            ]
        )


# -- Alias false-positive regression tests -----------------------------------
#
# Each of these pins a real false positive found auditing the taxonomy
# against 180 real, current postings pulled live via placeinator.jobs.sources
# .ats_feed (Greenhouse/Ashby, ADR 0003) -- not hypothetical edge cases.
# "security" and "c" were the #1 and #2 most-matched skills in that corpus
# before the fix, almost entirely from "we take security seriously"
# boilerplate and "Series C" funding mentions. "go" was 100% false positives
# in the same corpus -- every single match was "go-to-market". "excel" was
# majority false positive ("you excel in..."). "spark" looked like strong
# real evidence (24/180) until inspecting the actual matched text showed
# every hit was one company's repeated "spark innovation" boilerplate
# paragraph, not one real Apache Spark mention.


def test_bare_c_no_longer_matches_a_funding_round_mention():
    taxonomy = get_taxonomy()
    found = taxonomy.extract("We recently closed our Series C and are hiring fast")
    assert "c" not in found


def test_c_programming_still_matches():
    taxonomy = get_taxonomy()
    assert taxonomy.normalize("C programming") == "c"
    assert taxonomy.normalize("ANSI C") == "c"


def test_bare_security_no_longer_matches_generic_boilerplate():
    taxonomy = get_taxonomy()
    found = taxonomy.extract("We take security seriously and value job security")
    assert "cybersecurity" not in found


def test_cybersecurity_specific_terms_still_match():
    taxonomy = get_taxonomy()
    found = taxonomy.extract("3+ years in cybersecurity and penetration testing")
    assert "cybersecurity" in found


def test_bare_spring_no_longer_matches_a_season_mention():
    taxonomy = get_taxonomy()
    found = taxonomy.extract("This Spring 2027 internship program is open now")
    assert "spring-boot" not in found


def test_spring_boot_specific_terms_still_match():
    taxonomy = get_taxonomy()
    found = taxonomy.extract("Built services with Spring Boot and Spring Cloud")
    assert "spring-boot" in found


def test_bare_go_no_longer_matches_go_to_market():
    """The exact false positive found in the real corpus: every single
    "go" match was inside "go-to-market", never the Go language."""
    taxonomy = get_taxonomy()
    found = taxonomy.extract("Own our go-to-market strategy across three regions")
    assert "go" not in found


def test_golang_specific_terms_still_match():
    taxonomy = get_taxonomy()
    assert taxonomy.normalize("Golang") == "go"
    assert taxonomy.normalize("Google Go") == "go"


def test_bare_excel_no_longer_matches_the_verb():
    taxonomy = get_taxonomy()
    found = taxonomy.extract("We hire people who excel in ambiguous situations")
    assert "excel" not in found


def test_microsoft_excel_still_matches():
    taxonomy = get_taxonomy()
    assert taxonomy.normalize("Microsoft Excel") == "excel"


def test_bare_spark_no_longer_matches_marketing_boilerplate():
    """Pinned against the exact real false positive: a company's repeated
    "spark innovation" boilerplate, not any real Apache Spark mention."""
    taxonomy = get_taxonomy()
    found = taxonomy.extract("Our culture aims to spark innovation across teams")
    assert "spark" not in found


def test_apache_spark_still_matches():
    taxonomy = get_taxonomy()
    assert taxonomy.normalize("Apache Spark") == "spark"
    assert taxonomy.normalize("PySpark") == "spark"


def test_ruby_no_longer_has_a_garbled_alias():
    taxonomy = get_taxonomy()
    skill = taxonomy.get("ruby")
    assert skill is not None
    assert "ruby on rails' language" not in skill.aliases


def test_bare_asp_net_no_longer_conflates_with_dotnet_core():
    """"asp.net" alone (no "core") is classic ASP.NET Framework, a
    different technology from the dotnet-core id's real subject matter."""
    taxonomy = get_taxonomy()
    assert taxonomy.normalize("asp.net") is None
    assert taxonomy.normalize("asp.net core") == "dotnet-core"


def test_aws_services_are_distinct_ids_not_aliases_of_generic_aws():
    taxonomy = get_taxonomy()
    assert taxonomy.normalize("EC2") == "aws-ec2"
    assert taxonomy.normalize("S3") == "aws-s3"
    assert taxonomy.normalize("AWS Lambda") == "aws-lambda"
    assert taxonomy.normalize("AWS") == "aws"


def test_bare_lambda_does_not_falsely_match_aws_lambda():
    """A JD mentioning Python lambda expressions must not be read as
    wanting AWS Lambda experience -- the two share nothing but a word."""
    taxonomy = get_taxonomy()
    found = taxonomy.extract("Comfortable writing lambda functions in Python")
    assert "aws-lambda" not in found
