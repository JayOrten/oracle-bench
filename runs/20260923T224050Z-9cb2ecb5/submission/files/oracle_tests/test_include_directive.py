from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from docutils.parsers.rst.directives.misc import Include as BaseInclude

from sphinx.directives.other import Include


def make_include(argument, env):
    directive = Include.__new__(Include)
    directive.arguments = [argument]
    directive.state = SimpleNamespace(
        document=SimpleNamespace(settings=SimpleNamespace(env=env))
    )
    return directive


@pytest.mark.parametrize('argument', ['parts/intro.inc', '/shared/intro.inc', '../intro.inc'])
def test_include_resolves_and_records_file_before_running_docutils(
    monkeypatch, argument
):
    calls = []
    absolute_path = '/docs/parts/intro.inc'
    result = [object()]

    def relfn2path(value):
        calls.append(('resolve', value))
        return 'parts/intro.inc', absolute_path

    def note_included(value):
        calls.append(('included', value))

    def run_base(directive):
        calls.append(('docutils', directive.arguments[0]))
        return result

    env = SimpleNamespace(relfn2path=relfn2path, note_included=note_included)
    monkeypatch.setattr(BaseInclude, 'run', run_base)
    directive = make_include(argument, env)

    assert directive.run() is result
    assert directive.arguments == [absolute_path]
    assert calls == [
        ('resolve', argument),
        ('included', absolute_path),
        ('docutils', absolute_path),
    ]


@pytest.mark.parametrize('argument', ['<isonum.txt>', '<custom-name>', '<>'])
def test_standard_docutils_includes_bypass_sphinx_path_handling(monkeypatch, argument):
    env = SimpleNamespace(relfn2path=Mock(), note_included=Mock())
    result = [object()]
    base_run = Mock(return_value=result)
    monkeypatch.setattr(BaseInclude, 'run', base_run)
    directive = make_include(argument, env)

    assert directive.run() is result
    assert directive.arguments == [argument]
    base_run.assert_called_once_with()
    env.relfn2path.assert_not_called()
    env.note_included.assert_not_called()


@pytest.mark.parametrize('argument', ['<name', 'name>', ''])
def test_non_standard_include_names_are_resolved(monkeypatch, argument):
    env = SimpleNamespace(
        relfn2path=Mock(return_value=('relative', '/docs/relative')),
        note_included=Mock(),
    )
    monkeypatch.setattr(BaseInclude, 'run', Mock(return_value=[]))
    directive = make_include(argument, env)

    assert directive.run() == []
    env.relfn2path.assert_called_once_with(argument)
    env.note_included.assert_called_once_with('/docs/relative')


def test_path_resolution_error_does_not_record_or_run_include(monkeypatch):
    error = ValueError('unresolvable include')
    env = SimpleNamespace(
        relfn2path=Mock(side_effect=error), note_included=Mock()
    )
    base_run = Mock()
    monkeypatch.setattr(BaseInclude, 'run', base_run)
    directive = make_include('missing.inc', env)

    with pytest.raises(ValueError, match='unresolvable include'):
        directive.run()

    assert directive.arguments == ['missing.inc']
    env.note_included.assert_not_called()
    base_run.assert_not_called()


def test_docutils_error_propagates_after_recording_include(monkeypatch):
    env = SimpleNamespace(
        relfn2path=Mock(return_value=('file.inc', '/docs/file.inc')),
        note_included=Mock(),
    )
    error = RuntimeError('include could not be read')
    base_run = Mock(side_effect=error)
    monkeypatch.setattr(BaseInclude, 'run', base_run)
    directive = make_include('file.inc', env)

    with pytest.raises(RuntimeError, match='include could not be read'):
        directive.run()

    env.note_included.assert_called_once_with('/docs/file.inc')
    base_run.assert_called_once_with()
