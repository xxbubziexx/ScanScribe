"""Unit tests for PII/SSN redaction system."""
from app.services.redaction_service import redact_ssn


def test_standard_ssn_formats():
    assert redact_ssn("Subject SSN is 123-45-6789.") == "Subject SSN is [REDACTED SSN]."
    assert redact_ssn("SSN: 123 45 6789") == "SSN: [REDACTED SSN]"
    assert redact_ssn("123.45.6789 on file") == "[REDACTED SSN] on file"
    assert redact_ssn("Run 584-32-9012 for 10-27.") == "Run [REDACTED SSN] for 10-27."


def test_real_world_dispatch_transcripts():
    # 3-digit hyphen 6-digit with repeat
    t1 = "social is 488-151923 repeating 488-151923."
    assert redact_ssn(t1) == "social is [REDACTED SSN] repeating [REDACTED SSN]."

    # Comma separated groupings
    t2 = "with social 498, 08, 4613."
    assert redact_ssn(t2) == "with social [REDACTED SSN]."

    t3 = "with a social 499, 156168."
    assert redact_ssn(t3) == "with a social [REDACTED SSN]."

    # Repeated comma-separated stuttered numbers
    t4 = "Social 493-155-5862, 493-155-5862."
    assert redact_ssn(t4) == "Social [REDACTED SSN], [REDACTED SSN]."

    # Single digits separated by hyphens and commas
    t5 = "Social security number 4-9-2, 0-2, 2624, Levin Smith, first name Sarah."
    assert redact_ssn(t5) == "Social security number [REDACTED SSN], Levin Smith, first name Sarah."

    t6 = "social 4-9-1, 8-6, 7-5, 8-1."
    assert redact_ssn(t6) == "social [REDACTED SSN]."

    # Number stream with filler phrase
    t7 = "Can I get a social on female? 497211, 1130."
    assert redact_ssn(t7) == "Can I get a social on female? [REDACTED SSN]."

    t8 = "going to do social it is going to be 489-788-8387, 489-788-387."
    assert redact_ssn(t8) == "going to do social it is going to be [REDACTED SSN], [REDACTED SSN]."

    # Raw 9-digit sequence following SSN
    t9 = "Subject has SSN 123456789 on file."
    assert redact_ssn(t9) == "Subject has SSN [REDACTED SSN] on file."


def test_spoken_digit_words():
    t = "social is four eight eight one five one nine two three."
    assert redact_ssn(t) == "social is [REDACTED SSN]."


def test_false_positive_preservation():
    # 10-digit phone numbers must NOT be redacted
    assert redact_ssn("Call me at 314-555-1234 on cell.") == "Call me at 314-555-1234 on cell."

    # Police unit numbers and 10-codes must NOT be redacted
    assert redact_ssn("Unit 407 responding to 10-50 at mile marker 155.") == "Unit 407 responding to 10-50 at mile marker 155."

    # Street addresses must NOT be redacted
    assert redact_ssn("Address is 12834 Springtown Road.") == "Address is 12834 Springtown Road."

    # Questions mentioning "social" without digits must NOT be altered
    assert redact_ssn("Do you have a social or OLN I am not getting a return.") == "Do you have a social or OLN I am not getting a return."

    # Short 3-digit number after social security must NOT be redacted (incomplete/truncated)
    assert redact_ssn("Roger Social security number on the first is going to be 586.") == "Roger Social security number on the first is going to be 586."


def test_custom_replacement():
    t = "His SSN is 123-45-6789 please."
    assert redact_ssn(t, replacement="***-**-****") == "His SSN is ***-**-**** please."
    assert redact_ssn(t, replacement="[CENSORED]") == "His SSN is [CENSORED] please."


def test_empty_and_none_input():
    assert redact_ssn("") == ""
    assert redact_ssn(None) is None


if __name__ == "__main__":
    test_standard_ssn_formats()
    print("✅ test_standard_ssn_formats passed")
    test_real_world_dispatch_transcripts()
    print("✅ test_real_world_dispatch_transcripts passed")
    test_spoken_digit_words()
    print("✅ test_spoken_digit_words passed")
    test_false_positive_preservation()
    print("✅ test_false_positive_preservation passed")
    test_custom_replacement()
    print("✅ test_custom_replacement passed")
    test_empty_and_none_input()
    print("✅ test_empty_and_none_input passed")
    print("\n🎉 ALL 6 TEST SUITES PASSED!")
