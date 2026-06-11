from backend.app.repositories import find_user_match


def test_user_matching_empty_database_returns_no_match(tmp_path, monkeypatch):
    monkeypatch.setattr("backend.app.repositories.list_users", lambda: [])
    user_id, confidence = find_user_match({"pan": "ABCDE1234F", "extracted_text": "Akshay"})
    assert user_id is None
    assert confidence == 0


def test_user_matching_prefers_pan(monkeypatch):
    monkeypatch.setattr(
        "backend.app.repositories.list_users",
        lambda: [{"id": 7, "name": "Akshay", "pan": "ABCDE1234F", "aliases": "", "profile_hints": ""}],
    )
    user_id, confidence = find_user_match({"pan": "ABCDE1234F", "extracted_text": "Random text"})
    assert user_id == 7
    assert confidence >= 0.95


def test_user_matching_handles_reversed_names(monkeypatch):
    monkeypatch.setattr(
        "backend.app.repositories.list_users",
        lambda: [{"id": 7, "name": "Akshay Bhatnagar", "pan": "ABCDE1234F", "aliases": "", "profile_hints": ""}],
    )
    user_id, confidence = find_user_match({"name": "Bhatnagar Akshay", "extracted_text": "Employee Name Bhatnagar Akshay"})
    assert user_id == 7
    assert confidence >= 0.5


def test_user_matching_handles_small_name_typos(monkeypatch):
    monkeypatch.setattr(
        "backend.app.repositories.list_users",
        lambda: [{"id": 7, "name": "Akshay Bhatnagar", "pan": "ABCDE1234F", "aliases": "", "profile_hints": ""}],
    )
    user_id, confidence = find_user_match({"name": "Aakshay Bhatnagar", "extracted_text": "Employee Name Aakshay Bhatnagar"})
    assert user_id == 7
    assert confidence >= 0.5
