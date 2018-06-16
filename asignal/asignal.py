# -*- coding: utf-8 -*-

"""Main module."""

from asyncio import get_event_loop, Future
from collections import OrderedDict
from inspect import isawaitable
from itertools import chain
from ._saferef import safe_ref, BoundMethodWeakref


class Signal:
    __slots__ = ("__loop", "__listeners", "__weak_listeners", "__waiters")

    def __init__(self, *, loop=None):
        self.__loop = loop or get_event_loop()
        self.__listeners, self.__weak_listeners = set(), set()
        self.__waiters = Future()
        self.__waiters.set_result(None)

    @property
    def loop(self):
        return self.__loop

    def connect(self, listener, weak=True):
        if weak:
            self.__weak_listeners.add(safe_ref(listener, self.disconnect))
        else:
            self.__listeners.add(listener)

    def disconnect(self, listener):
        try:
            self.__listeners.remove(listener)
        except KeyError:
            try:
                if not isinstance(listener, BoundMethodWeakref):
                    listener = safe_ref(listener)

                self.__weak_listeners.remove(listener)
            except KeyError:
                pass

    def emit(self, *args, **kwargs):
        try:
            if len(self.__listeners) == 0 and len(self.__weak_listeners) == 0 and self.__waiters.done():
                return

            listeners = tuple(self.__listeners)
            weak_listeners = [wl() for wl in self.__weak_listeners]
            for listener in chain(listeners, weak_listeners):
                result = listener(*args, **kwargs)
                if isawaitable(result):
                    self.__loop.create_task(result)

            if self.__waiters.done():
                return

            # FIXME: possibly _very_ slow
            result = OrderedDict(kwargs)
            for i, v in enumerate(args):
                result[i] = v
            for k, v in kwargs.items():
                result[k] = v
            self.__waiters.set_result(result)
        except Exception as e:
            # TODO: real error handling
            raise e

    def __call__(self, *args, **kwargs):
        self.emit(*args, **kwargs)

    def __await__(self):
        if self.__waiters.done():
            self.__waiters = Future()
        yield from self.__waiters
