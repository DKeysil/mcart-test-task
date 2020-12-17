from aiohttp import web, ClientSession
from xml.dom import minidom
import json
from aiohttp_cors import setup as cors_setup, ResourceOptions
from loguru import logger
from datetime import datetime
import aioredis


routes = web.RouteTableDef()
currency_lst = minidom.parse('currency_list.asp')


def currency_dict(doc: minidom.Document) -> dict:
    """
    Обрабатывает XML документ
    :param doc:
    :return:
    """
    items = doc.firstChild.getElementsByTagName('Item')
    dct = {}

    for item in items:
        try:
            _id = item.attributes['ID'].value
            name = item.getElementsByTagName('Name')[0].firstChild.data
            symbol = item.getElementsByTagName('ISO_Char_Code')[0].firstChild.data
            dct.update({symbol: (name, _id)})
        except AttributeError:
            pass

    return dct


def currency_list(curr_dct: dict) -> list:
    lst = []
    for key in curr_dct.keys():
        lst.append([key, curr_dct[key][0]])

    return lst


currency_dct = currency_dict(currency_lst)
currency_lst = currency_list(currency_dct)


def custom_json_dumps(obj):
    return json.dumps(obj, ensure_ascii=False)


@routes.get('/api/currency_list')
async def get_currency_list(request: web.Request):
    """
    :param request:
    :return: Список валют, который содержит все доступные валюты в формате [('RUB', 'Рубль'), ..]
    """
    logger.info(request)
    return web.json_response(currency_lst, dumps=custom_json_dumps, status=200)


def currency_processing(doc: minidom.Document) -> (str, str):
    """
    Обрабатывает полученные данные
    :param doc:
    :return: Стоимость для первой даты, стоимость для второй даты, разница между второй и первой
    """
    first = doc.firstChild.firstChild.getElementsByTagName('Value')[0].firstChild.data
    last = doc.lastChild.lastChild.getElementsByTagName('Value')[0].firstChild.data
    # Деньги надо обрабатывать в минимальной единице (копейки), а не переводить во float, но я этого тут не делал,
    # так как сайт ЦБ предоставляет и так округленные данные

    return first, last


@routes.get('/api/exchange_rate_difference')
async def get_exchange_rate_difference(request: web.Request):
    """
    Возвращает разницу курса относительно рубля между двумя датами за выбранную дату
    GET параметры: символьный код продукта, дата 1, дата 2
    Например: api/exchange_rate_difference?symb=BYN&date_req1=2020-07-12&date_req2=2020-07-15
    :param request:
    :return: Курс за первую дату, курс за вторую дату и разницу между ними
    """
    logger.info(request)
    args = request.query
    logger.info(args)
    try:
        title = currency_dct.get(args.get("symb"))[0]
        currency_id = currency_dct.get(args.get("symb"))[1]
    except TypeError:
        return web.json_response({'error': 'Exchange rate not found'}, status=404)
    try:
        date_req1 = args.get("date_req1")
        date_req1 = datetime.strptime(date_req1, '%Y-%m-%d').strftime('%d/%m/%Y')
        date_req2 = args.get("date_req2")
        date_req2 = datetime.strptime(date_req2, '%Y-%m-%d').strftime('%d/%m/%Y')
    except ValueError:
        return web.json_response({'error': 'Error in parameters'}, status=422)
    exchange_api_link = 'http://www.cbr.ru/scripts/XML_dynamic.asp?' \
                        f'date_req1={date_req1}&' \
                        f'date_req2={date_req2}&' \
                        f'VAL_NM_RQ={currency_id}'

    redis: aioredis.Redis = request.app['redis_pool']
    first, last = None, None

    if exchange_dict := await redis.hgetall(currency_id, encoding='utf-8'):
        first = exchange_dict.get(date_req1)
        last = exchange_dict.get(date_req2)
    if first is None or last is None:
        async with ClientSession() as session:
            async with session.get(exchange_api_link) as resp:
                # Get exchange rates
                result = await resp.text()

        doc = minidom.parseString(result)
        try:
            val_curs = doc.firstChild.firstChild.data
            if val_curs == "Error in parameters":
                return web.json_response({'error': 'Error in parameters'}, status=422)
        except AttributeError:
            pass

        try:
            first, last = currency_processing(doc)
        except AttributeError:
            return web.json_response({'error': 'Error in parameters'}, status=422)
        await redis.hset(currency_id, date_req1, first)
        await redis.hset(currency_id, date_req2, last)

    first = float(first.replace(',', '.'))
    last = float(last.replace(',', '.'))

    jsn = {
        'title': title,
        'first_exchange_rate': first,
        'second_exchange_rate': last,
        'difference': last - first
    }

    return web.json_response(jsn, dumps=custom_json_dumps, status=200)


async def init():
    app = web.Application()
    app.add_routes(routes)

    cors = cors_setup(
        app,
        defaults={
            "*": ResourceOptions(
                allow_credentials=True, expose_headers="*", allow_headers="*",
            )
        },
    )

    for route in list(app.router.routes()):
        cors.add(route)

    redis_pool = await aioredis.create_redis_pool('redis://localhost')
    app['redis_pool'] = redis_pool

    return app


web.run_app(init())
