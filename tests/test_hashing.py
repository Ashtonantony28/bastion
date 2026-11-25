import numpy as np
import pandas as pd

from bastion.hashing import frame_hash, sha256_bytes


def test_sha256_bytes_known_vector():
    assert (
        sha256_bytes(b"abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )


def test_frame_hash_ignores_row_and_column_order_when_sorted():
    a = pd.DataFrame({"k": [1, 2, 3], "v": [0.1, 0.2, np.nan]})
    b = a.iloc[::-1][["v", "k"]]
    assert frame_hash(a, sort_by=["k"]) == frame_hash(b, sort_by=["k"])


def test_frame_hash_detects_small_numeric_change():
    a = pd.DataFrame({"k": [1, 2], "v": [0.1, 0.2]})
    b = a.assign(v=[0.1, 0.2 + 1e-9])
    assert frame_hash(a) != frame_hash(b)
