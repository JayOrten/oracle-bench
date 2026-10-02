"""Tests for caplog ``messages`` and the handlers' ``reset`` behaviour in
``_pytest.logging``."""
import logging
import sys

import pytest
from _pytest.logging import _LiveLoggingNullHandler
from _pytest.logging import _LiveLoggingStreamHandler
from _pytest.logging import LogCaptureHandler
from _pytest.pytester import Pytester


logger = logging.getLogger(__name__)
sublogger = logging.getLogger(__name__ + ".baz")


def make_record(msg, args=(), level=logging.INFO, name="oracle", exc_info=None):
    return logging.LogRecord(name, level, __file__, 1, msg, args, exc_info)


# ---------------------------------------------------------------------------
# LogCaptureHandler.reset
# ---------------------------------------------------------------------------


class TestLogCaptureHandlerReset:
    def test_emit_stores_records_and_text(self) -> None:
        handler = LogCaptureHandler()
        record = make_record("hello %s", ("world",))
        handler.emit(record)
        assert handler.records == [record]
        assert handler.stream.getvalue() == "hello world\n"

    def test_reset_discards_records_and_text(self) -> None:
        handler = LogCaptureHandler()
        handler.emit(make_record("one"))
        handler.emit(make_record("two"))

        handler.reset()

        assert handler.records == []
        assert handler.stream.getvalue() == ""

    def test_reset_on_fresh_handler(self) -> None:
        handler = LogCaptureHandler()
        handler.reset()
        assert handler.records == []
        assert handler.stream.getvalue() == ""

    def test_handler_keeps_capturing_after_reset(self) -> None:
        handler = LogCaptureHandler()
        handler.emit(make_record("before"))
        handler.reset()
        after = make_record("after")
        handler.emit(after)

        assert handler.records == [after]
        assert handler.stream.getvalue() == "after\n"

    def test_reset_does_not_mutate_previous_records_list(self) -> None:
        # pytest stores the records list of every phase (setup/call/teardown)
        # and resets the handler between phases, so previously handed out
        # lists must stay intact.
        handler = LogCaptureHandler()
        first = make_record("first")
        handler.emit(first)
        old_records = handler.records

        handler.reset()
        handler.emit(make_record("second"))

        assert old_records == [first]
        assert handler.records is not old_records

    def test_reset_does_not_mutate_previous_stream(self) -> None:
        handler = LogCaptureHandler()
        handler.emit(make_record("first"))
        old_stream = handler.stream

        handler.reset()
        handler.emit(make_record("second"))

        assert old_stream.getvalue() == "first\n"
        assert handler.stream is not old_stream
        assert handler.stream.getvalue() == "second\n"

    def test_reset_keeps_formatter_and_level(self) -> None:
        handler = LogCaptureHandler()
        formatter = logging.Formatter("%(levelname)s:%(message)s")
        handler.setFormatter(formatter)
        handler.setLevel(logging.WARNING)

        handler.reset()

        assert handler.formatter is formatter
        assert handler.level == logging.WARNING
        handler.emit(make_record("kept", level=logging.ERROR))
        assert handler.stream.getvalue() == "ERROR:kept\n"
        assert [r.getMessage() for r in handler.records] == ["kept"]


# ---------------------------------------------------------------------------
# _LiveLoggingStreamHandler.reset / _LiveLoggingNullHandler.reset
# ---------------------------------------------------------------------------


class FakeTerminalReporter:
    def __init__(self) -> None:
        self.chunks = []
        self.sections = []

    def write(self, s: str, **kwargs) -> None:
        self.chunks.append(s)

    def flush(self) -> None:
        pass

    def section(self, title: str, sep: str = "=", **kwargs) -> None:
        self.sections.append(title)
        self.chunks.append("<section %s>" % title)


class TestLiveLoggingReset:
    def make_handler(self):
        reporter = FakeTerminalReporter()
        handler = _LiveLoggingStreamHandler(reporter, None)  # type: ignore[arg-type]
        handler.setFormatter(logging.Formatter("%(message)s"))
        return reporter, handler

    def test_first_record_after_init_writes_leading_newline(self) -> None:
        reporter, handler = self.make_handler()
        handler.emit(make_record("msg"))
        assert reporter.chunks[0] == "\n"
        assert "".join(reporter.chunks) == "\nmsg\n"

    def test_leading_newline_written_only_once_without_reset(self) -> None:
        reporter, handler = self.make_handler()
        handler.emit(make_record("a"))
        handler.emit(make_record("b"))
        assert "".join(reporter.chunks) == "\na\nb\n"

    def test_reset_causes_leading_newline_again(self) -> None:
        reporter, handler = self.make_handler()
        handler.emit(make_record("a"))
        handler.reset()
        handler.emit(make_record("b"))
        assert "".join(reporter.chunks) == "\na\n\nb\n"

    def test_reset_returns_none_and_does_not_write(self) -> None:
        reporter, handler = self.make_handler()
        assert handler.reset() is None
        assert reporter.chunks == []

    def test_reset_does_not_reset_section_state(self) -> None:
        reporter, handler = self.make_handler()
        handler.set_when("call")
        handler.emit(make_record("a"))
        handler.reset()
        handler.emit(make_record("b"))
        # Section header is shown only once per phase, reset() is about the
        # leading newline only.
        assert reporter.sections == ["live log call"]
        assert "".join(reporter.chunks) == "\n<section live log call>a\n\nb\n"

    def test_null_handler_reset_is_noop(self) -> None:
        handler = _LiveLoggingNullHandler()
        assert handler.reset() is None
        handler.set_when("call")
        handler.handle(make_record("ignored"))


