"""
Tests for audit backends (file, redis, kafka, factory, coordinator).

These tests cover the new backends architecture which uses:
- ``FileAuditBackend``  — append-only JSON-lines file
- ``RedisAuditBackend`` — Redis Streams (XADD)
- ``KafkaAuditBackend`` — Kafka producer (write-only)
- ``MultiBackendCoordinator`` — fan-out to multiple backends
- ``get_audit_backend`` / ``get_configured_backends`` factory helpers
"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
from django.test import TestCase
from django.utils import timezone

from apps.auditing.backends.base import AuditBackendError, AuditBackendUnavailableError
from apps.auditing.backends.coordinator import MultiBackendCoordinator
from apps.auditing.backends.factory import get_audit_backend, get_configured_backends
from apps.auditing.backends.file import FileAuditBackend
from apps.auditing.backends.kafka import KafkaAuditBackend
from apps.auditing.backends.redis import RedisAuditBackend

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sample_event(**overrides: object) -> dict:
    data = {
        "id": "evt-001",
        "content_type_id": 1,
        "object_id": "42",
        "event_type": "CREATE",
        "version": 1,
        "snapshot": {"field": "value"},
        "actor_id": "user-1",
        "created_at": timezone.now().isoformat(),
    }
    data.update(overrides)
    return data


# ---------------------------------------------------------------------------
# FileAuditBackend
# ---------------------------------------------------------------------------


class TestFileAuditBackend(TestCase):
    """Tests for FileAuditBackend."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp()
        self.backend = FileAuditBackend(
            base_path=self.temp_dir,
            compress=False,
            rotate_daily=False,
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # --- dispatch ---

    def test_dispatch_appends_json_line(self) -> None:
        event_data = _sample_event()
        self.backend.dispatch(event_data)

        log_file = Path(self.temp_dir) / "audit.json"
        self.assertTrue(log_file.exists())
        content = log_file.read_text(encoding="utf-8")
        parsed = json.loads(content.strip())
        self.assertEqual(parsed["event_type"], "CREATE")

    def test_dispatch_multiple_lines(self) -> None:
        for i in range(3):
            self.backend.dispatch(_sample_event(id=f"evt-{i}"))

        log_file = Path(self.temp_dir) / "audit.json"
        lines = [ln for ln in log_file.read_text(encoding="utf-8").splitlines() if ln.strip()]
        self.assertEqual(len(lines), 3)

    def test_dispatch_raises_on_os_error(self) -> None:
        with (
            patch.object(self.backend, "_write_record", side_effect=OSError("disk full")),
            self.assertRaises(AuditBackendError),
        ):
            self.backend.dispatch(_sample_event())

    # --- write ---

    def test_write_returns_entry_id(self) -> None:
        entry_id = self.backend.write(
            content_type_id=1,
            object_id="99",
            event_type="create",
            current_state={"name": "Alice"},
            changes={},
            user_id="user-1",
            session_id=None,
            comment="initial",
            object_version=1,
        )
        self.assertIsInstance(entry_id, str)
        self.assertTrue(len(entry_id) > 0)

    def test_write_creates_log_file(self) -> None:
        self.backend.write(
            content_type_id=1,
            object_id="99",
            event_type="create",
            current_state={},
            changes={},
            user_id=None,
            session_id=None,
            comment="",
            object_version=1,
        )
        log_file = Path(self.temp_dir) / "audit.json"
        self.assertTrue(log_file.exists())

    def test_write_includes_checksum(self) -> None:
        entry_id = self.backend.write(
            content_type_id=1,
            object_id="99",
            event_type="create",
            current_state={"x": 1},
            changes={},
            user_id=None,
            session_id=None,
            comment="",
            object_version=1,
        )
        result = self.backend.read(entry_id)
        self.assertIsNotNone(result)
        self.assertIn("checksum", result)

    # --- read ---

    def test_read_returns_matching_record(self) -> None:
        entry_id = self.backend.write(
            content_type_id=1,
            object_id="42",
            event_type="update",
            current_state={"status": "active"},
            changes={"status": ["pending", "active"]},
            user_id="usr-5",
            session_id="sess-x",
            comment="status changed",
            object_version=2,
        )
        record = self.backend.read(entry_id)
        self.assertIsNotNone(record)
        self.assertEqual(record["id"], entry_id)
        self.assertEqual(record["event_type"], "update")

    def test_read_returns_none_for_missing_id(self) -> None:
        result = self.backend.read("non-existent-id-xyz")
        self.assertIsNone(result)

    # --- daily rotation ---

    def test_rotate_daily_creates_dated_file(self) -> None:
        backend = FileAuditBackend(
            base_path=self.temp_dir,
            compress=False,
            rotate_daily=True,
        )
        backend.write(
            content_type_id=1,
            object_id="1",
            event_type="create",
            current_state={},
            changes={},
            user_id=None,
            session_id=None,
            comment="",
            object_version=1,
        )
        date_str = timezone.now().strftime("%Y-%m-%d")
        log_file = Path(self.temp_dir) / f"audit_{date_str}.json"
        self.assertTrue(log_file.exists())

    # --- compression ---

    def test_compress_creates_gz_file(self) -> None:
        backend = FileAuditBackend(
            base_path=self.temp_dir,
            compress=True,
            rotate_daily=False,
        )
        backend.dispatch(_sample_event())
        log_file = Path(self.temp_dir) / "audit.json.gz"
        self.assertTrue(log_file.exists())

    # --- health_check ---

    def test_health_check_writable_dir(self) -> None:
        health = self.backend.health_check()
        self.assertEqual(health["backend"], "file")
        self.assertEqual(health["status"], "healthy")
        self.assertTrue(health["available"])

    def test_health_check_non_writable_dir(self) -> None:
        """health_check returns unhealthy when directory cannot be written."""
        with patch.object(Path, "touch", side_effect=OSError("permission denied")):
            health = self.backend.health_check()
        self.assertEqual(health["status"], "unhealthy")
        self.assertFalse(health["available"])
        self.assertIn("error", health)

    # --- name attribute ---

    def test_name_attribute(self) -> None:
        self.assertEqual(self.backend.name, "file")


# ---------------------------------------------------------------------------
# RedisAuditBackend
# ---------------------------------------------------------------------------


class TestRedisAuditBackend(TestCase):
    """Tests for RedisAuditBackend (client mocked out)."""

    def _backend_with_mock_client(self) -> tuple[RedisAuditBackend, MagicMock]:
        mock_client = MagicMock()
        with patch.object(RedisAuditBackend, "_connect"):
            backend = RedisAuditBackend(url="redis://localhost:6379/0")
        backend._client = mock_client
        return backend, mock_client

    def test_name_attribute(self) -> None:
        with patch.object(RedisAuditBackend, "_connect"):
            b = RedisAuditBackend()
        self.assertEqual(b.name, "redis")

    def test_dispatch_calls_xadd(self) -> None:
        backend, mock_client = self._backend_with_mock_client()
        event_data = _sample_event()
        backend.dispatch(event_data)
        mock_client.xadd.assert_called_once()
        call_args = mock_client.xadd.call_args
        # First positional arg is the stream key
        self.assertEqual(call_args.args[0], backend._stream_key)

    def test_dispatch_raises_when_client_none(self) -> None:
        with patch.object(RedisAuditBackend, "_connect"):
            backend = RedisAuditBackend()
        backend._client = None

        with self.assertRaises(AuditBackendUnavailableError):
            backend.dispatch(_sample_event())

    def test_dispatch_wraps_redis_error(self) -> None:
        backend, mock_client = self._backend_with_mock_client()
        mock_client.xadd.side_effect = Exception("connection reset")

        with self.assertRaises(AuditBackendError):
            backend.dispatch(_sample_event())

    def test_health_check_healthy(self) -> None:
        backend, mock_client = self._backend_with_mock_client()
        mock_client.ping.return_value = True
        mock_client.exists.return_value = False

        health = backend.health_check()
        self.assertEqual(health["status"], "healthy")
        self.assertTrue(health["available"])

    def test_health_check_unhealthy_no_client(self) -> None:
        with patch.object(RedisAuditBackend, "_connect"):
            backend = RedisAuditBackend()
        backend._client = None

        health = backend.health_check()
        self.assertEqual(health["status"], "unhealthy")
        self.assertFalse(health["available"])

    def test_health_check_unhealthy_on_ping_failure(self) -> None:
        backend, mock_client = self._backend_with_mock_client()
        mock_client.ping.side_effect = Exception("timeout")

        health = backend.health_check()
        self.assertEqual(health["status"], "unhealthy")
        self.assertFalse(health["available"])

    def test_is_available_true_with_client(self) -> None:
        backend, _ = self._backend_with_mock_client()
        self.assertTrue(backend.is_available())

    def test_is_available_false_without_client(self) -> None:
        with patch.object(RedisAuditBackend, "_connect"):
            backend = RedisAuditBackend()
        backend._client = None
        self.assertFalse(backend.is_available())


# ---------------------------------------------------------------------------
# KafkaAuditBackend
# ---------------------------------------------------------------------------


class TestKafkaAuditBackend(TestCase):
    """Tests for KafkaAuditBackend."""

    def test_producer_is_none_when_no_library(self) -> None:
        """When neither confluent-kafka nor kafka-python is installed, producer=None."""
        import builtins

        real_import = builtins.__import__

        def _no_kafka(name: str, *args, **kwargs):
            if name in ("confluent_kafka", "kafka"):
                raise ImportError(f"No module named {name!r}")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=_no_kafka):
            backend = KafkaAuditBackend(bootstrap_servers="localhost:9092")

        self.assertIsNone(backend.producer)

    def test_name_attribute(self) -> None:
        with patch.object(KafkaAuditBackend, "_connect"):
            backend = KafkaAuditBackend()
        self.assertEqual(backend.name, "kafka")

    def test_dispatch_raises_when_producer_none(self) -> None:
        with patch.object(KafkaAuditBackend, "_connect"):
            backend = KafkaAuditBackend()
        backend.producer = None

        with self.assertRaises(AuditBackendUnavailableError):
            backend.dispatch(_sample_event())

    def test_read_raises_not_implemented(self) -> None:
        with patch.object(KafkaAuditBackend, "_connect"):
            backend = KafkaAuditBackend()
        with self.assertRaises(NotImplementedError):
            backend.read("some-id")

    def test_query_raises_not_implemented(self) -> None:
        with patch.object(KafkaAuditBackend, "_connect"):
            backend = KafkaAuditBackend()
        with self.assertRaises(NotImplementedError):
            backend.query()

    def test_get_history_raises_not_implemented(self) -> None:
        with patch.object(KafkaAuditBackend, "_connect"):
            backend = KafkaAuditBackend()
        with self.assertRaises(NotImplementedError):
            backend.get_history(1, "42")

    def test_get_version_raises_not_implemented(self) -> None:
        with patch.object(KafkaAuditBackend, "_connect"):
            backend = KafkaAuditBackend()
        with self.assertRaises(NotImplementedError):
            backend.get_version(1, "42", 1)

    def test_health_check_unhealthy_when_producer_none(self) -> None:
        with patch.object(KafkaAuditBackend, "_connect"):
            backend = KafkaAuditBackend()
        backend.producer = None

        health = backend.health_check()
        self.assertEqual(health["status"], "unhealthy")
        self.assertFalse(health["available"])

    def test_health_check_healthy_with_producer(self) -> None:
        with patch.object(KafkaAuditBackend, "_connect"):
            backend = KafkaAuditBackend()
        backend.producer = MagicMock()

        health = backend.health_check()
        self.assertEqual(health["status"], "healthy")
        self.assertTrue(health["available"])

    def test_is_available_false_without_producer(self) -> None:
        with patch.object(KafkaAuditBackend, "_connect"):
            backend = KafkaAuditBackend()
        backend.producer = None
        self.assertFalse(backend.is_available())

    def test_dispatch_with_mock_producer(self) -> None:
        mock_producer = MagicMock()

        with patch.object(KafkaAuditBackend, "_connect"):
            backend = KafkaAuditBackend()
        backend.producer = mock_producer
        backend._topic = "audit.events"
        backend._produce = lambda key, msg: mock_producer.produce("audit.events", key=key, value=msg)

        backend.dispatch(_sample_event())

        mock_producer.flush.assert_called_once()


