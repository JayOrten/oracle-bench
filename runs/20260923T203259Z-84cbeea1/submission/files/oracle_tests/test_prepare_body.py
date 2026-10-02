# -*- coding: utf-8 -*-
"""Unit tests for requests.models.PreparedRequest.prepare_body."""

import tempfile

import pytest

from requests.models import PreparedRequest, Request


def make_prepared(headers=None):
    p = PreparedRequest()
    p.prepare_headers(headers)
    return p


def prepare(data, files=None, headers=None):
    p = make_prepared(headers)
    p.prepare_body(data, files)
    return p


def content_type_str(value):
    if isinstance(value, bytes):
        return value.decode('ascii')
    return value


def multipart_boundary(p):
    ct = content_type_str(p.headers['Content-Type'])
    prefix = 'multipart/form-data; boundary='
    assert ct.startswith(prefix)
    return ct[len(prefix):]


class SizedIterableWithBadLen(object):
    """Iterable whose length cannot be determined (super_len raises)."""

    def __init__(self, chunks):
        self.chunks = chunks

    def __iter__(self):
        return iter(self.chunks)

    def __len__(self):
        raise TypeError('no length')


class IterableWithLenAttr(object):
    """Iterable exposing its size via a ``len`` attribute."""

    def __init__(self, chunks):
        self.chunks = chunks
        self.len = sum(len(c) for c in chunks)

    def __iter__(self):
        return iter(self.chunks)


class SeekableReader(object):
    """File-like object that is not iterable but supports seek/tell."""

    def __init__(self, content):
        self.content = content
        self.pos = 0

    def read(self, n=-1):
        if n < 0:
            n = len(self.content) - self.pos
        chunk = self.content[self.pos:self.pos + n]
        self.pos += len(chunk)
        return chunk

    def seek(self, offset, whence=0):
        if whence == 0:
            self.pos = offset
        elif whence == 1:
            self.pos += offset
        elif whence == 2:
            self.pos = len(self.content) + offset

    def tell(self):
        return self.pos


# --- Empty / missing bodies -------------------------------------------------

class TestEmptyBody:

    def test_none_data_no_files(self):
        p = prepare(None)
        assert p.body is None
        assert p.headers['Content-Length'] == '0'
        assert 'Content-Type' not in p.headers
        assert 'Transfer-Encoding' not in p.headers

    def test_empty_dict_data(self):
        p = prepare({})
        assert p.body is None
        assert p.headers['Content-Length'] == '0'
        assert 'Content-Type' not in p.headers

    def test_empty_string_data(self):
        p = prepare('')
        assert p.body is None
        assert p.headers['Content-Length'] == '0'
        assert 'Content-Type' not in p.headers

    def test_empty_files_is_ignored(self):
        p = prepare({'a': 'b'}, files={})
        assert p.body == 'a=b'
        assert p.headers['Content-Type'] == 'application/x-www-form-urlencoded'

    def test_body_attribute_overwritten(self):
        p = make_prepared()
        p.body = 'stale'
        p.prepare_body(None, None)
        assert p.body is None


# --- Form encoded data ------------------------------------------------------

class TestFormEncoded:

    def test_dict_is_form_encoded(self):
        p = prepare({'key': 'value'})
        assert p.body == 'key=value'
        assert p.headers['Content-Type'] == 'application/x-www-form-urlencoded'
        assert p.headers['Content-Length'] == str(len('key=value'))
        assert 'Transfer-Encoding' not in p.headers

    def test_dict_with_multiple_keys(self):
        p = prepare({'a': '1', 'b': '2'})
        assert sorted(p.body.split('&')) == ['a=1', 'b=2']
        assert p.headers['Content-Length'] == str(len(p.body))

    def test_dict_with_list_values(self):
        p = prepare({'a': ['1', '2']})
        assert p.body == 'a=1&a=2'
        assert p.headers['Content-Length'] == '7'

    def test_dict_with_none_value_is_dropped(self):
        p = prepare({'a': '1', 'b': None})
        assert p.body == 'a=1'
        assert p.headers['Content-Length'] == '3'

    def test_dict_with_non_string_value(self):
        p = prepare({'n': 1})
        assert p.body == 'n=1'

    def test_dict_values_are_url_quoted(self):
        p = prepare({'q': 'a b&c'})
        assert p.body == 'q=a+b%26c'
        assert p.headers['Content-Length'] == str(len('q=a+b%26c'))

    def test_unicode_values_are_utf8_encoded(self):
        p = prepare({'k': u'é'})
        assert p.body == 'k=%C3%A9'

    def test_explicit_content_type_is_preserved(self):
        p = prepare({'a': 'b'}, headers={'Content-Type': 'text/plain'})
        assert p.body == 'a=b'
        assert p.headers['Content-Type'] == 'text/plain'
        assert p.headers['Content-Length'] == '3'

    def test_explicit_content_type_check_is_case_insensitive(self):
        p = prepare({'a': 'b'}, headers={'content-type': 'text/plain'})
        assert p.headers['Content-Type'] == 'text/plain'
        assert len([k for k in p.headers if k.lower() == 'content-type']) == 1


