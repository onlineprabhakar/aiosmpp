"""
Simple hack server to print out POST vars
"""
import sys

from aiohttp import web


class WebHandler(object):
    def app(self) -> web.Application:
        _app = web.Application()

        _app.add_routes((
            web.post('/sms/mo', self.handle_mo),
        ))

        return _app

    # Legacy send
    async def handle_mo(self, request: web.Request) -> web.Response:
        # Parse / Validate form data
        try:
            form_data = await request.post()
            print(form_data)
        except Exception:
            try:
                form_data = await request.post()
                print(form_data)
            except Exception:
                print('Unknown')

        return web.Response(text='ok', status=200)


def app(argv: list = None) -> web.Application:
    return WebHandler().app()


if __name__ == '__main__':
    web.run_app(app(sys.argv), port=8083)