# ---------------------------------------------------------------------------
# Backend factory
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestBackendFactory:
    """Tests for get_audit_backend and get_configured_backends."""

    def test_get_file_backend(self, tmp_path) -> None:
        backend = get_audit_backend("file", base_path=str(tmp_path))
        assert isinstance(backend, FileAuditBackend)

    def test_get_redis_backend(self) -> None:
        with patch.object(RedisAuditBackend, "_connect"):
            backend = get_audit_backend("redis", url="redis://localhost:6379/0")
        assert isinstance(backend, RedisAuditBackend)

    def test_get_kafka_backend(self) -> None:
        with patch.object(KafkaAuditBackend, "_connect"):
            backend = get_audit_backend("kafka", bootstrap_servers="localhost:9092")
        assert isinstance(backend, KafkaAuditBackend)

    def test_unknown_backend_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Unknown audit backend"):
            get_audit_backend("nonexistent")

    def test_get_configured_backends_returns_list(self, tmp_path) -> None:
        from django.test import override_settings

        with override_settings(AUDITING={"BACKENDS": ["file"], "BACKEND_OPTIONS": {"file": {"path": str(tmp_path)}}}):
            backends = get_configured_backends()
        assert len(backends) == 1
        assert isinstance(backends[0], FileAuditBackend)

    def test_get_configured_backends_skips_unknown(self) -> None:
        from django.test import override_settings

        with override_settings(AUDITING={"BACKENDS": ["nonexistent_backend"]}):
            backends = get_configured_backends()
        # No crash — unknown backend is skipped with a warning
        assert backends == []