# --- Raw string / bytes data ------------------------------------------------

class TestRawData:

    def test_str_data_is_passed_through(self):
        p = prepare('x=1&y=2')
        assert p.body == 'x=1&y=2'
        assert p.headers['Content-Length'] == '7'

    def test_str_data_sets_no_content_type(self):
        p = prepare('{"json": true}')
        assert 'Content-Type' not in p.headers

    def test_str_data_keeps_explicit_content_type(self):
        p = prepare('{}', headers={'Content-Type': 'application/json'})
        assert p.body == '{}'
        assert p.headers['Content-Type'] == 'application/json'
        assert p.headers['Content-Length'] == '2'

    def test_bytes_data_is_passed_through(self):
        p = prepare(b'raw-bytes')
        assert p.body == b'raw-bytes'
        assert p.headers['Content-Length'] == '9'
        assert 'Transfer-Encoding' not in p.headers

    def test_bytes_data_is_not_streamed(self):
        # bytes are iterable but must not be treated as a stream.
        p = prepare(b'abc')
        assert 'Transfer-Encoding' not in p.headers
        assert p.headers['Content-Length'] == '3'


# --- File-like data (non-stream) -------------------------------------------

class TestFileLikeData:

    def test_readable_non_iterable_passed_through(self):
        reader = SeekableReader(b'hello world')
        p = prepare(reader)
        assert p.body is reader
        assert 'Content-Type' not in p.headers
        assert p.headers['Content-Length'] == '11'

    def test_content_length_rewinds_file_position(self):
        reader = SeekableReader(b'hello world')
        reader.seek(3)
        p = prepare(reader)
        assert p.headers['Content-Length'] == '11'
        assert reader.tell() == 0

    def test_readable_keeps_explicit_content_type(self):
        reader = SeekableReader(b'abc')
        p = prepare(reader, headers={'Content-Type': 'application/octet-stream'})
        assert p.headers['Content-Type'] == 'application/octet-stream'


# --- Streaming bodies -------------------------------------------------------

class TestStreamingBody:

    def test_real_file_is_streamed_with_length(self):
        with tempfile.TemporaryFile() as f:
            f.write(b'hello')
            f.seek(0)
            p = prepare(f)
            assert p.body is f
            assert p.headers['Content-Length'] == '5'
            assert 'Transfer-Encoding' not in p.headers
            assert 'Content-Type' not in p.headers

    def test_iterable_with_len_attr_sets_content_length(self):
        data = IterableWithLenAttr([b'ab', b'cde'])
        p = prepare(data)
        assert p.body is data
        assert p.headers['Content-Length'] == '5'
        assert 'Transfer-Encoding' not in p.headers

    def test_list_is_streamed_as_is(self):
        data = [b'chunk1', b'chunk2']
        p = prepare(data)
        assert p.body is data
        assert p.headers['Content-Length'] == '2'
        assert 'Content-Type' not in p.headers

    def test_unknown_length_uses_chunked_encoding(self):
        data = SizedIterableWithBadLen([b'a', b'b'])
        p = prepare(data)
        assert p.body is data
        assert p.headers['Transfer-Encoding'] == 'chunked'
        assert 'Content-Length' not in p.headers
        assert 'Content-Type' not in p.headers

    def test_generator_body_is_passed_through(self):
        gen = (c for c in [b'a', b'b'])
        p = prepare(gen)
        assert p.body is gen
        assert 'Content-Type' not in p.headers

    def test_stream_with_files_raises(self):
        with pytest.raises(NotImplementedError):
            prepare(iter([b'a']), files={'f': b'data'})

    def test_list_data_with_files_raises(self):
        with pytest.raises(NotImplementedError):
            prepare([('a', 'b')], files={'f': ('f.txt', b'data')})

    def test_stream_with_empty_files_is_allowed(self):
        data = SizedIterableWithBadLen([b'x'])
        p = prepare(data, files={})
        assert p.body is data
        assert p.headers['Transfer-Encoding'] == 'chunked'

    def test_stream_does_not_set_default_content_type(self):
        data = IterableWithLenAttr([b'abc'])
        p = prepare(data, headers={'Content-Type': 'application/octet-stream'})
        assert p.headers['Content-Type'] == 'application/octet-stream'


