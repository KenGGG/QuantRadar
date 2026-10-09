import json
from unittest.mock import Mock,patch
import pytest
from quantradar2.frozen import Recorder,Replay,FrozenProvider,FrozenDataError

def test_record_replay_exact_response_without_connecting(tmp_path):
    connection=Mock();connection.request.return_value={"dtype":"dataframe","columns":["open"],"records":[[1.25]]}
    directory=tmp_path/"frozen";identity={"source":"test"}
    recorder=Recorder(connection,directory,identity)
    request={"security":"600519.XSHG","count":1}
    actual=recorder.request("data.history",request)
    with patch("bullet_trade.data.providers.remote_qmt.RemoteQmtConnection") as network:
        replay=Replay(directory,identity);provider=FrozenProvider(replay)
        assert provider._connection.request("data.history",request)==actual
        network.assert_not_called()
        with pytest.raises(FrozenDataError,match="network fallback forbidden"):
            provider._connection.request("data.history",dict(request,count=2))
        assert replay.errors

def test_frozen_corruption_or_input_changes_rejected(tmp_path):
    connection=Mock();connection.request.return_value={"value":123}
    directory=tmp_path/"frozen";recorder=Recorder(connection,directory,{"code":"original"})
    recorder.request("data.security_info",{"security":"x"})
    with pytest.raises(FrozenDataError,match="identity mismatch"):Replay(directory,{"code":"changed"})
    content=next(p for p in directory.iterdir() if p.name!="manifest.json")
    content.write_text("changed")
    with pytest.raises(FrozenDataError,match="checksum mismatch"):Replay(directory,{"code":"original"})

def test_mutating_response_during_recording_rejected(tmp_path):
    connection=Mock();connection.request.side_effect=[{"value":1},{"value":2}]
    recorder=Recorder(connection,tmp_path/"frozen",{})
    recorder.request("data.history",{})
    with pytest.raises(FrozenDataError,match="changed during recording"):recorder.request("data.history",{})
    assert recorder.errors

def test_recording_io_failure_is_remembered_even_if_native_engine_catches_it(tmp_path):
    connection=Mock();connection.request.return_value={"value":1}
    recorder=Recorder(connection,tmp_path/"frozen",{})
    with patch("quantradar2.frozen.write",side_effect=OSError("disk unavailable")):
        with pytest.raises(OSError):recorder.request("data.history",{})
    assert "Recording failed: OSError" in recorder.errors[0]