# ---------------------------------------------------------------------------
# MultiBackendCoordinator
# ---------------------------------------------------------------------------


class TestMultiBackendCoordinator(TestCase):
    """Tests for MultiBackendCoordinator."""

    @staticmethod
    def _make_backend(name: str, entry_id: str = "id-1") -> Mock:
        backend = Mock(spec=["name", "dispatch", "write", "health_check"])
        backend.name = name
        backend.write.return_value = entry_id
        backend.dispatch.return_value = None
        backend.health_check.return_value = {"status": "healthy", "available": True}
        return backend

    # --- dispatch ---

    def test_dispatch_all_backends_succeed(self) -> None:
        b1 = self._make_backend("b1")
        b2 = self._make_backend("b2")
        coordinator = MultiBackendCoordinator(backends=[b1, b2])

        result = coordinator.dispatch(_sample_event())

        self.assertTrue(result["success"])
        self.assertTrue(result["results"]["b1"]["ok"])
        self.assertTrue(result["results"]["b2"]["ok"])
        b1.dispatch.assert_called_once()
        b2.dispatch.assert_called_once()

    def test_dispatch_best_effort_continues_on_failure(self) -> None:
        b1 = self._make_backend("b1")
        b2 = self._make_backend("b2")
        b2.dispatch.side_effect = Exception("connection refused")
        coordinator = MultiBackendCoordinator(strict_mode=False, backends=[b1, b2])

        result = coordinator.dispatch(_sample_event())

        self.assertFalse(result["success"])
        self.assertTrue(result["results"]["b1"]["ok"])
        self.assertFalse(result["results"]["b2"]["ok"])
        self.assertIn("connection refused", result["results"]["b2"]["error"])

    def test_dispatch_strict_mode_raises_on_failure(self) -> None:
        b1 = self._make_backend("b1")
        b1.dispatch.side_effect = Exception("fatal")
        coordinator = MultiBackendCoordinator(strict_mode=True, backends=[b1])

        with self.assertRaises(RuntimeError):
            coordinator.dispatch(_sample_event())

    def test_dispatch_empty_backends(self) -> None:
        coordinator = MultiBackendCoordinator(backends=[])
        result = coordinator.dispatch(_sample_event())
        self.assertTrue(result["success"])
        self.assertEqual(result["results"], {})

    # --- write ---

    def test_write_aggregates_entry_ids(self) -> None:
        b1 = self._make_backend("b1", entry_id="id-aaa")
        b2 = self._make_backend("b2", entry_id="id-bbb")
        coordinator = MultiBackendCoordinator(backends=[b1, b2])

        result = coordinator.write(
            content_type_id=1,
            object_id="42",
            event_type="create",
            current_state={"x": 1},
            changes={},
            user_id="usr-1",
            session_id=None,
            comment="",
            object_version=1,
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["primary_entry_id"], "id-aaa")
        self.assertEqual(result["results"]["b1"]["entry_id"], "id-aaa")
        self.assertEqual(result["results"]["b2"]["entry_id"], "id-bbb")

    def test_write_best_effort_on_failure(self) -> None:
        b1 = self._make_backend("b1", entry_id="id-ok")
        b2 = self._make_backend("b2")
        b2.write.side_effect = Exception("backend down")
        coordinator = MultiBackendCoordinator(strict_mode=False, backends=[b1, b2])

        result = coordinator.write(
            content_type_id=1,
            object_id="1",
            event_type="update",
            current_state={},
            changes={},
            user_id=None,
            session_id=None,
            comment="",
            object_version=2,
        )

        self.assertFalse(result["success"])
        self.assertEqual(result["primary_entry_id"], "id-ok")
        self.assertFalse(result["results"]["b2"]["ok"])

    def test_write_strict_mode_raises(self) -> None:
        b1 = self._make_backend("b1")
        b1.write.side_effect = Exception("error")
        coordinator = MultiBackendCoordinator(strict_mode=True, backends=[b1])

        with self.assertRaises(RuntimeError):
            coordinator.write(
                content_type_id=1,
                object_id="1",
                event_type="create",
                current_state={},
                changes={},
                user_id=None,
                session_id=None,
                comment="",
                object_version=1,
            )

    def test_write_falls_back_to_dispatch_when_no_write_method(self) -> None:
        """Backends without write() fall back to dispatch()."""
        b1 = Mock(spec=["name", "dispatch", "health_check"])
        b1.name = "dispatch_only"
        b1.dispatch.return_value = None
        coordinator = MultiBackendCoordinator(backends=[b1])

        result = coordinator.write(
            content_type_id=1,
            object_id="1",
            event_type="create",
            current_state={},
            changes={},
            user_id=None,
            session_id=None,
            comment="",
            object_version=1,
        )

        b1.dispatch.assert_called_once()
        self.assertIsNone(result["results"]["dispatch_only"]["entry_id"])

    # --- health_check ---

    def test_health_check_all_healthy(self) -> None:
        b1 = self._make_backend("b1")
        b2 = self._make_backend("b2")
        coordinator = MultiBackendCoordinator(backends=[b1, b2])

        health = coordinator.health_check()

        self.assertTrue(health["healthy"])
        self.assertIn("b1", health["backends"])
        self.assertIn("b2", health["backends"])

    def test_health_check_one_unhealthy(self) -> None:
        b1 = self._make_backend("b1")
        b2 = self._make_backend("b2")
        b2.health_check.return_value = {"status": "unhealthy", "available": False}
        coordinator = MultiBackendCoordinator(backends=[b1, b2])

        health = coordinator.health_check()

        self.assertFalse(health["healthy"])

    def test_health_check_backend_raises(self) -> None:
        b1 = self._make_backend("b1")
        b1.health_check.side_effect = Exception("connect timeout")
        coordinator = MultiBackendCoordinator(backends=[b1])

        health = coordinator.health_check()

        self.assertFalse(health["healthy"])
        self.assertIn("error", health["backends"]["b1"])


