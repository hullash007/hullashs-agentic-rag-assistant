"""Opt-in local execution accounting. No runtime policy defaults or remote I/O.

A lease belongs to its submitted future, not to the coroutine awaiting it.
This is process-local cooperative admission, not a hard cancellation boundary.
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import math
import threading
import time


class OperationExpired(RuntimeError):
    pass


class OperationBusy(RuntimeError):
    pass


@dataclass(frozen=True)
class ExecutionPolicy:
    capacity: int
    workers: int
    total_seconds: float
    max_calls: int

    def __post_init__(self):
        if (type(self.capacity) is not int or type(self.workers) is not int or
            not 1 <= self.workers <= self.capacity or
            type(self.total_seconds) not in (int, float) or
            not math.isfinite(self.total_seconds) or self.total_seconds <= 0 or
            type(self.max_calls) is not int or not 1 <= self.max_calls <= 32):
            raise ValueError('explicit bounded execution policy required')


@dataclass(frozen=True)
class Operation:
    tenant: str
    kind: str
    deadline: float
    max_calls: int
    cancelled: threading.Event
    clock: object

    def check(self):
        if self.cancelled.is_set() or self.clock() >= self.deadline:
            raise OperationExpired('operation outcome not confirmed')

    def remaining(self):
        self.check()
        return self.deadline - self.clock()


class Lease:
    def __init__(self, owner, operation):
        self.owner, self.operation = owner, operation
        self.state = 'admitted'
        self.future = None

    def abandon(self):
        """Signal cancellation; only an unsubmitted lease releases here."""
        self.operation.cancelled.set()
        with self.owner._lock:
            if self.state == 'admitted':
                self.owner._release(self)
            future = self.future
        # Do not Future.cancel() queued items: ThreadPoolExecutor retains their
        # callable/arguments until dequeue even after cancellation. Keep the lease
        # until _run drains the item and observes the cancellation signal.

    def submit(self, function, *args, **kwargs):
        with self.owner._lock:
            if self.state != 'admitted':
                raise RuntimeError('lease already submitted or exited')
            try:
                self.operation.check()
                if self.owner._closing:
                    raise OperationBusy('execution admission closed')
                self.state = 'queued'
                self.future = self.owner._executor.submit(self._run, function, args, kwargs)
            except BaseException:
                self.owner._release(self)
                raise
            future = self.future
        future.add_done_callback(self._finished)
        return future

    def _run(self, function, args, kwargs):
        with self.owner._lock:
            self.state = 'running'
        self.operation.check()  # An expired queued worker must not call user work.
        return function(*args, operation=self.operation, **kwargs)

    def _finished(self, future):
        with self.owner._lock:
            self.owner._release(self)

    async def run(self, function, *args, **kwargs):
        future = self.submit(function, *args, **kwargs)
        try:
            # Shield prevents await cancellation from falsely owning worker lifetime.
            wrapped = asyncio.wrap_future(future)
            wrapped.add_done_callback(lambda done: None if done.cancelled() else done.exception())
            return await asyncio.shield(wrapped)
        except BaseException:
            self.abandon()
            raise


class AdmissionController:
    def __init__(self, policy, *, clock=time.monotonic):
        if not isinstance(policy, ExecutionPolicy) or not callable(clock):
            raise ValueError('explicit execution policy and clock required')
        self.policy, self.clock = policy, clock
        self._lock = threading.RLock()
        self._active = set()
        self._closing = False
        self._executor = ThreadPoolExecutor(max_workers=policy.workers,
                                            thread_name_prefix='rag-owned-worker')

    def admit(self, *, tenant, kind):
        if type(tenant) is not str or not tenant or kind not in ('upload', 'query'):
            raise ValueError('verified immutable tenant and operation kind required')
        operation = Operation(tenant, kind, self.clock() + self.policy.total_seconds,
                              self.policy.max_calls, threading.Event(), self.clock)
        with self._lock:
            if self._closing or len(self._active) >= self.policy.capacity:
                raise OperationBusy('execution capacity unavailable')
            operation.check()
            lease = Lease(self, operation)
            self._active.add(lease)
            return lease

    def _release(self, lease):
        # Called under lock, only for never-submitted or completed futures.
        if lease.state != 'exited':
            lease.state = 'exited'
            self._active.remove(lease)

    @property
    def active(self):
        with self._lock:
            return len(self._active)

    def shutdown(self, *, wait):
        with self._lock:
            self._closing = True
            leases = tuple(self._active)
        for lease in leases:
            lease.abandon()
        # wait=False does not claim active workers stopped. Queued wrappers drain
        # before releasing their retained-argument capacity; callbacks own permits.
        self._executor.shutdown(wait=wait, cancel_futures=False)