# ---------------------------------------------------------------------------
# caplog.messages
# ---------------------------------------------------------------------------


class TestCaplogMessages:
    def test_empty_when_nothing_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        assert caplog.messages == []

    def test_messages_are_interpolated(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.INFO)
        logger.info("boo %s", "arg")
        logger.info("bar %s\nbaz %s", "arg1", "arg2")
        logger.warning("%d%%", 42)

        assert caplog.messages == ["boo arg", "bar arg1\nbaz arg2", "42%"]
        # The raw records still hold the format string.
        assert caplog.records[0].msg == "boo %s"
        assert caplog.records[0].args == ("arg",)

    def test_mapping_args(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.INFO)
        logger.info("%(a)s-%(b)d", {"a": "x", "b": 3})
        assert caplog.messages == ["x-3"]

    def test_non_string_message(self, caplog: pytest.LogCaptureFixture) -> None:
        class Obj:
            def __str__(self) -> str:
                return "custom object"

        caplog.set_level(logging.INFO)
        logger.info(Obj())
        logger.info(12)
        assert caplog.messages == ["custom object", "12"]

    def test_unicode(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.INFO)
        logger.info("bū %s", "ñ")
        assert caplog.messages == ["bū ñ"]

    def test_no_level_or_logger_name_in_messages(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.INFO)
        logger.error("plain")
        assert caplog.messages == ["plain"]
        assert "ERROR" in caplog.text
        assert "plain" in caplog.text

    def test_order_and_multiple_loggers(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.INFO)
        logger.info("first")
        sublogger.warning("second")
        logging.getLogger().error("third")
        assert caplog.messages == ["first", "second", "third"]

    def test_matches_record_tuples_and_records(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.DEBUG)
        logger.debug("a %d", 1)
        sublogger.critical("b %s", "two")
        assert caplog.messages == [m for _, _, m in caplog.record_tuples]
        assert caplog.messages == [r.getMessage() for r in caplog.records]

    def test_respects_level(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.WARNING)
        logger.info("hidden")
        logger.warning("shown")
        assert caplog.messages == ["shown"]

    def test_respects_at_level(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.WARNING)
        with caplog.at_level(logging.DEBUG, logger=logger.name):
            logger.debug("inside")
        logger.debug("outside")
        assert caplog.messages == ["inside"]

    def test_exception_traceback_not_included(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.INFO)
        try:
            raise ValueError("boom")
        except ValueError:
            logger.exception("oops %s", "here")

        assert caplog.messages == ["oops here"]
        assert "Traceback" not in caplog.messages[0]
        assert "ValueError: boom" in caplog.text

    def test_exc_info_not_included(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.INFO)
        try:
            raise RuntimeError("bad")
        except RuntimeError:
            logger.error("failure", exc_info=True)
        assert caplog.messages == ["failure"]
        assert "RuntimeError" in caplog.text

    def test_stack_info_not_included(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.INFO)
        logger.info("with stack", stack_info=True)
        assert caplog.messages == ["with stack"]
        assert "Stack (most recent call last)" in caplog.text

    def test_returns_new_list(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.INFO)
        logger.info("x")
        messages = caplog.messages
        messages.append("injected")
        messages.clear()
        assert caplog.messages == ["x"]

    def test_reflects_later_records(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.INFO)
        logger.info("a")
        before = caplog.messages
        logger.info("b")
        assert before == ["a"]
        assert caplog.messages == ["a", "b"]

    def test_interpolation_is_lazy_until_accessed(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.INFO)
        values = ["v1"]
        logger.info("list: %s", values)
        values.append("v2")
        # getMessage() is re-evaluated each time ``messages`` is accessed.
        assert caplog.messages == ["list: ['v1', 'v2']"]

    def test_empty_after_clear(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.INFO)
        logger.info("before")
        assert caplog.messages == ["before"]
        caplog.clear()
        assert caplog.messages == []
        logger.info("after")
        assert caplog.messages == ["after"]


# ---------------------------------------------------------------------------
# caplog.clear (LogCaptureFixture -> handler reset)
# ---------------------------------------------------------------------------


