import contextlib

from io import StringIO

from unittest import mock
from unittest import IsolatedAsyncioTestCase
from tempfile import NamedTemporaryFile

from .. import logging as test_module


class TestLoggingConfigurator(IsolatedAsyncioTestCase):
    agent_label_arg_value = "Aries Cloud Agent"
    transport_arg_value = "transport"
    host_arg_value = "host"
    port_arg_value = "port"

    @mock.patch.object(test_module, "load_resource", autospec=True)
    @mock.patch.object(test_module, "fileConfig", autospec=True)
    def test_configure_default(self, mock_file_config, mock_load_resource):
        test_module.LoggingConfigurator.configure()

        mock_load_resource.assert_called_once_with(
            test_module.DEFAULT_LOGGING_CONFIG_PATH, "utf-8"
        )
        mock_file_config.assert_called_once_with(
            mock_load_resource.return_value,
            disable_existing_loggers=False,
            new_file_path=None,
        )

    def test_configure_with_per_tenant_config_file(self):
        with mock.patch.object(
            test_module,
            "logging",
            mock.MagicMock(
                basicConfig=mock.MagicMock(),
                FileHandler=mock.MagicMock(),
                root=mock.MagicMock(
                    warning=mock.MagicMock(),
                    handlers=[],
                ),
            ),
        ):
            test_module.LoggingConfigurator.configure(
                log_file="test.log",
                multitenant=True,
            )

    def test_configure_with_per_tenant_yml_file(self):
        with mock.patch.object(
            test_module,
            "logging",
            mock.MagicMock(
                basicConfig=mock.MagicMock(),
                FileHandler=mock.MagicMock(),
                root=mock.MagicMock(
                    warning=mock.MagicMock(),
                    handlers=[],
                ),
            ),
        ):
            test_module.LoggingConfigurator.configure(
                logging_config_path="aries_cloudagent/config/default_per_tenant_logging_config.yml",
                log_file="test.log",
                multitenant=True,
            )

    def test_configure_with_default_config(self):
        with mock.patch.object(
            test_module,
            "logging",
            mock.MagicMock(
                basicConfig=mock.MagicMock(),
                FileHandler=mock.MagicMock(),
                root=mock.MagicMock(
                    warning=mock.MagicMock(),
                    handlers=[],
                ),
            ),
        ):
            test_module.LoggingConfigurator.configure(
                log_file="test.log",
                multitenant=True,
            )

    def test_configure_default_no_resource(self):
        with mock.patch.object(
            test_module, "load_resource", mock.MagicMock()
        ) as mock_load:
            mock_load.return_value = None
            test_module.LoggingConfigurator.configure()

    def test_configure_default_file(self):
        log_file = NamedTemporaryFile()
        with mock.patch.object(
            test_module, "load_resource", mock.MagicMock()
        ) as mock_load:
            mock_load.return_value = None
            test_module.LoggingConfigurator.configure(
                log_level="ERROR", log_file=log_file.name
            )

    @mock.patch.object(test_module, "load_resource", autospec=True)
    @mock.patch.object(test_module, "fileConfig", autospec=True)
    def test_configure_path(self, mock_file_config, mock_load_resource):
        path = "a path"
        test_module.LoggingConfigurator.configure(path)

        mock_load_resource.assert_called_once_with(path, "utf-8")
        mock_file_config.assert_called_once_with(
            mock_load_resource.return_value,
            disable_existing_loggers=False,
            new_file_path=None,
        )

    def test_banner_did(self):
        stdout = StringIO()
        mock_http = mock.MagicMock(scheme="http", host="1.2.3.4", port=8081)
        mock_https = mock.MagicMock(schemes=["https", "archie"])
        mock_admin_server = mock.MagicMock(host="1.2.3.4", port=8091)
        with contextlib.redirect_stdout(stdout):
            test_label = "Aries Cloud Agent"
            test_did = "55GkHamhTU1ZbTbV2ab9DE"
            test_module.LoggingConfigurator.print_banner(
                test_label,
                {"in": mock_http},
                {"out": mock_https},
                test_did,
                mock_admin_server,
            )
            test_module.LoggingConfigurator.print_banner(
                test_label, {"in": mock_http}, {"out": mock_https}, test_did
            )
        output = stdout.getvalue()
        assert test_did in output

    def test_load_resource(self):
        with mock.patch("builtins.open", mock.MagicMock()) as mock_open:
            test_module.load_resource("abc", encoding="utf-8")
            mock_open.side_effect = IOError("insufficient privilege")
            test_module.load_resource("abc", encoding="utf-8")

        with mock.patch.object(
            test_module.pkg_resources, "resource_stream", mock.MagicMock()
        ) as mock_res_stream, mock.patch.object(
            test_module.io, "TextIOWrapper", mock.MagicMock()
        ) as mock_text_io_wrapper:
            test_module.load_resource("abc:def", encoding="utf-8")

        with mock.patch.object(
            test_module.pkg_resources, "resource_stream", mock.MagicMock()
        ) as mock_res_stream:
            test_module.load_resource("abc:def", encoding=None)
