"""Twofish block cipher, pure Python.

The panel offers Twofish 128 alongside AES for encrypted comms paths. No
maintained Python package provides it (the one on PyPI is a C extension that no
longer builds), and this integration deliberately ships no runtime
dependencies, so it is implemented here from the specification.

Only what the protocol needs is provided: 128-bit blocks, key sizes of 128,
192 and 256 bits, single-block encrypt and decrypt. CBC chaining is handled by
the caller.

Correctness is checked against the published test vectors in the test suite;
do not modify without re-running them.
"""

from __future__ import annotations

# 4-bit permutations that build the q0/q1 byte permutations. Generating the
# 256-entry tables from these is less error-prone than transcribing them.
_Q0_T = (
    (0x8, 0x1, 0x7, 0xD, 0x6, 0xF, 0x3, 0x2, 0x0, 0xB, 0x5, 0x9, 0xE, 0xC, 0xA, 0x4),
    (0xE, 0xC, 0xB, 0x8, 0x1, 0x2, 0x3, 0x5, 0xF, 0x4, 0xA, 0x6, 0x7, 0x0, 0x9, 0xD),
    (0xB, 0xA, 0x5, 0xE, 0x6, 0xD, 0x9, 0x0, 0xC, 0x8, 0xF, 0x3, 0x2, 0x4, 0x7, 0x1),
    (0xD, 0x7, 0xF, 0x4, 0x1, 0x2, 0x6, 0xE, 0x9, 0xB, 0x3, 0x0, 0x8, 0x5, 0xC, 0xA),
)
_Q1_T = (
    (0x2, 0x8, 0xB, 0xD, 0xF, 0x7, 0x6, 0xE, 0x3, 0x1, 0x9, 0x4, 0x0, 0xA, 0xC, 0x5),
    (0x1, 0xE, 0x2, 0xB, 0x4, 0xC, 0x3, 0x7, 0x6, 0xD, 0xA, 0x5, 0xF, 0x9, 0x0, 0x8),
    (0x4, 0xC, 0x7, 0x5, 0x1, 0x6, 0x9, 0xA, 0x0, 0xE, 0xD, 0x8, 0x2, 0xB, 0x3, 0xF),
    (0xB, 0x9, 0x5, 0x1, 0xC, 0x3, 0xD, 0xE, 0x6, 0x4, 0x7, 0xF, 0x2, 0x0, 0x8, 0xA),
)


def _build_q(t):
    out = []
    for x in range(256):
        a0, b0 = x >> 4, x & 0xF
        a1 = a0 ^ b0
        b1 = (a0 ^ ((b0 >> 1) | ((b0 & 1) << 3)) ^ (8 * a0)) & 0xF
        a2, b2 = t[0][a1], t[1][b1]
        a3 = a2 ^ b2
        b3 = (a2 ^ ((b2 >> 1) | ((b2 & 1) << 3)) ^ (8 * a2)) & 0xF
        a4, b4 = t[2][a3], t[3][b3]
        out.append((b4 << 4) | a4)
    return tuple(out)


_Q0 = _build_q(_Q0_T)
_Q1 = _build_q(_Q1_T)

_MDS_POLY = 0x169  # x^8 + x^6 + x^5 + x^3 + 1
_RS_POLY = 0x14D   # x^8 + x^6 + x^3 + x^2 + 1


def _gf_mul(a: int, b: int, poly: int) -> int:
    result = 0
    while b:
        if b & 1:
            result ^= a
        a <<= 1
        if a & 0x100:
            a ^= poly
        b >>= 1
    return result & 0xFF


_MDS = ((0x01, 0xEF, 0x5B, 0x5B),
        (0x5B, 0xEF, 0xEF, 0x01),
        (0xEF, 0x5B, 0x01, 0xEF),
        (0xEF, 0x01, 0xEF, 0x5B))

_RS = ((0x01, 0xA4, 0x55, 0x87, 0x5A, 0x58, 0xDB, 0x9E),
       (0xA4, 0x56, 0x82, 0xF3, 0x1E, 0xC6, 0x68, 0xE5),
       (0x02, 0xA1, 0xFC, 0xC1, 0x47, 0xAE, 0x3D, 0x19),
       (0xA4, 0x55, 0x87, 0x5A, 0x58, 0xDB, 0x9E, 0x03))


def _mds_multiply(y: bytes) -> int:
    z = []
    for row in _MDS:
        acc = 0
        for coeff, val in zip(row, y):
            acc ^= _gf_mul(coeff, val, _MDS_POLY)
        z.append(acc)
    return z[0] | (z[1] << 8) | (z[2] << 16) | (z[3] << 24)


def _rs_encode(key_bytes: bytes) -> int:
    """Reed-Solomon reduction producing one S-box key word from 8 key bytes."""
    out = []
    for row in _RS:
        acc = 0
        for coeff, val in zip(row, key_bytes):
            acc ^= _gf_mul(coeff, val, _RS_POLY)
        out.append(acc)
    return out[0] | (out[1] << 8) | (out[2] << 16) | (out[3] << 24)