class TestCaplogClear:
    def test_clear_resets_records_and_text(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.INFO)
        logger.info("bū")
        assert len(caplog.records)
        assert caplog.text
        caplog.clear()
        assert not len(caplog.records)
        assert not caplog.text
        assert caplog.record_tuples == []

    def test_clear_is_idempotent(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.clear()
        caplog.clear()
        assert caplog.records == []
        assert caplog.text == ""

    def test_clear_keeps_levels(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.WARNING)
        caplog.clear()
        logger.info("hidden")
        logger.warning("shown")
        assert caplog.messages == ["shown"]

    def test_get_records_call_consistent_after_clear(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        def verify_consistency() -> None:
            assert caplog.get_records("call") == caplog.records

        caplog.set_level(logging.INFO)
        verify_consistency()
        logger.info("a_call_log_message")
        verify_consistency()
        caplog.clear()
        verify_consistency()
        assert caplog.get_records("call") == []
        logger.info("another")
        verify_consistency()
        assert [r.getMessage() for r in caplog.get_records("call")] == ["another"]


def test_clear_in_call_keeps_setup_records(pytester: Pytester) -> None:
    pytester.makepyfile(
        """
        import logging
        import pytest

        logger = logging.getLogger(__name__)

        @pytest.fixture
        def logging_during_setup(caplog):
            caplog.set_level(logging.INFO)
            logger.info("a_setup_log")
            yield

        def test_it(logging_during_setup, caplog):
            logger.info("a_call_log")
            assert [r.getMessage() for r in caplog.get_records("setup")] == ["a_setup_log"]
            assert caplog.messages == ["a_call_log"]

            caplog.clear()

            assert [r.getMessage() for r in caplog.get_records("setup")] == ["a_setup_log"]
            assert caplog.get_records("call") == []
            assert caplog.messages == []
        """
    )
    result = pytester.runpytest()
    result.assert_outcomes(passed=1)


def test_messages_per_phase(pytester: Pytester) -> None:
    pytester.makepyfile(
        """
        import logging
        import pytest

        logger = logging.getLogger(__name__)

        @pytest.fixture
        def fix(caplog):
            caplog.set_level(logging.INFO)
            logger.info("setup %d", 1)
            yield
            assert caplog.messages == []
            logger.info("teardown %d", 3)
            assert caplog.messages == ["teardown 3"]
            assert [r.getMessage() for r in caplog.get_records("call")] == ["call 2"]
            assert [r.getMessage() for r in caplog.get_records("setup")] == ["setup 1"]

        def test_it(fix, caplog):
            # The handler is reset between phases.
            assert caplog.messages == []
            logger.info("call %d", 2)
            assert caplog.messages == ["call 2"]
        """
    )
    result = pytester.runpytest()
    result.assert_outcomes(passed=1)


def test_report_sections_contain_only_their_phase(pytester: Pytester) -> None:
    # The report handler is reset at the start of each phase so the captured
    # log sections contain only the records of that phase.
    pytester.makepyfile(
        """
        import logging
        import pytest

        logger = logging.getLogger(__name__)

        @pytest.fixture
        def fix():
            logger.warning("SETUP-MSG")
            yield
            logger.warning("TEARDOWN-MSG")

        def test_it(fix):
            logger.warning("CALL-MSG")
            assert False
        """
    )
    result = pytester.runpytest("-p", "no:cacheprovider")
    result.assert_outcomes(failed=1)
    out = result.stdout.str()
    call_section = out.split("Captured log call")[1]
    setup_section = out.split("Captured log setup")[1].split("Captured log call")[0]
    assert "SETUP-MSG" in setup_section
    assert "CALL-MSG" not in setup_section
    assert "CALL-MSG" in call_section
    assert "SETUP-MSG" not in call_section


def test_clear_does_not_affect_report_section(pytester: Pytester) -> None:
    pytester.makepyfile(
        """
        import logging

        logger = logging.getLogger(__name__)

        def test_it(caplog):
            logger.warning("BEFORE-CLEAR")
            caplog.clear()
            logger.warning("AFTER-CLEAR")
            assert caplog.messages == ["AFTER-CLEAR"]
            assert False
        """
    )
    result = pytester.runpytest()
    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(
        ["*Captured log call*", "*BEFORE-CLEAR*", "*AFTER-CLEAR*"]
    )


def test_live_logging_reset_between_tests(pytester: Pytester) -> None:
    pytester.makepyfile(
        """
        import logging

        logger = logging.getLogger(__name__)

        def test_one():
            logger.warning("ONE-MSG")

        def test_two():
            logger.warning("TWO-MSG")
        """
    )
    result = pytester.runpytest("-o", "log_cli=true", "-p", "no:cacheprovider")
    result.assert_outcomes(passed=2)
    result.stdout.fnmatch_lines(
        [
            "*::test_one ",
            "*-- live log call --*",
            "*ONE-MSG*",
            "PASSED*",
            "*::test_two ",
            "*-- live log call --*",
            "*TWO-MSG*",
            "PASSED*",
        ]
    )


@pytest.mark.skipif(sys.version_info < (3, 8), reason="stacklevel needs 3.8")
def test_messages_with_stacklevel(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    logger.info("lvl %s", "x", stacklevel=1)
    assert caplog.messages == ["lvl x"]
