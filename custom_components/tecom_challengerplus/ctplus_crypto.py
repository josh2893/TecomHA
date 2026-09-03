"""Encrypted transport wrapper for CTPlus comms paths.

The panel can encrypt a comms path with one of three ciphers. All three use the
same datagram wrapper, confirmed against captures of the official software::

    IV          16 bytes   plaintext, prepended
    length       2 bytes   big endian, plaintext length before padding
    ciphertext   n x 16    CBC mode, zero padded to a block boundary

The ciphertext ends at the UDP payload boundary. The four-byte "trailer" in
3.4.0/3.4.1 was a PCAPNG block footer accidentally included by the capture
reader. Corrected extraction of 552 datagrams confirms this layout for both
authentication methods and all three ciphers.

The key is the configured key string as raw ASCII, null padded to the cipher's
key length. There is no hashing or derivation step. The panel documentation
limits the key to 16 characters for the 128-bit ciphers and 32 for AES 256,
which is exactly the padded length. Short keys leave more zero-filled bytes
and provide less entropy than longer mixed keys.

Padding is zero bytes rather than PKCS#7; the explicit length field makes it
unambiguous.
"""

from __future__ import annotations

from .twofish import Twofish

ENC_NONE = "none"
ENC_TWOFISH_128 = "twofish_128"
ENC_AES_CBC_128 = "aes_cbc_128"
ENC_AES_CBC_256 = "aes_cbc_256"

# Key length in bytes, and the maximum key characters the panel accepts.
_CIPHER_SPECS = {
    ENC_TWOFISH_128: (16, "twofish"),
    ENC_AES_CBC_128: (16, "aes"),
    ENC_AES_CBC_256: (32, "aes"),
}

IV_LEN = 16
BLOCK_LEN = 16


def key_length_for(enc_type: str) -> int:
    """Maximum key characters for an encryption type (0 when not encrypted)."""
    spec = _CIPHER_SPECS.get(enc_type)
    return spec[0] if spec else 0


def derive_key(key_text: str, enc_type: str) -> bytes:
    """Key bytes for a cipher: the key text as ASCII, null padded."""
    spec = _CIPHER_SPECS.get(enc_type)
    if not spec:
        raise ValueError(f"Unsupported encryption type: {enc_type}")
    size = spec[0]
    raw = (key_text or "").encode("ascii", errors="strict")
    if len(raw) > size:
        raise ValueError(f"Key too long for {enc_type}: max {size} characters")
    return raw.ljust(size, b"\x00")


class _AesCbc:
    """AES-CBC via the cryptography package.

    Home Assistant ships cryptography, so this adds no requirement to
    manifest.json. It is imported lazily and with a clear failure message all
    the same: a bare ImportError from inside a constructor tells a user nothing
    about what to do, and Twofish still works without it.
    """

    def __init__(self, key: bytes) -> None:
        try:
            from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        except ImportError as err:  # pragma: no cover - depends on the environment
            raise RuntimeError(
                "AES path encryption requires the 'cryptography' package, which "
                "Home Assistant normally provides. Install it, or select TwoFish "
                "on the panel's comms path, which needs no extra packages."
            ) from err

        self._Cipher = Cipher
        self._algorithms = algorithms
        self._modes = modes
        self._key = key

    def encrypt(self, iv: bytes, data: bytes) -> bytes:
        enc = self._Cipher(self._algorithms.AES(self._key), self._modes.CBC(iv)).encryptor()
        return enc.update(data) + enc.finalize()

    def decrypt(self, iv: bytes, data: bytes) -> bytes:
        dec = self._Cipher(self._algorithms.AES(self._key), self._modes.CBC(iv)).decryptor()
        return dec.update(data) + dec.finalize()


class _TwofishCbc:
    """Twofish-CBC. Pure Python, so noticeably slower than AES.

    Fine at CTPlus frame rates (a handful of small frames per second), but AES
    should be preferred where the panel allows a choice.
    """

    def __init__(self, key: bytes) -> None:
        self._tf = Twofish(key)

    def encrypt(self, iv: bytes, data: bytes) -> bytes:
        out = bytearray()
        prev = iv
        for i in range(0, len(data), BLOCK_LEN):
            block = bytes(a ^ b for a, b in zip(data[i:i + BLOCK_LEN], prev))
            prev = self._tf.encrypt_block(block)
            out += prev
        return bytes(out)

    def decrypt(self, iv: bytes, data: bytes) -> bytes:
        out = bytearray()
        prev = iv
        for i in range(0, len(data), BLOCK_LEN):
            block = data[i:i + BLOCK_LEN]
            out += bytes(a ^ b for a, b in zip(self._tf.decrypt_block(block), prev))
            prev = block
        return bytes(out)


class CtplusCipher:
    """Wraps and unwraps CTPlus datagrams for an encrypted comms path."""

    def __init__(self, enc_type: str, key_text: str) -> None:
        if enc_type not in _CIPHER_SPECS:
            raise ValueError(f"Unsupported encryption type: {enc_type}")
        self.enc_type = enc_type
        key = derive_key(key_text, enc_type)
        self._impl = _TwofishCbc(key) if _CIPHER_SPECS[enc_type][1] == "twofish" else _AesCbc(key)

    def wrap(self, plaintext: bytes, iv: bytes | None = None) -> bytes:
        """Encrypt one frame into a datagram ready to send."""
        if iv is None:
            import os

            iv = os.urandom(IV_LEN)
        if len(iv) != IV_LEN:
            raise ValueError("IV must be 16 bytes")
        padded = plaintext + b"\x00" * (-len(plaintext) % BLOCK_LEN)
        ciphertext = self._impl.encrypt(iv, padded)
        return iv + len(plaintext).to_bytes(2, "big") + ciphertext

    def unwrap(self, datagram: bytes) -> bytes | None:
        """Decrypt a received datagram, or None if it is not a valid wrapper.

        Returning None rather than raising lets the caller treat a run of
        failures as a probable key mismatch, which is the only signal available
        -- the panel does not report one.
        """
        if not looks_encrypted(datagram):
            return None
        iv = datagram[:IV_LEN]
        length = int.from_bytes(datagram[IV_LEN:IV_LEN + 2], "big")
        ciphertext = datagram[IV_LEN + 2:]
        try:
            plaintext = self._impl.decrypt(iv, ciphertext)
        except Exception:
            return None
        if any(plaintext[length:]):
            return None
        return plaintext[:length]


def looks_encrypted(datagram: bytes) -> bool:
    """Heuristic: does this datagram look like the encrypted wrapper?

    Check the length field and block alignment. The IV is arbitrary and may
    start with 0x5E, just like a plaintext frame. This does not establish that
    decryption succeeded; the receiver must also validate the frame CRC.
    """
    if len(datagram) < IV_LEN + 2 + BLOCK_LEN:
        return False
    ciphertext_len = len(datagram) - IV_LEN - 2
    if ciphertext_len % BLOCK_LEN:
        return False
    length = int.from_bytes(datagram[IV_LEN:IV_LEN + 2], "big")
    return 0 < length <= ciphertext_len < length + BLOCK_LEN
