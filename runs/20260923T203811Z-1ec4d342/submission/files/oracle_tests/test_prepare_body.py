"""Focused tests for PreparedRequest.prepare_body."""

from io import BytesIO

import pytest

from requests.models import PreparedRequest


@pytest.fixture
def prepared_request():
    request = PreparedRequest()
    request.prepare_headers({})
    return request


@pytest.mark.parametrize("data", [None, "", b"", {}])
def test_empty_body_has_zero_length_and_no_content_type(prepared_request, data):
    prepared_request.prepare_body(data, None)

    assert prepared_request.body is None
    assert prepared_request.headers["Content-Length"] == "0"
    assert "Content-Type" not in prepared_request.headers
    assert "Transfer-Encoding" not in prepared_request.headers


@pytest.mark.parametrize(
    ("data", "content_type"),
    [("caf\u00e9", None), (b"raw\x00bytes", "application/x-www-form-urlencoded")],
)
def test_raw_text_and_bytes_are_not_form_encoded(prepared_request, data, content_type):
    prepared_request.prepare_body(data, None)

    assert prepared_request.body == data
    assert prepared_request.headers["Content-Length"] == str(len(data))
    assert prepared_request.headers.get("Content-Type") == content_type


def test_form_fields_are_urlencoded_and_have_encoded_length(prepared_request):
    prepared_request.prepare_body(
        {"name": "caf\u00e9", "tags": ["one two", "three"], "skip": None}, None
    )

    assert prepared_request.body == "name=caf%C3%A9&tags=one+two&tags=three"
    assert prepared_request.headers["Content-Length"] == str(len(prepared_request.body))
    assert prepared_request.headers["Content-Type"] == "application/x-www-form-urlencoded"


def test_existing_content_type_is_not_overwritten_for_form(prepared_request):
    prepared_request.prepare_headers({"content-type": "application/custom"})

    prepared_request.prepare_body({"key": "value"}, None)

    assert prepared_request.body == "key=value"
    assert prepared_request.headers["Content-Type"] == "application/custom"
    assert prepared_request.headers["Content-Length"] == "9"


def test_multipart_upload_contains_fields_and_explicit_file_type(prepared_request):
    prepared_request.prepare_body(
        {"title": "example", "tags": ["first", "second"]},
        {"attachment": ("report.txt", BytesIO(b"file contents"), "text/plain")},
    )

    body = prepared_request.body
    content_type = prepared_request.headers["Content-Type"]
    assert content_type.startswith(b"multipart/form-data; boundary=")
    boundary = content_type.split(b"boundary=", 1)[1]
    assert body.startswith(b"--" + boundary + b"\r\n")
    assert body.endswith(b"--" + boundary + b"--\r\n")
    assert b'Content-Disposition: form-data; name="title"\r\n\r\nexample\r\n' in body
    assert b'Content-Disposition: form-data; name="tags"\r\n\r\nfirst\r\n' in body
    assert b'Content-Disposition: form-data; name="tags"\r\n\r\nsecond\r\n' in body
    assert (
        b'Content-Disposition: form-data; name="attachment"; filename="report.txt"'
        b"\r\nContent-Type: text/plain\r\n\r\nfile contents\r\n"
    ) in body
    assert prepared_request.headers["Content-Length"] == str(len(body))


def test_multipart_bytes_file_guesses_type_and_keeps_existing_header(prepared_request):
    prepared_request.prepare_headers({"Content-Type": "application/overridden"})

    prepared_request.prepare_body(None, {"attachment": ("photo.png", b"PNG bytes")})

    assert prepared_request.headers["Content-Type"] == "application/overridden"
    assert b'filename="photo.png"\r\nContent-Type: image/png\r\n\r\nPNG bytes' in prepared_request.body
    assert prepared_request.headers["Content-Length"] == str(len(prepared_request.body))


def test_sized_iterable_is_streamed_without_form_encoding(prepared_request):
    chunks = (b"abc", b"def")

    prepared_request.prepare_body(chunks, None)

    assert prepared_request.body is chunks
    assert prepared_request.headers["Content-Length"] == "2"
    assert "Transfer-Encoding" not in prepared_request.headers
    assert "Content-Type" not in prepared_request.headers


def test_zero_length_iterable_still_sets_content_length(prepared_request):
    chunks = ()

    prepared_request.prepare_body(chunks, None)

    assert prepared_request.body is chunks
    assert prepared_request.headers["Content-Length"] == "0"
    assert "Transfer-Encoding" not in prepared_request.headers


def test_unsized_iterator_uses_chunked_transfer_when_length_fails(
    prepared_request, monkeypatch
):
    def unavailable_length(data):
        raise TypeError("length unavailable")

    monkeypatch.setattr("requests.models.super_len", unavailable_length)
    chunks = (chunk for chunk in [b"abc", b"def"])

    prepared_request.prepare_body(chunks, None)

    assert prepared_request.body is chunks
    assert prepared_request.headers["Transfer-Encoding"] == "chunked"
    assert "Content-Length" not in prepared_request.headers
    assert "Content-Type" not in prepared_request.headers


def test_iterable_with_len_attribute_sets_content_length(prepared_request):
    class SizedChunks:
        len = 7

        def __iter__(self):
            return iter([b"payload"])

    chunks = SizedChunks()
    prepared_request.prepare_body(chunks, None)

    assert prepared_request.body is chunks
    assert prepared_request.headers["Content-Length"] == "7"
    assert "Transfer-Encoding" not in prepared_request.headers


def test_stream_and_files_cannot_be_combined(prepared_request):
    chunks = (chunk for chunk in [b"payload"])

    with pytest.raises(NotImplementedError, match="mutually exclusive"):
        prepared_request.prepare_body(chunks, {"attachment": ("file.txt", b"file")})


def test_noniterable_file_like_body_is_rewound_and_measured(prepared_request):
    class FileLike:
        def __init__(self, content):
            self.stream = BytesIO(content)

        def read(self, size=-1):
            return self.stream.read(size)

        def seek(self, offset, whence=0):
            return self.stream.seek(offset, whence)

        def tell(self):
            return self.stream.tell()

    data = FileLike(b"abcdef")
    data.seek(3)

    prepared_request.prepare_body(data, None)

    assert prepared_request.body is data
    assert prepared_request.headers["Content-Length"] == "6"
    assert data.tell() == 0
    assert "Content-Type" not in prepared_request.headers
