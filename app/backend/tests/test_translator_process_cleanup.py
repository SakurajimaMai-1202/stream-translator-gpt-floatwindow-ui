from unittest.mock import Mock, patch

from backend.core.translator import _close_process_pipes, _redact_command_args, _terminate_process_tree


def test_windows_termination_kills_entire_process_tree():
    process = Mock()
    process.pid = 1234
    process.poll.return_value = None
    process.wait.return_value = 0

    completed = Mock(returncode=0, stdout="", stderr="")
    with patch("backend.core.translator.os.name", "nt"), patch(
        "backend.core.translator.subprocess.run", return_value=completed
    ) as run:
        _terminate_process_tree(process)

    run.assert_called_once()
    assert run.call_args.args[0] == ["taskkill", "/PID", "1234", "/T", "/F"]
    process.wait.assert_called_once()


def test_process_pipes_are_closed():
    process = Mock()

    _close_process_pipes(process)

    process.stdin.close.assert_called_once()
    process.stdout.close.assert_called_once()
    process.stderr.close.assert_called_once()


def test_sensitive_command_arguments_are_redacted():
    command = ["python", "-m", "tool", "--openai_api_key", "secret", "--model", "qwen"]

    redacted = _redact_command_args(command)

    assert redacted[4] == "***"
    assert command[4] == "secret"
