#! /usr/bin/python3
# -*- coding: utf-8 -*-

import datetime
from time import sleep, clock
import vk
from vk.exceptions import VkAPIError

class Benchmark:
    def __init__(self, path):
        self.start = clock()
        self.date = datetime.datetime.now()
        self.path = path

    def result(self):
        benchmark = '[{}] {}s taken on {}'.format(
            self.date,
            '%.6f' % (clock() - self.start),
            self.path
        )

        return benchmark

def safe_call(method, *data_pos, **data_dict):
    def safe_call_1(method, delay, *data_pos, **data_dict):
        try:
            return None, method(*data_pos, **data_dict)
        except VkAPIError as e:
            if e.error_data['error_code'] in (9, 901, 5):
                raise e
                # return e, {'error': e.error_data['error_code']}
            else:
                sleep(delay)
                return e, None
        except Exception as e:
            sleep(delay)
            return e, None

    delay = 0.3
    e, result = safe_call_1(method, delay, *data_pos, **data_dict)
    while (delay < 1.1) and result is None:
        delay += 0.3
        e, result = safe_call_1(method, delay, *data_pos, **data_dict)

    if result is None:
        raise e

    return result

def get_api(**data_dict):
    session = vk.Session()
    api = vk.API(session, **data_dict)
    return api
