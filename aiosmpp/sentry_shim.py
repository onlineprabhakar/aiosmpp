import os
import asyncio
from raven_aiohttp import AioHttpTransportBase
from raven.exceptions import APIError, RateLimited
from aiohttp_sentry import SentryMiddleware


class ProxyAioHttpTransportBase(AioHttpTransportBase):
    def __init__(self, *args, proxy: str = None, **kwargs):
        super(ProxyAioHttpTransportBase, self).__init__(*args, **kwargs)

        self.proxy = proxy

    @asyncio.coroutine
    def _do_send(self, url, data, headers, success_cb, failure_cb):
        if self.keepalive:
            session = self._client_session
        else:
            session = self._client_session_factory()

        resp = None

        try:
            resp = yield from session.post(
                url,
                data=data,
                compress=False,
                headers=headers,
                timeout=self.timeout,
                proxy=self.proxy
            )

            code = resp.status
            if code != 200:
                msg = resp.headers.get('x-sentry-error')
                if code == 429:
                    try:
                        retry_after = resp.headers.get('retry-after')
                        retry_after = int(retry_after)
                    except (ValueError, TypeError):
                        retry_after = 0
                    failure_cb(RateLimited(msg, retry_after))
                else:
                    failure_cb(APIError(msg, code))
            else:
                success_cb()
        except asyncio.CancelledError:
            # do not mute asyncio.CancelledError
            raise
        except Exception as exc:
            failure_cb(exc)
        finally:
            if resp is not None:
                resp.release()
            if not self.keepalive:
                yield from session.close()


class ProxyAioHttpTransport(ProxyAioHttpTransportBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._tasks = set()

    def _async_send(self, url, data, headers, success_cb, failure_cb):
        coro = self._do_send(url, data, headers, success_cb, failure_cb)

        task = asyncio.ensure_future(coro, loop=self._loop)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.remove)

    @asyncio.coroutine
    def _close(self):
        yield from asyncio.gather(
            *self._tasks,
            return_exceptions=True,
            loop=self._loop
        )

        assert len(self._tasks) == 0


def proxy_transport_wrapper(*args, **kwargs):
    return ProxyAioHttpTransport(*args, proxy=os.environ.get('SENTRY_PROXY'), **kwargs)


sentry_middleware = SentryMiddleware(sentry_kwargs={
    'transport': proxy_transport_wrapper,
    'enable_breadcrumbs': True,
    'install_logging_hook': False,
})
