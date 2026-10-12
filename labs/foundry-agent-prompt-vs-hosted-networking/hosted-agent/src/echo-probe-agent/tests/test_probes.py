"""
Unit tests for echo-probe-agent probe functions.

Run from src/echo-probe-agent/:
    python -m pytest tests/ -v
  or:
    python -m unittest discover tests/

All tests are self-contained and require only the stdlib plus `requests`.
No credentials, no network access, no Foundry packages needed.
"""
"""
## Test strategy

``probe_echo`` and ``probe_ctrl`` are pure Python functions that call
``requests.get``.  The MAF, Azure identity, and dotenv packages are
infrastructure concerns that the probe functions do not touch directly;
importing ``main`` would fail if those packages are absent.  The stub
strategy below isolates the probe logic from its heavyweight runtime deps.

### sys.modules stubbing (why setdefault, not patch.dict)

``sys.modules.setdefault(name, stub)`` inserts a MagicMock *only when the
real package is absent* — if the .venv has the real package, the real one
is used (good for integration runs).  This differs from ``unittest.mock.patch.dict``
which would forcibly replace even an installed package for the duration of
the with-block and then restore it, breaking cross-test module identity.

Why module identity matters: ``@patch("main.requests.get")`` resolves the
``requests`` name *as it lives in the ``main`` module's namespace at import
time*.  If ``main`` were re-imported after the patch-dict block restored the
real ``requests``, the patch target would be stale.  Using ``setdefault`` keeps
``main`` (and its ``requests`` reference) alive in ``sys.modules`` for the whole
test session, so ``@patch("main.requests.get")`` always resolves correctly.

Docs: https://docs.python.org/3/library/unittest.mock.html#patch

### @patch("main.requests.get") — target string convention

``patch("main.requests.get")`` patches the ``get`` attribute on the ``requests``
object that was bound into the ``main`` module's namespace at import time.
It does NOT patch ``requests.get`` globally; other modules that import
``requests`` independently are unaffected.  This is the standard "patch where
it is used, not where it is defined" rule.

### Why the HTTPError propagation tests matter

A naive implementation might catch exceptions in the probe function and return
``{"error": "..."}`` — a success-shaped dict — to avoid crashing the agent.
That would be wrong: the agent's system prompt instructs the LLM to *report
exception messages verbatim*, which only works if the exception propagates to
the MAF tool-call layer (MAF serialises uncaught exceptions into the tool
result).  Tests in ``TestHTTPErrorPropagation`` explicitly assert that no such
silent wrapping occurs.
"""
import socket
import sys
import unittest
from unittest.mock import MagicMock, patch

import requests

# ---------------------------------------------------------------------------
# Permanently stub non-standard packages so that ``import main`` succeeds
# without the Foundry / Azure / dotenv packages installed.
#
# ``sys.modules.setdefault`` only inserts when the key is absent; if the real
# package is installed (e.g. in the .venv), the real one wins — no forced
# replacement.  All six stubs are MagicMocks so any attribute access
# (``agent_framework.Agent``, ``azure.identity.DefaultAzureCredential``, etc.)
# returns another MagicMock without raising AttributeError.
#
# Both the flat name (``"azure"``) and the dotted sub-module
# (``"azure.identity"``) must be stubbed; Python resolves ``from azure.identity
# import DefaultAzureCredential`` by looking up both keys in sys.modules.
# ---------------------------------------------------------------------------
for _name, _stub in {
    "agent_framework": MagicMock(name="agent_framework"),
    "agent_framework.foundry": MagicMock(name="agent_framework.foundry"),
    "agent_framework_foundry_hosting": MagicMock(name="agent_framework_foundry_hosting"),
    "azure": MagicMock(name="azure"),
    "azure.identity": MagicMock(name="azure.identity"),
    "dotenv": MagicMock(name="dotenv"),
}.items():
    sys.modules.setdefault(_name, _stub)

# Import main after stubs are in place.  The alias ``_main`` keeps IDE
# "unused import" warnings away while making clear this is a test-only
# import. The ordering is intentional because these stubs must exist first.
import main as _main

probe_echo = _main.probe_echo
probe_ctrl = _main.probe_ctrl
probe_dependency_dns = _main.probe_dependency_dns
probe_dependency_tls = _main.probe_dependency_tls
probe_dependency_https = _main.probe_dependency_https


# ===========================================================================
# probe_echo
# ===========================================================================