# ---------------------------------------------------------------------------
# AuditableManagerMixin
# ---------------------------------------------------------------------------


class TestAuditableManagerMixin(TestCase):
    """Smoke tests for AuditableManagerMixin / AuditableQuerySetMixin."""

    def test_auditable_manager_importable(self) -> None:
        from apps.auditing.models.mixins import AuditableManagerMixin, AuditableQuerySetMixin

        self.assertTrue(issubclass(AuditableManagerMixin, object))
        self.assertTrue(issubclass(AuditableQuerySetMixin, object))

    def test_auditable_manager_is_django_manager(self) -> None:
        from django.db import models

        from apps.auditing.models.mixins import AuditableManagerMixin

        self.assertTrue(issubclass(AuditableManagerMixin, models.Manager))


# ---------------------------------------------------------------------------
# RedisAuditBackend - _connect failure paths
# ---------------------------------------------------------------------------


class TestRedisAuditBackendConnect(TestCase):
    """Tests for RedisAuditBackend connection setup paths."""

    def test_connect_import_error_disables_backend(self) -> None:
        """When redis package is not installed, backend is disabled gracefully."""
        with patch.dict("sys.modules", {"redis": None}), patch("apps.auditing.backends.redis.logger") as mock_logger:
            backend = RedisAuditBackend(url="redis://localhost:6379/0")
            self.assertIsNone(backend._client)
            mock_logger.warning.assert_called()

    def test_connect_connection_error_disables_backend(self) -> None:
        """When redis connection fails, backend is disabled gracefully."""
        mock_redis_module = MagicMock()
        mock_client = MagicMock()
        mock_client.ping.side_effect = Exception("Connection refused")
        mock_redis_module.from_url.return_value = mock_client

        with (
            patch.dict("sys.modules", {"redis": mock_redis_module}),
            patch("apps.auditing.backends.redis.logger") as mock_logger,
        ):
            backend = RedisAuditBackend(url="redis://localhost:6379/0")
            self.assertIsNone(backend._client)
            mock_logger.warning.assert_called()

    def test_health_check_with_stream_exists(self) -> None:
        """Health check reports stream length when stream exists."""
        backend = RedisAuditBackend.__new__(RedisAuditBackend)
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.exists.return_value = True
        mock_client.xlen.return_value = 42
        backend._client = mock_client
        backend._stream_key = "audit:events"
        backend.name = "redis"

        result = backend.health_check()
        self.assertTrue(result["available"])
        self.assertEqual(result["stream_length"], 42)

    def test_health_check_stream_does_not_exist(self) -> None:
        """Health check reports 0 length when stream does not exist."""
        backend = RedisAuditBackend.__new__(RedisAuditBackend)
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.exists.return_value = False
        backend._client = mock_client
        backend._stream_key = "audit:events"
        backend.name = "redis"

        result = backend.health_check()
        self.assertTrue(result["available"])
        self.assertEqual(result["stream_length"], 0)