def _h(x: int, key_words: list[int], k: int) -> int:
    """The h function: key-dependent byte permutations followed by MDS."""
    b = [(x >> 24) & 0xFF, (x >> 16) & 0xFF, (x >> 8) & 0xFF, x & 0xFF]
    y = [b[3], b[2], b[1], b[0]]  # little-endian byte order

    if k == 4:
        y[0] = _Q1[y[0]] ^ (key_words[3] & 0xFF)
        y[1] = _Q0[y[1]] ^ ((key_words[3] >> 8) & 0xFF)
        y[2] = _Q0[y[2]] ^ ((key_words[3] >> 16) & 0xFF)
        y[3] = _Q1[y[3]] ^ ((key_words[3] >> 24) & 0xFF)
    if k >= 3:
        y[0] = _Q1[y[0]] ^ (key_words[2] & 0xFF)
        y[1] = _Q1[y[1]] ^ ((key_words[2] >> 8) & 0xFF)
        y[2] = _Q0[y[2]] ^ ((key_words[2] >> 16) & 0xFF)
        y[3] = _Q0[y[3]] ^ ((key_words[2] >> 24) & 0xFF)

    y[0] = _Q1[_Q0[_Q0[y[0]] ^ (key_words[1] & 0xFF)] ^ (key_words[0] & 0xFF)]
    y[1] = _Q0[_Q0[_Q1[y[1]] ^ ((key_words[1] >> 8) & 0xFF)] ^ ((key_words[0] >> 8) & 0xFF)]
    y[2] = _Q1[_Q1[_Q0[y[2]] ^ ((key_words[1] >> 16) & 0xFF)] ^ ((key_words[0] >> 16) & 0xFF)]
    y[3] = _Q0[_Q1[_Q1[y[3]] ^ ((key_words[1] >> 24) & 0xFF)] ^ ((key_words[0] >> 24) & 0xFF)]

    return _mds_multiply(bytes(y))


def _rol32(x: int, n: int) -> int:
    n &= 31
    return ((x << n) | (x >> (32 - n))) & 0xFFFFFFFF


def _ror32(x: int, n: int) -> int:
    n &= 31
    return ((x >> n) | (x << (32 - n))) & 0xFFFFFFFF


class Twofish:
    """Single-block Twofish. Key must be 16, 24 or 32 bytes."""

    def __init__(self, key: bytes) -> None:
        if len(key) not in (16, 24, 32):
            raise ValueError("Twofish key must be 16, 24 or 32 bytes")
        self._key = key
        k = len(key) // 8          # 2, 3 or 4
        words = [int.from_bytes(key[i * 4:i * 4 + 4], "little") for i in range(len(key) // 4)]
        me = [words[i] for i in range(0, len(words), 2)]
        mo = [words[i] for i in range(1, len(words), 2)]

        # S-box key words, derived by Reed-Solomon reduction over key byte groups
        self._s = []
        for i in range(k):
            self._s.append(_rs_encode(key[i * 8:(i + 1) * 8]))
        self._s.reverse()

        # Round key expansion
        self._subkeys = []
        rho = 0x01010101
        for i in range(20):
            a = _h((2 * i) * rho, me, k)
            b = _rol32(_h((2 * i + 1) * rho, mo, k), 8)
            ab = (a + b) & 0xFFFFFFFF
            self._subkeys.append(ab)
            self._subkeys.append(_rol32((ab + b) & 0xFFFFFFFF, 9))
        self._k = k

    def _g(self, x: int) -> int:
        return _h(x, self._s, self._k)

    def encrypt_block(self, block: bytes) -> bytes:
        if len(block) != 16:
            raise ValueError("Twofish block must be 16 bytes")
        r = [int.from_bytes(block[i * 4:i * 4 + 4], "little") ^ self._subkeys[i] for i in range(4)]
        for i in range(16):
            t0 = self._g(r[0])
            t1 = self._g(_rol32(r[1], 8))
            r2 = _ror32(r[2] ^ ((t0 + t1 + self._subkeys[8 + 2 * i]) & 0xFFFFFFFF), 1)
            r3 = _rol32(r[3], 1) ^ ((t0 + 2 * t1 + self._subkeys[9 + 2 * i]) & 0xFFFFFFFF)
            r = [r2, r3 & 0xFFFFFFFF, r[0], r[1]]
        out = [r[(i + 2) % 4] ^ self._subkeys[4 + i] for i in range(4)]
        return b"".join(w.to_bytes(4, "little") for w in out)

    def decrypt_block(self, block: bytes) -> bytes:
        if len(block) != 16:
            raise ValueError("Twofish block must be 16 bytes")
        c = [int.from_bytes(block[i * 4:i * 4 + 4], "little") for i in range(4)]
        # Undo output whitening and the final swap in one step: encryption ends
        # with out[i] = r[(i + 2) % 4] ^ subkey[4 + i].
        r = [0, 0, 0, 0]
        for i in range(4):
            r[(i + 2) % 4] = c[i] ^ self._subkeys[4 + i]

        for i in range(15, -1, -1):
            prev0, prev1 = r[2], r[3]
            t0 = self._g(prev0)
            t1 = self._g(_rol32(prev1, 8))
            prev2 = _rol32(r[0], 1) ^ ((t0 + t1 + self._subkeys[8 + 2 * i]) & 0xFFFFFFFF)
            prev3 = _ror32(r[1] ^ ((t0 + 2 * t1 + self._subkeys[9 + 2 * i]) & 0xFFFFFFFF), 1)
            r = [prev0, prev1, prev2 & 0xFFFFFFFF, prev3]

        out = [r[i] ^ self._subkeys[i] for i in range(4)]
        return b"".join(w.to_bytes(4, "little") for w in out)