# --- Multipart file uploads -------------------------------------------------

class TestMultipart:

    def test_files_produce_multipart_body(self):
        p = prepare(None, files={'file': ('name.txt', b'contents')})
        boundary = multipart_boundary(p)
        assert isinstance(p.body, bytes)
        assert p.body.startswith(('--%s\r\n' % boundary).encode('ascii'))
        assert p.body.endswith(('--%s--\r\n' % boundary).encode('ascii'))
        assert b'name="file"; filename="name.txt"' in p.body
        assert b'\r\n\r\ncontents\r\n' in p.body

    def test_content_length_matches_body(self):
        p = prepare({'k': 'v'}, files={'file': ('name.txt', b'contents')})
        assert p.headers['Content-Length'] == str(len(p.body))
        assert 'Transfer-Encoding' not in p.headers

    def test_data_fields_included(self):
        p = prepare({'field': 'value'}, files={'file': ('a.txt', b'x')})
        assert b'Content-Disposition: form-data; name="field"\r\n\r\nvalue\r\n' in p.body
        assert b'filename="a.txt"' in p.body

    def test_data_field_list_values_repeated(self):
        p = prepare({'a': ['1', '2']}, files={'f': ('f.bin', b'z')})
        assert p.body.count(b'name="a"') == 2
        assert b'name="a"\r\n\r\n1\r\n' in p.body
        assert b'name="a"\r\n\r\n2\r\n' in p.body

    def test_explicit_file_content_type(self):
        p = prepare(None, files={'f': ('n.bin', b'\x00\x01', 'application/x-custom')})
        assert b'Content-Type: application/x-custom\r\n\r\n\x00\x01\r\n' in p.body

    def test_file_object_uses_its_name(self):
        f = SeekableReader(b'file-data')
        f.name = 'report.txt'
        p = prepare(None, files={'upload': f})
        assert b'name="upload"; filename="report.txt"' in p.body
        assert b'file-data' in p.body

    def test_file_object_with_bracketed_name_falls_back_to_key(self):
        f = SeekableReader(b'file-data')
        f.name = '<stdin>'
        p = prepare(None, files={'upload': f})
        assert b'name="upload"; filename="upload"' in p.body

    def test_raw_bytes_file_falls_back_to_key_name(self):
        p = prepare(None, files={'upload': b'payload'})
        assert b'name="upload"; filename="upload"' in p.body
        assert b'payload' in p.body

    def test_explicit_content_type_header_preserved(self):
        p = prepare(None, files={'f': ('n.txt', b'hi')},
                    headers={'content-type': 'x/y'})
        assert p.headers['Content-Type'] == 'x/y'
        assert p.headers['Content-Length'] == str(len(p.body))

    def test_multiple_files(self):
        p = prepare(None, files=[('a', ('a.txt', b'AAA')), ('b', ('b.txt', b'BBB'))])
        assert b'filename="a.txt"' in p.body
        assert b'filename="b.txt"' in p.body
        assert p.body.index(b'AAA') < p.body.index(b'BBB')


# --- Integration through Request.prepare ------------------------------------

class TestRequestPrepare:

    def test_default_request_has_empty_body(self):
        p = Request('GET', 'http://example.com/').prepare()
        assert p.body is None
        assert p.headers['Content-Length'] == '0'

    def test_post_with_dict_data(self):
        p = Request('POST', 'http://example.com/', data={'a': 'b'}).prepare()
        assert p.body == 'a=b'
        assert p.headers['Content-Type'] == 'application/x-www-form-urlencoded'
        assert p.headers['Content-Length'] == '3'

    def test_post_with_files(self):
        p = Request('POST', 'http://example.com/',
                    files={'f': ('f.txt', b'data')}).prepare()
        assert content_type_str(p.headers['Content-Type']).startswith('multipart/form-data')
        assert p.headers['Content-Length'] == str(len(p.body))