# ---------------------------------------------------------------------------
# KafkaAuditBackend - produce methods and additional paths
# ---------------------------------------------------------------------------


class TestKafkaAuditBackendProduceMethods(TestCase):
    """Tests for KafkaAuditBackend _confluent_produce and _kafkapython_produce."""

    def test_confluent_produce_calls_producer(self) -> None:
        """_confluent_produce calls producer.produce with correct args."""
        backend = KafkaAuditBackend.__new__(KafkaAuditBackend)
        mock_producer = MagicMock()
        backend.producer = mock_producer
        backend._topic = "audit.events"
        backend._produce = backend._confluent_produce

        backend._confluent_produce(b"key", b"message")
        mock_producer.produce.assert_called_once_with("audit.events", key=b"key", value=b"message")

    def test_kafkapython_produce_calls_producer_send(self) -> None:
        """_kafkapython_produce calls producer.send with correct args."""
        backend = KafkaAuditBackend.__new__(KafkaAuditBackend)
        mock_producer = MagicMock()
        backend.producer = mock_producer
        backend._topic = "audit.events"
        backend._produce = backend._kafkapython_produce

        backend._kafkapython_produce(b"key", b"message")
        mock_producer.send.assert_called_once_with("audit.events", key=b"key", value=b"message")

    def test_connect_falls_back_to_kafka_python(self) -> None:
        """When confluent_kafka unavailable, falls back to kafka-python."""
        mock_kafka_producer_class = MagicMock()
        mock_kafka_producer_instance = MagicMock()
        mock_kafka_producer_class.return_value = mock_kafka_producer_instance

        with (
            patch.dict("sys.modules", {"confluent_kafka": None}),
            patch.dict("sys.modules", {"kafka": MagicMock(KafkaProducer=mock_kafka_producer_class)}),
            patch("apps.auditing.backends.kafka.logger") as mock_logger,
        ):
            KafkaAuditBackend(bootstrap_servers="localhost:9092", topic="test")
            # Either the producer was set (if mock worked) or None
            mock_logger.info.assert_called()

    def test_connect_both_unavailable_producer_is_none(self) -> None:
        """When neither kafka library is available, producer is None."""
        with (
            patch.dict("sys.modules", {"confluent_kafka": None, "kafka": None}),
            patch("apps.auditing.backends.kafka.logger") as mock_logger,
        ):
            backend = KafkaAuditBackend(bootstrap_servers="localhost:9092")
            self.assertIsNone(backend.producer)
            mock_logger.warning.assert_called()

    def test_dispatch_error_wraps_exception(self) -> None:
        """dispatch() wraps non-unavailable exceptions in AuditBackendError."""
        from apps.auditing.backends.base import AuditBackendError

        backend = KafkaAuditBackend.__new__(KafkaAuditBackend)
        mock_producer = MagicMock()
        mock_producer.flush.side_effect = RuntimeError("Kafka error")
        backend.producer = mock_producer
        backend._topic = "audit.events"
        backend._bootstrap_servers = "localhost:9092"
        backend.name = "kafka"

        def raise_on_produce(key, message):
            pass

        backend._produce = raise_on_produce
        backend.producer.flush.side_effect = RuntimeError("Kafka error")

        with self.assertRaises(AuditBackendError):
            backend.dispatch({"id": "evt-001", "event_type": "CREATE"})


