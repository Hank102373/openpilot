"""Manager-local D-024 coordinator and deferred UI request transport.

The abstract Unix socket is only transport/single-instance exclusion, not state.
No UI writer may change owner Params. This service survives offroad cycles with
manager; a manager restart fails closed for every interrupted transaction.
"""
import hashlib
import json
import os
import socket
import time
import uuid

from openpilot.selfdrive.selfdrived.hank_owner import Evidence, OwnerCoordinator, Sample


def socket_address(params):
  identity = os.path.realpath(params.get_param_path()).encode()
  return bytes([0]) + b"hank-owner-" + hashlib.sha256(identity).hexdigest()[:24].encode()


def request_owner(params, target, timeout=3.0):
  """Thin future UI API: no Params mutation, no retry or alternate owner path."""
  with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as client:
    client.bind(bytes([0]) + f"hank-owner-client-{uuid.uuid4()}".encode())
    client.settimeout(timeout)
    client.sendto(json.dumps({"target": target}).encode(), socket_address(params))
    return json.loads(client.recv(2048))


class OwnerService:
  def __init__(self, params, sm, clock_ns=time.monotonic_ns):
    self.sm = sm
    self.clock_ns = clock_ns
    self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    # Do not unlink another owner's socket. A duplicate service cannot start.
    try:
      self.socket.bind(socket_address(params))
      self.socket.setblocking(False)
      self.coordinator = OwnerCoordinator(params)
    except Exception:
      self.socket.close()
      raise

  def close(self):
    self.socket.close()

  def session_cleared(self, epoch_ns):
    self.coordinator.session_cleared(epoch_ns, self.clock_ns())

  def observe(self, refresh=False):
    if refresh:
      self.sm.update(0)
    topics = ("deviceState", "selfdriveState", "carControl", "carState", "carParams", "pandaStates")
    return Evidence(self.clock_ns(), {
      topic: Sample(self.sm[topic], self.sm.logMonoTime[topic], self.sm.valid[topic])
      for topic in topics if self.sm.seen[topic]
    })

  def poll(self):
    self.coordinator.tick(self.observe())
    # Bounded work: repeated UI taps cannot starve the manager lifecycle.
    for _ in range(4):
      try:
        payload, address = self.socket.recvfrom(256)
      except BlockingIOError:
        break
      try:
        value = json.loads(payload)
        if type(value) is not dict or set(value) != {"target"}:
          raise ValueError("invalid owner request")
        result = self.coordinator.request(value["target"], lambda: self.observe(refresh=True))
      except (ValueError, TypeError, UnicodeError):
        result = "BLOCKED_INVALID_REQUEST"
      if address:
        try:
          self.socket.sendto(json.dumps({"result": result, "reason": self.coordinator.reason}).encode(), address)
        except OSError:
          pass  # Client disappearance must never replay a transaction.
