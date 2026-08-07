import logging
import uuid
from pathlib import Path


from bullet_trade.core.globals import Logger


def test_configure_file_logging_switches_directory(tmp_path, monkeypatch):
    token = uuid.uuid4().hex
    real_get_logger = logging.getLogger

    def _fake_get_logger(name=None):
        target = name or ''
        if target.startswith('jq_strategy'):
            logger = real_get_logger(f"{target}_{token}")
            for handler in list(logger.handlers):
                logger.removeHandler(handler)
            return logger
        return real_get_logger(name)

    monkeypatch.setattr('bullet_trade.core.globals.logging.getLogger', _fake_get_logger)
    monkeypatch.setenv('LOG_DIR', str(tmp_path / "bootstrap"))

    logger = Logger()

    first_dir = tmp_path / "first"
    logger.configure_file_logging(log_dir=str(first_dir))
    handler = logger._file_handler
    assert handler is not None
    assert Path(handler.baseFilename).parent == first_dir.resolve()

    second_dir = tmp_path / "second"
    logger.configure_file_logging(log_dir=str(second_dir), level_name='DEBUG')
    handler2 = logger._file_handler
    assert handler2 is not None
    assert Path(handler2.baseFilename).parent == second_dir.resolve()
    assert handler2.level == logging.DEBUG


def test_configure_file_logging_accepts_file_path(tmp_path, monkeypatch):
    token = uuid.uuid4().hex
    real_get_logger = logging.getLogger

    def _fake_get_logger(name=None):
        target = name or ''
        if target.startswith('jq_strategy'):
            logger = real_get_logger(f"{target}_{token}")
            for handler in list(logger.handlers):
                logger.removeHandler(handler)
            return logger
        return real_get_logger(name)

    monkeypatch.setattr('bullet_trade.core.globals.logging.getLogger', _fake_get_logger)
    logger = Logger()
    log_file = tmp_path / "custom.log"
    logger.configure_file_logging(file_path=str(log_file), level_name='ERROR')
    handler = logger._file_handler
    assert handler is not None
    assert Path(handler.baseFilename) == log_file.resolve()
    assert handler.level == logging.ERROR
