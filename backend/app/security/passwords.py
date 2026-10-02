"""Password policy for local accounts: length plus a common-password screen.

The list is the subset of widely published breach/top-password lists that would pass
the 10-character minimum on their own. It is a floor, not a breach-corpus check.
"""

from __future__ import annotations

MIN_LENGTH = 10
MAX_LENGTH = 256

_COMMON = frozenset(
    p.lower()
    for p in (
        "1234567890", "12345678910", "123456789a", "0123456789", "0987654321", "1234567890a",
        "1q2w3e4r5t", "1q2w3e4r5t6y", "q1w2e3r4t5", "1qaz2wsx3edc", "qwertyuiop", "qwertyuiop1",
        "asdfghjkl1", "zxcvbnm123", "qwerty1234", "qwerty12345", "qwerty123456", "asdfghjkl;",
        "password12", "password123", "password1234", "password!1", "password!", "passw0rd123",
        "p@ssw0rd123", "p@ssword123", "p4ssw0rd123", "iloveyou12", "iloveyou123", "princess12",
        "football12", "football123", "baseball12", "baseball123", "basketball", "basketball1",
        "superman12", "superman123", "starwars12", "starwars123", "welcome123", "welcome1234",
        "letmein123", "letmein1234", "sunshine12", "sunshine123", "michael123", "charlie123",
        "jennifer12", "trustno1234", "dragon1234", "monkey1234", "master1234", "shadow1234",
        "1111111111", "0000000000", "2222222222", "1212121212", "1122334455", "1234554321",
        "abcdefghij", "abcdefghijk", "abcd123456", "abc1234567", "a123456789", "aa12345678",
        "administrator", "admin12345", "admin123456", "administrator1", "changeme123", "changeme12",
        "computer12", "computer123", "internet12", "whatever12", "qazwsxedcrfv", "zaq12wsxcde",
        "chocolate1", "chocolate12", "liverpool1", "liverpool12", "manchester", "manchester1",
        "pakistan123", "metallica1", "mustang123", "soccer1234", "hockey1234", "summer2024",
        "summer2025", "summer2026", "winter2024", "winter2025", "winter2026", "spring2025",
        "spring2026", "autumn2025", "autumn2026", "january2026", "october2026", "company123",
        "testtest12", "test123456", "testing123", "default123", "secret1234", "mypassword",
        "mypassword1", "yourpassword", "letmeinplease", "passwordpassword",
    )
)


def password_problem(password: str, email: str | None = None) -> str | None:
    """Human-readable reason the password is unacceptable, or None when it is fine."""
    if len(password) < MIN_LENGTH:
        return f"password must be at least {MIN_LENGTH} characters"
    if len(password) > MAX_LENGTH:
        return f"password must be at most {MAX_LENGTH} characters"
    lowered = password.lower()
    if lowered in _COMMON or ("password" in lowered and len(set(lowered.replace("password", ""))) < 4):
        return "that password is too common; choose a longer, unique passphrase"
    if len(set(password)) < 4:
        return "password needs more variety than a few repeated characters"
    if email:
        local = email.split("@", 1)[0].lower()
        if len(local) >= 4 and local in lowered and len(lowered) - len(local) < 6:
            return "password must not be based on your email address"
    return None
