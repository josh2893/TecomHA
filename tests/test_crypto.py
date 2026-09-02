"""Encryption and path authentication tests.

Every constant here came from a packet capture of the official software. The
panel gives no feedback for a wrong key or credential, so these tests are the
only thing standing between a subtle encoding mistake and a silent failure in
the field.
"""

from __future__ import annotations


import pytest

# conftest.py registers the integration directory as a stand-in package, so
# these import without pulling in Home Assistant.
from tecom_cp import ctplus_crypto as crypto  # noqa: E402
from tecom_cp import ctplus_protocol as proto  # noqa: E402
from tecom_cp.twofish import Twofish  # noqa: E402


# --------------------------------------------------------------------------
# Twofish, against the published test vectors. The implementation is ours, so
# a failure here means the cipher itself is wrong, not the protocol.
# --------------------------------------------------------------------------

TWOFISH_VECTORS = [
    ("00000000000000000000000000000000",
     "00000000000000000000000000000000",
     "9F589F5CF6122C32B6BFEC2F2AE8C35A"),
    ("0123456789ABCDEFFEDCBA98765432100011223344556677",
     "00000000000000000000000000000000",
     "CFD1D2E5A9BE9CDF501F13B892BD2248"),
    ("0123456789ABCDEFFEDCBA987654321000112233445566778899AABBCCDDEEFF",
     "00000000000000000000000000000000",
     "37527BE0052334B89F0CFCCAE87CFA20"),
]


@pytest.mark.parametrize("key,plain,cipher", TWOFISH_VECTORS)
def test_twofish_vectors(key, plain, cipher):
    tf = Twofish(bytes.fromhex(key))
    assert tf.encrypt_block(bytes.fromhex(plain)).hex().upper() == cipher


@pytest.mark.parametrize("key,plain,cipher", TWOFISH_VECTORS)
def test_twofish_round_trip(key, plain, cipher):
    # An earlier revision encrypted correctly but decrypted wrongly, which is
    # exactly the fault that looks fine until traffic arrives.
    tf = Twofish(bytes.fromhex(key))
    assert tf.decrypt_block(bytes.fromhex(cipher)) == bytes.fromhex(plain)


# --------------------------------------------------------------------------
# Key derivation: the key text as ASCII, null padded. No hashing.
# --------------------------------------------------------------------------

def test_key_derivation_is_null_padded_ascii():
    assert crypto.derive_key("1234567890", crypto.ENC_AES_CBC_128) == b"1234567890" + b"\x00" * 6
    assert crypto.derive_key("1234567890", crypto.ENC_AES_CBC_256) == b"1234567890" + b"\x00" * 22
    assert crypto.derive_key("1234567890", crypto.ENC_TWOFISH_128) == b"1234567890" + b"\x00" * 6


def test_key_length_limits_match_the_panel():
    assert crypto.key_length_for(crypto.ENC_AES_CBC_128) == 16
    assert crypto.key_length_for(crypto.ENC_TWOFISH_128) == 16
    assert crypto.key_length_for(crypto.ENC_AES_CBC_256) == 32


def test_over_long_key_is_rejected():
    with pytest.raises(ValueError):
        crypto.derive_key("x" * 17, crypto.ENC_AES_CBC_128)


# --------------------------------------------------------------------------
# The datagram wrapper, identical for all three ciphers.
# --------------------------------------------------------------------------

# Captured session hello, encrypted with key "1234567890".
HELLO_PLAINTEXT = bytes.fromhex("5ea080000125019234c0")
CAPTURED = {
    crypto.ENC_AES_CBC_128:
        "761f22b2c1593d0bb87e0b606f990ba4000a3892a0f8431666eb0d241d9fed80fe686c000000",
    crypto.ENC_AES_CBC_256:
        None,   # exercised via round-trip below; the captured value differs by cipher
}


def test_wrapper_layout():
    c = crypto.CtplusCipher(crypto.ENC_AES_CBC_128, "1234567890")
    iv = bytes(range(16))
    dg = c.wrap(HELLO_PLAINTEXT, iv=iv)
    assert dg[:16] == iv
    assert int.from_bytes(dg[16:18], "big") == len(HELLO_PLAINTEXT)
    ciphertext = dg[18:-4]
    assert len(ciphertext) % 16 == 0
    assert dg[-4] == (0x5C + len(ciphertext)) & 0xFF
    assert dg[-3:] == b"\x00\x00\x00"


def test_captured_aes128_datagram_decrypts():
    c = crypto.CtplusCipher(crypto.ENC_AES_CBC_128, "1234567890")
    dg = bytes.fromhex(CAPTURED[crypto.ENC_AES_CBC_128])
    assert c.unwrap(dg) == HELLO_PLAINTEXT


