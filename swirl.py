# encoding: utf-8

"""
Provides some sugar to make Tornado's async stuff more palatable.
"""

import logging
import inspect
import functools
from tornado.ioloop import IOLoop
from tornado.web import RequestHandler, asynchronous as web_async

try:
    from inspect import isgeneratorfunction
except ImportError:
    # Python < 2.6
    def isgeneratorfunction(obj):
        return bool((inspect.isfunction(object) or
                     inspect.ismethod(object)) and
                    obj.func_code.co_flags & inspect.CO_GENERATOR)

__version__ = '0.1.1'


class CoroutineRunner(object):
    def __init__(self, generator, web_handler=None, io_loop=None,
                 callback = None):
        self.gen = generator
        self.web_handler = web_handler
        self.io_loop = io_loop
        self.work = None

        self.final_callback = callback

        # start the ball rolling...
        self.callback_proxy()

    def execute_work(self):
        return self.work(self.callback_proxy)

    def callback_proxy(self, *args, **kwargs):
        try:
            if len(args) > 0:
                if isinstance(args[-1], Exception):
                    self.work = self.gen.throw(args[-1])
                elif (hasattr(args[0], 'error') and
                      isinstance(args[0].error, Exception)):
                    self.work = self.gen.throw(args[0].error)
                else:
                    if args[-1] is None:
                        args = args[:-1]
                    if len(args) == 1:
                        self.work = self.gen.send(args[0])
                    else:
                        self.work = self.gen.send(args)
            else:
                self.work = self.gen.next()

            if isinstance(self.work, YieldReturn):
                raise StopIteration

            if self.io_loop is None:
                self.io_loop = IOLoop.instance()

            self.io_loop.add_callback(self.execute_work)
        except StopIteration:

            if self.web_handler and not self.web_handler._finished:
                self.web_handler.finish()

            if (isinstance(self.work, YieldReturn) and
                self.final_callback is not None):
                self.work(self.final_callback)

        except Exception, e:
            if self.web_handler:
                if self.web_handler._headers_written:
                    logging.error('Exception after headers written',
                        exc_info=True)
                else:
                    self.web_handler._handle_request_exception(e)
            else:
                raise


def return_(val):
    return YieldReturn(val)


class YieldReturn(object):
    def __init__(self, x):
        self.res = x

    def __call__(self, callback):
        if ((inspect.isfunction(self.res) or inspect.ismethod(self.res)) and
            getattr(self.res, "is_callback_wrapper", False)):
            self.res(callback)
        else:
            return callback(self.res)

    def __repr__(self):
        return "<Yielded '%r'>" % self.res


def make_asynchronous_decorator(io_loop):
    """
    Creates an asynchronous decorator that uses the given I/O loop.

    If the `io_loop` argument is None, the default IOLoop instance will be
    used.

    For information on how to use such a decorator, see
    `swirl.asynchronous`.
    """

    def asynchronous(coroutine, callback = None):
        """
        Allows a function to not use explicit callback functions to respond
        to asynchronous events.
        """

        if not isgeneratorfunction(coroutine):
            # the "coroutine" isn't actually a coroutine; just return
            # its result like tornado.web.asynchronous would do
            if callback is not None:
                return callback(coroutine)
            else:
                return coroutine

        web_async_coroutine = web_async(coroutine)

        @functools.wraps(coroutine)
        def run_async_routine(*args, **kwargs):
            # we check if we're an instancemethod of RequestHandler for better
            # intergration
            if len(args) > 0 and isinstance(args[0], RequestHandler):
                CoroutineRunner(web_async_coroutine(*args, **kwargs),
                    args[0], io_loop, callback = callback)
            else:
                CoroutineRunner(coroutine(*args, **kwargs), io_loop=io_loop,
                                callback = callback)

        return run_async_routine

    return asynchronous

asynchronous = make_asynchronous_decorator(None)


def make_async_with_return(ioloop):
    _asynchronous = make_asynchronous_decorator(ioloop)
    def with_callback(func):

        if not isgeneratorfunction(func):
            raise ValueError, "can't async a func with no yield"

        @functools.wraps(func)
        def _with_callback(*args, **kwargs):

            def _partial_call(callback):

                f = _asynchronous(func, callback = callback)
                return f(*args, **kwargs)

            _partial_call.is_callback_wrapper = True
            return _partial_call

        _with_callback.has_callback_wrapper = True
        return _with_callback
    return with_callback

async_return = make_async_with_return(None)