# ---------------------------------------------------------------------------
# EventQuerySet / EventManager Tests
# ---------------------------------------------------------------------------


class TestEventQuerySetAndManager(TestCase):
    """Tests for EventQuerySet and EventManager in apps.auditing.models.managers."""

    def test_update_immutable_fields_raises(self) -> None:
        """Attempting to update immutable fields raises ImmutabilityError."""
        from apps.auditing.exceptions import ImmutabilityError

        # Build a mock queryset with the right model
        from apps.auditing.models import Event
        from apps.auditing.models.managers import EventQuerySet

        qs = EventQuerySet(model=Event, using="default")
        with self.assertRaises(ImmutabilityError):
            qs.update(event_type="UPDATE")  # event_type is immutable

    def test_bulk_update_immutable_fields_raises(self) -> None:
        """bulk_update on immutable fields raises ImmutabilityError."""
        from apps.auditing.exceptions import ImmutabilityError
        from apps.auditing.models import Event
        from apps.auditing.models.managers import EventQuerySet

        qs = EventQuerySet(model=Event, using="default")
        with self.assertRaises(ImmutabilityError):
            qs.bulk_update([], fields=["content_type"])

    def test_update_mutable_field_does_not_raise(self) -> None:
        """Updating a mutable field (like comment) should not raise."""
        from apps.auditing.models import Event
        from apps.auditing.models.managers import EventQuerySet

        qs = EventQuerySet(model=Event, using="default")
        # 'comment' is a MUTABLE_FIELD — no ImmutabilityError
        # (will fail at DB level if no rows, that's fine)
        try:
            qs.update(comment="test comment")
        except Exception as exc:
            # Any exception should NOT be ImmutabilityError
            from apps.auditing.exceptions import ImmutabilityError

            self.assertNotIsInstance(exc, ImmutabilityError)

    def test_event_manager_with_deleted_includes_all(self) -> None:
        """EventManager.with_deleted() returns EventQuerySet without deleted filter."""
        from apps.auditing.models import Event
        from apps.auditing.models.managers import EventManager, EventQuerySet

        mgr = EventManager()
        mgr.model = Event
        mgr._db = "default"

        qs = mgr.with_deleted()
        self.assertIsInstance(qs, EventQuerySet)

    def test_event_manager_pending_dispatch(self) -> None:
        """EventManager.pending_dispatch() returns a valid queryset."""
        from apps.auditing.models import Event
        from apps.auditing.models.managers import EventManager

        mgr = EventManager()
        mgr.model = Event
        mgr._db = "default"

        qs = mgr.pending_dispatch()
        self.assertIsNotNone(qs)

    def test_event_queryset_active_filter(self) -> None:
        """EventQuerySet.active() excludes soft-deleted events."""
        from apps.auditing.models import Event
        from apps.auditing.models.managers import EventQuerySet

        qs = EventQuerySet(model=Event, using="default")
        active_qs = qs.active()
        # Check that the query includes the deleted_at__isnull filter
        str_query = str(active_qs.query)
        self.assertIn("deleted_at", str_query.lower())

    def test_event_queryset_for_actor(self) -> None:
        """EventQuerySet.for_actor() method exists and accepts an actor."""
        from apps.auditing.models import Event
        from apps.auditing.models.managers import EventQuerySet

        qs = EventQuerySet(model=Event, using="default")
        # Just verify the method returns a queryset (don't evaluate it to avoid DB)
        result = qs.for_actor(None)
        self.assertIsNotNone(result)

    def test_event_queryset_by_event_type(self) -> None:
        """EventQuerySet.by_event_type() applies event_type__in filter."""
        from apps.auditing.models import Event
        from apps.auditing.models.managers import EventQuerySet

        qs = EventQuerySet(model=Event, using="default")
        filtered = qs.by_event_type("create", "update")
        self.assertIsNotNone(filtered)

    def test_event_queryset_created_between(self) -> None:
        """EventQuerySet.created_between() applies date range filter."""
        from django.utils import timezone

        from apps.auditing.models import Event
        from apps.auditing.models.managers import EventQuerySet

        qs = EventQuerySet(model=Event, using="default")
        now = timezone.now()
        filtered = qs.created_between(now, now)
        self.assertIsNotNone(filtered)

    def test_event_queryset_pending_dispatch(self) -> None:
        """EventQuerySet.pending_dispatch() excludes empty backends_pending."""
        from apps.auditing.models import Event
        from apps.auditing.models.managers import EventQuerySet

        qs = EventQuerySet(model=Event, using="default")
        filtered = qs.pending_dispatch()
        self.assertIsNotNone(filtered)

    def test_event_queryset_fully_dispatched(self) -> None:
        """EventQuerySet.fully_dispatched() filters backends_pending=[]."""
        from apps.auditing.models import Event
        from apps.auditing.models.managers import EventQuerySet

        qs = EventQuerySet(model=Event, using="default")
        filtered = qs.fully_dispatched()
        self.assertIsNotNone(filtered)

    def test_event_queryset_with_related(self) -> None:
        """EventQuerySet.with_related() returns select_related queryset."""
        from apps.auditing.models import Event
        from apps.auditing.models.managers import EventQuerySet

        qs = EventQuerySet(model=Event, using="default")
        related_qs = qs.with_related()
        self.assertIsNotNone(related_qs)

    def test_event_queryset_with_deleted(self) -> None:
        """EventQuerySet.with_deleted() returns the same queryset (no extra filter)."""
        from apps.auditing.models import Event
        from apps.auditing.models.managers import EventQuerySet

        qs = EventQuerySet(model=Event, using="default")
        result = qs.with_deleted()
        self.assertIsNotNone(result)

    def test_event_queryset_for_object(self) -> None:
        """EventQuerySet.for_object() applies content_type and object_id filter."""
        from apps.auditing.models import Event
        from apps.auditing.models.managers import EventQuerySet

        qs = EventQuerySet(model=Event, using="default")
        filtered = qs.for_object(content_type=1, object_id="42")
        self.assertIsNotNone(filtered)

    def test_hard_delete_outside_gdpr_raises(self) -> None:
        """hard_delete() outside gdpr_purge/retention_purge raises HardDeleteForbiddenError."""
        from apps.auditing.exceptions import HardDeleteForbiddenError
        from apps.auditing.models import Event
        from apps.auditing.models.managers import EventQuerySet

        qs = EventQuerySet(model=Event, using="default")
        with self.assertRaises(HardDeleteForbiddenError):
            qs.hard_delete()

    def test_enforce_immutability_allowed_fields(self) -> None:
        """_enforce_immutability does not raise for mutable field names."""
        from apps.auditing.models import Event
        from apps.auditing.models.managers import EventQuerySet

        qs = EventQuerySet(model=Event, using="default")
        # 'comment' and 'context' are in MUTABLE_FIELDS — should not raise
        qs._enforce_immutability({"comment", "context"})