class TestProbeEcho(unittest.TestCase):
    """probe_echo: exact URL, explicit (5,10) timeout, raise_for_status, JSON return."""

    @patch("main.requests.get")
    def test_calls_exact_echo_url_with_timeout(self, mock_get):
        """probe_echo calls http://echo.tools.lab/api/echo with timeout=(5, 10)."""
        mock_get.return_value.json.return_value = {"label": "echo"}
        probe_echo()
        mock_get.assert_called_once_with(
            "http://echo.tools.lab/api/echo",
            timeout=(5, 10),
        )

    @patch("main.requests.get")
    def test_calls_raise_for_status(self, mock_get):
        """probe_echo calls raise_for_status() on the response object."""
        mock_get.return_value.json.return_value = {}
        probe_echo()
        mock_get.return_value.raise_for_status.assert_called_once()

    @patch("main.requests.get")
    def test_returns_target_json(self, mock_get):
        """probe_echo returns exactly the dict produced by resp.json()."""
        payload = {
            "echo": "test", "label": "echo", "server_ip": "10.1.100.4",
            "src_ip": "192.168.1.10", "request_url": "http://echo.tools.lab/api/echo",
        }
        mock_get.return_value.json.return_value = payload
        self.assertEqual(probe_echo(), payload)


# ===========================================================================
# probe_ctrl
# ===========================================================================

class TestProbeCtrl(unittest.TestCase):
    """probe_ctrl: exact URL, explicit (5,10) timeout, raise_for_status, JSON return."""

    @patch("main.requests.get")
    def test_calls_exact_ctrl_url_with_timeout(self, mock_get):
        """probe_ctrl calls http://ctrl.tools.lab/api/echo with timeout=(5, 10)."""
        mock_get.return_value.json.return_value = {"label": "ctrl"}
        probe_ctrl()
        mock_get.assert_called_once_with(
            "http://ctrl.tools.lab/api/echo",
            timeout=(5, 10),
        )

    @patch("main.requests.get")
    def test_calls_raise_for_status(self, mock_get):
        """probe_ctrl calls raise_for_status() on the response object."""
        mock_get.return_value.json.return_value = {}
        probe_ctrl()
        mock_get.return_value.raise_for_status.assert_called_once()

    @patch("main.requests.get")
    def test_returns_target_json(self, mock_get):
        """probe_ctrl returns exactly the dict produced by resp.json()."""
        payload = {
            "echo": "test", "label": "ctrl", "server_ip": "10.1.200.4",
            "src_ip": "192.168.1.10", "request_url": "http://ctrl.tools.lab/api/echo",
        }
        mock_get.return_value.json.return_value = payload
        self.assertEqual(probe_ctrl(), payload)


# ===========================================================================
# HTTPError propagation
# ===========================================================================

class TestHTTPErrorPropagation(unittest.TestCase):
    """HTTPError from raise_for_status must propagate -- not swallowed into {error: ...}."""

    @patch("main.requests.get")
    def test_probe_echo_propagates_http_error(self, mock_get):
        """HTTPError from raise_for_status propagates out of probe_echo unchanged."""
        mock_get.return_value.raise_for_status.side_effect = requests.HTTPError("503 Server Error")
        with self.assertRaises(requests.HTTPError):
            probe_echo()

    @patch("main.requests.get")
    def test_probe_ctrl_propagates_http_error(self, mock_get):
        """HTTPError from raise_for_status propagates out of probe_ctrl unchanged."""
        mock_get.return_value.raise_for_status.side_effect = requests.HTTPError("503 Server Error")
        with self.assertRaises(requests.HTTPError):
            probe_ctrl()

    @patch("main.requests.get")
    def test_probe_echo_error_not_swallowed_to_dict(self, mock_get):
        """probe_echo must not wrap HTTPError in a success-shaped {"error": ...} dict."""
        mock_get.return_value.raise_for_status.side_effect = requests.HTTPError("503 Server Error")
        try:
            result = probe_echo()
        except requests.HTTPError:
            return  # correct: exception propagated
        self.fail(
            "probe_echo swallowed HTTPError and returned "
            + repr(result)
            + " instead of propagating"
        )

    @patch("main.requests.get")
    def test_probe_ctrl_error_not_swallowed_to_dict(self, mock_get):
        """probe_ctrl must not wrap HTTPError in a success-shaped {"error": ...} dict."""
        mock_get.return_value.raise_for_status.side_effect = requests.HTTPError("503 Server Error")
        try:
            result = probe_ctrl()
        except requests.HTTPError:
            return
        self.fail(
            "probe_ctrl swallowed HTTPError and returned "
            + repr(result)
            + " instead of propagating"
        )


