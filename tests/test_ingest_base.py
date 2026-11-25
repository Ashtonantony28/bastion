import json

import pytest

from bastion.ingest.base import DownloadItem, HttpClient, PinMismatchError, Pins, materialise


def _item(rel, payload):
    return DownloadItem(rel, lambda: payload, url="https://example.invalid/" + rel)


def test_unpinned_then_pin_then_ok(tmp_path):
    pins = Pins(path=tmp_path / "pins.json")
    raw = tmp_path / "raw"
    assert materialise([_item("a/x.csv", b"1")], raw, pins)[0].status == "unpinned"
    assert materialise([_item("a/x.csv", b"1")], raw, pins, pin=True)[0].status == "pinned-new"
    saved = json.loads((tmp_path / "pins.json").read_text())
    assert saved["a/x.csv"]["bytes"] == 1
    assert (
        materialise([_item("a/x.csv", b"1")], raw, Pins.load(tmp_path / "pins.json"))[0].status
        == "pinned-ok"
    )
    assert (raw / "a/x.csv").read_bytes() == b"1"


def test_drift_fails_and_does_not_overwrite(tmp_path):
    pins = Pins(path=tmp_path / "pins.json")
    raw = tmp_path / "raw"
    materialise([_item("x.csv", b"old")], raw, pins, pin=True)
    with pytest.raises(PinMismatchError):
        materialise([_item("x.csv", b"new")], raw, pins)
    assert (raw / "x.csv").read_bytes() == b"old"
    assert (
        materialise([_item("x.csv", b"new")], raw, pins, allow_drift=True)[0].status
        == "drift-allowed"
    )


def test_pins_file_is_sorted(tmp_path):
    pins = Pins(path=tmp_path / "pins.json")
    materialise([_item("b", b"2"), _item("a", b"1")], tmp_path / "raw", pins, pin=True)
    assert list(json.loads((tmp_path / "pins.json").read_text())) == ["a", "b"]


class _FakeResp:
    def __init__(self, code, content=b""):
        self.status_code, self.content, self.text = code, content, content.decode()


class _FakeSession:
    def __init__(self, codes):
        self.codes, self.headers, self.calls = list(codes), {}, 0

    def get(self, url, params=None, timeout=None):
        self.calls += 1
        return _FakeResp(self.codes.pop(0), b"ok")


def test_http_client_retries_transient_errors():
    s = _FakeSession([503, 429, 200])
    assert HttpClient(session=s, sleep=lambda _: None).get("https://x.invalid") == b"ok"
    assert s.calls == 3
    assert "bastion-research" in s.headers["User-Agent"]


def test_http_client_does_not_retry_404():
    s = _FakeSession([404])
    with pytest.raises(RuntimeError, match="404"):
        HttpClient(session=s, sleep=lambda _: None).get("https://x.invalid")
    assert s.calls == 1
