from app.services.auth import hash_password, hash_token, new_session_token, verify_password


def test_hash_round_trip():
    stored = hash_password("hola1234")
    assert stored.startswith("scrypt$")
    assert "hola1234" not in stored
    assert verify_password("hola1234", stored)
    assert not verify_password("hola12345", stored)


def test_same_password_gets_different_salts():
    assert hash_password("same") != hash_password("same")


def test_verify_rejects_missing_or_malformed_hash():
    assert not verify_password("anything", None)
    assert not verify_password("anything", "")
    assert not verify_password("anything", "not-a-hash")
    assert not verify_password("anything", "bcrypt$1$2$3$aa$bb")
    assert not verify_password("anything", "scrypt$16384$8$1$zz$zz")


def test_session_tokens_are_unique_and_only_hash_is_stored():
    a, b = new_session_token(), new_session_token()
    assert a != b
    assert len(hash_token(a)) == 64
    assert hash_token(a) == hash_token(a)
    assert hash_token(a) != a
