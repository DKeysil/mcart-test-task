from aiohttp import web

routes = web.RouteTableDef()


@routes.get('/api/currency_list')
async def get_currency_list(request: web.Request):
    """
    :param request:
    :return: Список валют, который содержит все доступные валюты в формате [('RUB', 'Рубль'), ..]
    """
    return web.json_response()


@routes.get('/api/exchange_rate_difference')
async def get_exchange_rate_difference(request: web.Request):
    """
    Возвращает разницу курса относительно рубля между двумя датами за выбранную дату
    GET параметры: символьный код продукта, дата 1, дата 2
    :param request:
    :return: Курс за первую дату, курс за вторую дату и разницу между ними
    """
    return web.json_response()


app = web.Application()
app.add_routes(routes)

web.run_app(app)