def test_captured_datagram_re_encrypts_identically():
    # Reading the panel is only half of it; we must also produce datagrams it
    # will accept.
    c = crypto.CtplusCipher(crypto.ENC_AES_CBC_128, "1234567890")
    dg = bytes.fromhex(CAPTURED[crypto.ENC_AES_CBC_128])
    assert c.wrap(c.unwrap(dg), iv=dg[:16]) == dg


@pytest.mark.parametrize("enc_type", [
    crypto.ENC_AES_CBC_128, crypto.ENC_AES_CBC_256, crypto.ENC_TWOFISH_128,
])
@pytest.mark.parametrize("payload", [
    HELLO_PLAINTEXT,
    b"\x5e" * 1,
    bytes.fromhex("5e80800001923303000002000000135631302d30372e3637363933"),
    bytes(range(64)),
])
def test_round_trip_all_ciphers(enc_type, payload):
    c = crypto.CtplusCipher(enc_type, "1234567890")
    assert c.unwrap(c.wrap(payload)) == payload


def test_padding_is_zero_not_pkcs7():
    # The explicit length field makes zero padding unambiguous; assuming PKCS#7
    # would corrupt any frame whose length is already block aligned.
    c = crypto.CtplusCipher(crypto.ENC_AES_CBC_128, "1234567890")
    aligned = bytes(range(16))
    dg = c.wrap(aligned)
    assert len(dg[18:-4]) == 16          # no extra padding block
    assert c.unwrap(dg) == aligned


def test_unwrap_rejects_rubbish_rather_than_raising():
    c = crypto.CtplusCipher(crypto.ENC_AES_CBC_128, "1234567890")
    assert c.unwrap(b"") is None
    assert c.unwrap(b"\x00" * 8) is None
    assert c.unwrap(b"\x00" * 40) is None


def test_wrong_key_does_not_produce_a_valid_frame():
    right = crypto.CtplusCipher(crypto.ENC_AES_CBC_128, "1234567890")
    wrong = crypto.CtplusCipher(crypto.ENC_AES_CBC_128, "0987654321")
    dg = right.wrap(HELLO_PLAINTEXT)
    out = wrong.unwrap(dg)
    assert out != HELLO_PLAINTEXT
    assert proto.parse_frame(out) is None


def test_looks_encrypted_does_not_flag_plaintext():
    assert not crypto.looks_encrypted(HELLO_PLAINTEXT)
    c = crypto.CtplusCipher(crypto.ENC_AES_CBC_128, "1234567890")
    dg = c.wrap(HELLO_PLAINTEXT, iv=bytes(range(16)))
    assert crypto.looks_encrypted(dg)


# --------------------------------------------------------------------------
# Path authentication
# --------------------------------------------------------------------------

def test_security_password_is_nibble_swapped_bcd():
    # Captured with the panel password set to 1234567890.
    assert proto.encode_security_password("1234567890") == bytes.fromhex("2143658709")
    assert proto.encode_security_password("0000000000") == bytes(5)


def test_security_password_frame_matches_capture():
    assert proto.cmd_session_auth_security_password("1234567890") == bytes.fromhex("01060b2143658709")


def test_default_security_password_matches_previous_hardcoded_frame():
    # Builds before this release always sent this. The config entry migration
    # relies on it being byte-identical, or existing installs would break.
    assert proto.cmd_session_auth_security_password(proto.DEFAULT_SECURITY_PASSWORD) == bytes.fromhex("01060b0000000000")
    assert proto.cmd_session_params() == bytes.fromhex("01060b0000000000")


@pytest.mark.parametrize("bad", ["123", "", "12345678901", "12345abcde", None])
def test_security_password_rejects_anything_but_ten_digits(bad):
    with pytest.raises(ValueError):
        proto.encode_security_password(bad)


def test_credentials_frame_matches_capture():
    expected = (
        "01310a1e"                                    # cmd, len, method, field width
        "544553545553455231" + "00" * 21 +            # "TESTUSER1" padded to 30
        "10"                                          # password field width
        "39383736353433323130" + "00" * 6             # "9876543210" padded to 16
    )
    assert proto.cmd_session_auth_credentials("TESTUSER1", "9876543210").hex() == expected


def test_credential_field_widths():
    frame = proto.cmd_session_auth_credentials("u", "p")
    # 0x01, length, method, 30-byte field marker, username, 16-byte marker, password
    assert frame[0] == 0x01
    assert frame[2] == proto.AUTH_USERNAME_PASSWORD
    assert frame[3] == proto.AUTH_USERNAME_FIELD == 30
    assert frame[3 + 1 + 30] == proto.AUTH_PASSWORD_FIELD == 16
    assert len(frame) == 2 + 1 + 1 + 30 + 1 + 16


@pytest.mark.parametrize("user,pw", [("x" * 31, "p"), ("u", "x" * 17)])
def test_credentials_reject_over_long_values(user, pw):
    with pytest.raises(ValueError):
        proto.cmd_session_auth_credentials(user, pw)