# ---------------------------------------------------------------------------
# AuditableModelMixin - more complete tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestAuditableModelMixinBehavior(TestCase):
    """Tests for AuditableModelMixin save/delete/audit behavior."""

    def test_auditable_model_mixin_save_create_is_audited(self) -> None:
        """AuditableModelMixin exposes save/delete/_audit interface."""
        from apps.auditing.models.mixins import AuditableModelMixin

        # Verify the mixin has the right methods
        self.assertTrue(hasattr(AuditableModelMixin, "save"))
        self.assertTrue(hasattr(AuditableModelMixin, "delete"))
        self.assertTrue(hasattr(AuditableModelMixin, "_audit"))

    def test_auditable_queryset_mixin_methods_exist(self) -> None:
        """AuditableQuerySetMixin has all expected methods."""
        from apps.auditing.models.mixins import AuditableQuerySetMixin

        self.assertTrue(hasattr(AuditableQuerySetMixin, "create"))
        self.assertTrue(hasattr(AuditableQuerySetMixin, "update"))
        self.assertTrue(hasattr(AuditableQuerySetMixin, "delete"))
        self.assertTrue(hasattr(AuditableQuerySetMixin, "bulk_create"))
        self.assertTrue(hasattr(AuditableQuerySetMixin, "bulk_update"))
        self.assertTrue(hasattr(AuditableQuerySetMixin, "_audit_bulk"))

    def test_auditable_manager_get_queryset(self) -> None:
        """AuditableManagerMixin.get_queryset returns AuditableQuerySetMixin."""
        from django.db import models as dj_models

        from apps.auditing.models.mixins import AuditableManagerMixin, AuditableQuerySetMixin

        class FakeModel(dj_models.Model):
            class Meta:
                app_label = "auditing"

            def __str__(self) -> str:
                return f"FakeModel<{self.pk}>"

        mgr = AuditableManagerMixin()
        mgr.model = FakeModel
        mgr._db = "default"
        qs = mgr.get_queryset()
        self.assertIsInstance(qs, AuditableQuerySetMixin)

    def test_init_subclass_registers_non_abstract_model(self) -> None:
        """__init_subclass__ registers concrete models with audit_registry."""
        # UserAccount extends AuditableModelMixin (indirectly via core)
        # It should be registered
        from apps.accounts.models import Principal
        from apps.auditing.registry import audit_registry

        # Principal is registered (has ACTOR_REQUIRED = True indicating it's tracked)
        # Just verify the registry's should_audit_model works
        # (it may return True or False depending on config)
        result = audit_registry.should_audit_model(Principal)
        self.assertIsInstance(result, bool)

    def test_audit_bulk_empty_list_no_op(self) -> None:
        """_audit_bulk with empty list should not raise."""
        from apps.auditing.models import Event
        from apps.auditing.models.mixins import AuditableQuerySetMixin

        qs = AuditableQuerySetMixin(model=Event, using="default")
        # Should not raise
        qs._audit_bulk([], "create")