# ===========================================================================
# Function application-dependency probes
# ===========================================================================

class TestDependencyProbes(unittest.TestCase):
    """Dependency probes preserve DNS, TLS, and HTTPS as separate evidence stages."""

    @patch.dict(
        "os.environ",
        {"FUNCTION_DEPENDENCY_URL": "https://function.example/api/dependency-probe"},
        clear=False,
    )
    @patch("main.socket.getaddrinfo")
    def test_dns_returns_unique_sorted_addresses(self, mock_getaddrinfo):
        """DNS uses the OS resolver and de-duplicates repeated address records."""
        mock_getaddrinfo.return_value = [
            (2, 1, 6, "", ("10.0.0.5", 443)),
            (2, 1, 6, "", ("10.0.0.4", 443)),
            (2, 1, 6, "", ("10.0.0.5", 443)),
        ]

        result = probe_dependency_dns()

        mock_getaddrinfo.assert_called_once_with(
            "function.example", 443, type=socket.SOCK_STREAM
        )
        self.assertEqual(result["addresses"], ["10.0.0.4", "10.0.0.5"])
        self.assertEqual(result["stage"], "dns")

    @patch.dict(
        "os.environ",
        {"FUNCTION_DEPENDENCY_URL": "https://function.example/api/dependency-probe"},
        clear=False,
    )
    @patch("main.ssl.create_default_context")
    @patch("main.socket.create_connection")
    def test_tls_reports_selected_peer_and_protocol(
        self, mock_create_connection, mock_create_default_context
    ):
        """TLS probe reports the address actually selected by create_connection."""
        tcp_context = MagicMock()
        tcp_socket = MagicMock()
        tcp_context.__enter__.return_value = tcp_socket
        mock_create_connection.return_value = tcp_context

        tls_context = MagicMock()
        tls_socket = MagicMock()
        tls_socket.getpeername.return_value = ("10.0.0.6", 443)
        tls_socket.version.return_value = "TLSv1.3"
        tls_socket.cipher.return_value = ("TLS_AES_256_GCM_SHA384", "TLSv1.3", 256)
        tls_context.__enter__.return_value = tls_socket
        mock_create_default_context.return_value.wrap_socket.return_value = tls_context

        result = probe_dependency_tls()

        mock_create_connection.assert_called_once_with(
            ("function.example", 443), timeout=5
        )
        mock_create_default_context.return_value.wrap_socket.assert_called_once_with(
            tcp_socket, server_hostname="function.example"
        )
        self.assertEqual(result["peer_ip"], "10.0.0.6")
        self.assertEqual(result["tls_version"], "TLSv1.3")

    @patch.dict(
        "os.environ",
        {"FUNCTION_DEPENDENCY_URL": "https://function.example/api/dependency-probe"},
        clear=False,
    )
    @patch("main.requests.get")
    def test_https_returns_status_and_target_json(self, mock_get):
        """HTTPS direct dependency call retains target-observed response metadata."""
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {
            "label": "function-dependency",
            "forwarded_for": ["192.168.0.7"],
        }

        result = probe_dependency_https()

        mock_get.assert_called_once_with(
            "https://function.example/api/dependency-probe",
            timeout=(5, 10),
        )
        mock_get.return_value.raise_for_status.assert_called_once()
        self.assertEqual(result["status_code"], 200)
        self.assertEqual(result["target"]["forwarded_for"], ["192.168.0.7"])

    @patch.dict("os.environ", {}, clear=True)
    def test_missing_dependency_url_is_explicit_error(self):
        """Missing deployment configuration fails before any network operation."""
        with self.assertRaisesRegex(RuntimeError, "FUNCTION_DEPENDENCY_URL"):
            probe_dependency_dns()

    @patch.dict(
        "os.environ",
        {"FUNCTION_DEPENDENCY_URL": "http://function.example/api/dependency-probe"},
        clear=False,
    )
    def test_non_https_dependency_url_is_rejected(self):
        """HTTP would change the tested path and is therefore rejected."""
        with self.assertRaisesRegex(RuntimeError, "absolute HTTPS URL"):
            probe_dependency_https()


if __name__ == "__main__":
    unittest.main()
