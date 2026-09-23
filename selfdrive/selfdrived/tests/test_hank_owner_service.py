"""Exercise real local request transport and messaging freshness conversion."""
import json
import socket
from dataclasses import replace

import pytest
from cereal import messaging

from openpilot.common.params import Params, ParamKeyFlag
from openpilot.selfdrive.selfdrived import hank_owner as ho
from openpilot.selfdrive.selfdrived.tests.test_hank_owner import observation, cp_for, BOOT_A
from openpilot.system.manager.hank_owner_service import OwnerService, socket_address


@pytest.fixture
def service(tmp_path):
  params = Params(str(tmp_path))
  params.put(ho.OWNER, False)
  sm = messaging.SubMaster(["deviceState", "selfdriveState", "carControl", "carState", "carParams", "pandaStates"])
  service = OwnerService(params, sm, clock_ns=lambda: int(11e9))
  service.coordinator.boot_id_reader = lambda: BOOT_A
  yield params, sm, service
  service.close()


def test_single_coordinator_socket_and_thin_request(service):
  params, sm, server = service
  with pytest.raises(OSError):
    OwnerService(params, sm)
  params.clear_all(ParamKeyFlag.CLEAR_ON_ONROAD_TRANSITION)
  server.coordinator.session_cleared(int(10e9), int(10.1e9))
  params.put("CarParams", cp_for("HANK").to_bytes())
  evidence = observation()
  server.observe = lambda refresh=False: evidence
  server.poll()
  assert params.get(ho.GATE) is True
  with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as client:
    client.bind(bytes([0]) + (str(params.get_param_path()) + "-test").encode()[-100:])
    client.settimeout(1)
    client.sendto(b'{"target":"TSS"}', socket_address(params))
    server.poll()
    assert json.loads(client.recv(2048))["result"] == "REQUESTED"
    assert params.get(ho.OWNER) is True
    assert params.get(ho.CYCLE) is True
    params.put(ho.CYCLE, False)
    client.sendto(b'{"target":"TSS"}', socket_address(params))
    server.poll()
    assert json.loads(client.recv(2048))["result"] == "BLOCKED_UNVERIFIED"
    assert params.get(ho.CYCLE) is False


def test_real_message_timestamp_and_validity_forwarding(service):
  _, sm, server = service
  msg = messaging.new_message("deviceState")
  msg.valid = True
  msg.logMonoTime = int(10.5e9)
  msg.deviceState.started = True
  msg.deviceState.startedMonoTime = int(10e9)
  sm.update_msgs(11., [msg])
  evidence = server.observe()
  assert evidence.fresh("deviceState", int(10.1e9))
  assert evidence.samples["deviceState"].value.startedMonoTime == int(10e9)
  assert not evidence.fresh("carParams")
  assert not replace(evidence, now_ns=int(15e9)).fresh("deviceState")
  msg.valid = False
  sm.update_msgs(11.1, [msg])
  assert not server.observe().fresh("deviceState")


def test_service_requires_post_clear_carparams(service):
  params, _, server = service
  params.put("CarParams", cp_for("HANK").to_bytes())
  server.session_cleared(int(10e9))
  assert server.coordinator.fault
  assert params.get(ho.GATE) is False
