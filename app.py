#! /usr/bin/python3
# -*- coding: utf8 -*-
import traceback

from flask import Flask, request, json
application = Flask(__name__)

from tools import get_api, Benchmark

from vkchat import Vkchat
from vkchat import on_conformation as vkchat_conformation
import vkchat_settings

import psycopg2

api = get_api(v=5.65)
data_types_accepted = (
    'message_new',
    'group_join',
    'message_allow'
)

@application.route('/common/<path:secret>', methods=['POST'])
def c_common(secret):
    benchmark = Benchmark(request.url)
    global api
    global data_types_accepted
    conn_vkchat = psycopg2.connect(**vkchat_settings.db_config)
    data = json.loads(request.data)

    if 'type' not in data.keys():
        return 'not vk'

    elif data['type'] == 'confirmation':
        return vkchat_conformation(data['group_id'], conn_vkchat)

    elif data['type'] in data_types_accepted:
        group_id = data['group_id']
        user_id = data['object']['user_id']

        try:
            processor = Vkchat(group_id, user_id, secret, conn_vkchat, api)

            if data['type'] == 'message_new':
                processor.on_message_new(data['object'])

            elif data['type'] == 'group_join':
                processor.on_group_join()

            elif data['type'] == 'message_allow':
                processor.on_message_allow()

        except Exception as e:
            print('-----')
            print('Data:')
            print(data)
            print('Exception:')
            print(e)
            traceback.print_tb(e.__traceback__)
            print('-----')

    print(benchmark.result())
    return 'ok'
