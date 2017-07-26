#! /usr/bin/python3
# -*- coding: utf8 -*-

import re

from vk.exceptions import VkAPIError

import psycopg2
import requests
import json

from vkchat_settings import ru_phrases
from tools import safe_call

def on_conformation(scope_id, conn):
    cursor = conn.cursor()
    query = 'SELECT c_token FROM scopes WHERE id=%s LIMIT 1'
    cursor.execute(query, (scope_id, ))

    result = cursor.fetchone()
    if result is None:
        key = 'Send confirmation_token to Vk Mass Chat administrator'
    else:
        key = result[0]
    return key

class Vkchat:
    def __init__(self, scope_id, in_scope_id, secret, conn, api):
        self.scope_id = scope_id
        self.in_scope_id = in_scope_id
        self.conn = conn
        self.cursor = self.conn.cursor()

        query = 'SELECT token, c_token, link FROM scopes WHERE id=%s AND c_token=%s LIMIT 1'
        self.cursor.execute(query, (scope_id, secret))
        if self.cursor.rowcount == 1:
            self.token, self.c_token, self.group_link = self.cursor.fetchone()
        else:
            raise Exception('fake request url')

        self.api = api

        self.is_new = self.set_user_id_and_state()

        self.ru_phrases = ru_phrases

    def set_user_id_and_state(self):
        query = 'SELECT id, state_id FROM users WHERE scope_id=%s AND in_scope_id=%s'
        self.cursor.execute(query, (self.scope_id, self.in_scope_id))
        result = self.cursor.fetchone()
        is_new = result is None
        if is_new:
            query = 'INSERT INTO users (scope_id, in_scope_id, state_id) SELECT %s,%s,%s WHERE NOT EXISTS (SELECT id FROM users WHERE scope_id=%s AND in_scope_id=%s) RETURNING id'

            self.cursor.execute(query, (self.scope_id, self.in_scope_id, 1, self.scope_id, self.in_scope_id))
            result_new_user = self.cursor.fetchone()
            if result_new_user is not None:
                self.user_id = result_new_user[0]
                self.state_id = 1
                self.conn.commit()
            else:
                query = 'SELECT id, state_id FROM users WHERE scope_id=%s AND in_scope_id=%s'
                self.cursor.execute(query, (self.scope_id, self.in_scope_id))
                self.user_id, self.state_id = self.cursor.fetchone()

        else:
            self.user_id, self.state_id = result

        return is_new

    def on_group_join(self):
        if self.is_new:
            message = self.ru_phrases['join_new']
        else:
            message = self.ru_phrases['join_seen']

        try:
            safe_call(
                self.api.messages.send,
                access_token=self.token,
                user_id=self.in_scope_id,
                title=self.ru_phrases['bot_title'],
                message=message
            )
        except VkAPIError as e:
            pass

    def on_message_allow(self):
        if self.is_new:
            message = self.ru_phrases['allow_new']
        else:
            message = self.ru_phrases['allow_seen']

        safe_call(
            self.api.messages.send,
            access_token=self.token,
            user_id=self.in_scope_id,
            title=self.ru_phrases['bot_title'],
            message=message
        )

    def on_message_new(self, income_message):
        if self.state_id == 1:
            self.on_state_1(income_message)
        elif self.state_id == 2:
            self.on_state_2(income_message)
        elif self.state_id == 3:
            self.on_state_3(income_message)
        else:
            self.on_other_states(income_message)


    def on_state_1(self, income_message):
        txt = income_message['body']
        if txt.lower() in ('!', 'чат', '"чат"'):
            companion = self.get_new_companion()
            if not companion:
                message = '{wait_companion}\n{to_stop_search}'.format(**self.ru_phrases)
            else:
                message = '{companion_found}\n{to_stop_chat}'.format(**self.ru_phrases)

                safe_call(
                    self.api.messages.send,
                    access_token=companion[0],
                    user_id=companion[1],
                    title=self.ru_phrases['bot_title'],
                    message=message
                )
        else:
            message = '{to_start_chat}'.format(**self.ru_phrases)

        if self.is_new:
            message += '\n-----\n{new_user_greetings}'.format(**self.ru_phrases)
            if not self.in_public():
                message += '\n{to_save_bot}'.format(**self.ru_phrases)

        safe_call(self.api.messages.send,
            access_token=self.token,
            user_id=str(self.in_scope_id),
            title=self.ru_phrases['bot_title'],
            message=message
        )

    def on_state_2(self, income_message):
        txt = income_message['body']
        if txt.lower() in ('!', 'стоп', '"стоп"'):
            self.stop_search()
            message = '{search_stopped}\n{to_start_search}'.format(**self.ru_phrases)
        else:
            message = '{wait_companion}\n{to_stop_search}'.format(**self.ru_phrases)

        safe_call(
            self.api.messages.send,
            access_token=self.token,
            user_id=self.in_scope_id,
            title=self.ru_phrases['bot_title'],
            message=message
        )

    def on_state_3(self, income_message):
        txt = income_message['body']
        companion = self.get_companion()
        if txt.lower() in ('!', 'стоп', '"стоп"'):
            self.close_chat()

            message = '{companion_left}\n{to_start_search}'.format(**self.ru_phrases)
            safe_call(
                self.api.messages.send,
                access_token=companion[0],
                user_id=str(companion[1]),
                title=self.ru_phrases['bot_title'],
                message=message
            )
            message = '{user_left}\n{to_start_search}'.format(**self.ru_phrases)
            safe_call(
                self.api.messages.send,
                access_token=self.token,
                user_id=self.in_scope_id,
                title=self.ru_phrases['bot_title'],
                message=message
            )
        else:
            safe_call(
                self.api.messages.markAsRead,
                access_token=self.token,
                message_ids = (income_message['id'], ),
                start_message_id = income_message['id']
            )

            data_to_send = {
                'user_id': companion[1],
                'access_token': companion[0]
            }

            data_to_send.update(self.get_redirected_message(income_message, companion[0]))

            safe_call(self.api.messages.send, **data_to_send)

    def on_other_states(self, income_message):
        print('unknown state')

    def get_new_companion(self):
        companion_id = self.fetch_from_searches()
        if companion_id is None:
            self.insert_new_search()
            self.conn.commit()
            result = False
        else:
            query = 'SELECT token, in_scope_id FROM users INNER JOIN scopes ON scope_id=scopes.id WHERE users.id = %s LIMIT 1'
            self.cursor.execute(query, (companion_id, ))
            result = self.cursor.fetchone()

        return result

    def insert_new_search(self):
        query = 'INSERT INTO searches (user_id) VALUES (%s)'
        self.cursor.execute(query, (self.user_id, ))

        query = 'UPDATE users SET state_id=2 WHERE id=%s'
        self.cursor.execute(query, (self.user_id, ))

    def fetch_from_searches(self):
        query = 'LOCK TABLE searches'
        self.cursor.execute(query)

        query = 'SELECT id, user_id FROM searches WHERE user_id != %s LIMIT 1'
        self.cursor.execute(query, (self.user_id, ))
        result = self.cursor.fetchone()

        if result is not None:
            query = 'DELETE FROM searches WHERE id = %s'
            self.cursor.execute(query, (result[0], ))

            query = 'INSERT INTO chats (id) VALUES (DEFAULT) RETURNING id'
            self.cursor.execute(query)
            chat_id = self.cursor.fetchone()[0]

            query = 'INSERT INTO chat_users (chat_id, user_id) VALUES (%s,%s)'
            self.cursor.execute(query, (chat_id, self.user_id))
            query = 'INSERT INTO chat_users (chat_id, user_id) VALUES (%s,%s)'
            self.cursor.execute(query, (chat_id, result[1]))

            query = 'INSERT INTO active_chats (chat_id) VALUES (%s)'
            self.cursor.execute(query, (chat_id, ))

            query = 'UPDATE users SET state_id=3 WHERE id=%s OR id=%s'
            self.cursor.execute(query, (self.user_id, result[1]))

            return result[1]
        else:
            return None

    def in_public(self):
        response = safe_call(
            self.api.groups.isMember,
            access_token=self.token,
            group_id=self.scope_id,
            user_id=self.in_scope_id
        )
        return response == 1

    def get_companion(self):
        chat_id = self.get_chat_id()
        companion_id = self.get_companion_id(chat_id)
        return self.get_companion_by_id(companion_id)

    def stop_search(self):
        query = 'DELETE FROM searches WHERE user_id = %s'
        self.cursor.execute(query, (self.user_id, ))

        query = 'UPDATE users SET state_id=1 WHERE id=%s'
        self.cursor.execute(query, (self.user_id, ))

        self.conn.commit()

    def get_chat_id(self):
        query = 'SELECT active_chats.chat_id FROM active_chats INNER JOIN chat_users ON active_chats.chat_id=chat_users.chat_id WHERE user_id=%s LIMIT 1'
        self.cursor.execute(query, (self.user_id, ))
        chat_id = self.cursor.fetchone()[0]

        return chat_id

    def get_companion_by_id(self, companion_id):
        query = 'SELECT token, in_scope_id FROM users INNER JOIN scopes ON scope_id=scopes.id WHERE users.id = %s LIMIT 1'
        self.cursor.execute(query, (companion_id, ))
        return self.cursor.fetchone()

    def get_companion_id(self, chat_id):
        query = 'SELECT user_id FROM active_chats INNER JOIN chat_users ON active_chats.chat_id=chat_users.chat_id WHERE active_chats.chat_id=%s AND user_id!=%s LIMIT 1'
        self.cursor.execute(query, (chat_id, self.user_id))
        companion_id = self.cursor.fetchone()[0]

        return companion_id

    def close_chat(self):
        chat_id = self.get_chat_id()
        companion_id = self.get_companion_id(chat_id)

        query = 'DELETE FROM active_chats WHERE chat_id=%s'
        self.cursor.execute(query, (chat_id, ))

        query = 'UPDATE users SET state_id=1 WHERE id=%s OR id=%s'
        self.cursor.execute(query, (self.user_id, companion_id))

        self.conn.commit()

    def get_sticker_data(self, attachment):
        if attachment['type'] == 'sticker':
            return attachment['sticker']
        else:
            return None

    def get_link_urls(self, attachments):
        urls = []
        for attachment in attachments:
            if attachment['type'] == 'link':
                url = attachment['link']['url']
                if self.re_product_link.match(url) is None:
                    urls.append(url)

        return urls

    def get_max_photo_key(self, data):
        re_photo = re.compile('photo_(\d+)')
        photos = []
        for key in data:
            match_photo = re_photo.match(key)
            if match_photo:
                photos.append(int(match_photo.group(1)))
        if photos == []:
            return None
        else:
            return 'photo_{}'.format(sorted(photos, reverse=True)[0])

    def attachments_to_attachment(self, attachments):
        out_attachments = []
        t_out_attachment = '{key}{owner_id}_{id}'

        for attachment in attachments:
            key = attachment['type']

            if key == 'link':
                match_product = self.re_product_link.match(attachment['link']['url'])
                if match_product is None:
                    continue
                else:
                    out_attachment = 'market{}_{}_{}'.format(match_product.group(1), match_product.group(2), match_product.group(3))

            else:
                # durty hack. Future api versions would give the possibility to get rid of it
                if key == 'wall':
                    attachment['wall']['owner_id'] = attachment['wall']['to_id']
                # durty hack ends

                out_attachment = t_out_attachment.format(key=key, **attachment[key])
                if 'access_key' in attachment[key]:
                    out_attachment += '_' + attachment[key]['access_key']

            out_attachments.append(out_attachment)

        return out_attachments

    def get_valid_attachments(self, message_id):
        res = safe_call(
                    self.api.messages.getById,
                    access_token=self.token,
                    message_ids=(message_id, )
                )

        return res['items'][0]['attachments']

    def upload_remote_photo(self, url_remote, dist_token):
        def file_by_url(url):
            r = requests.get(url, stream=True)
            if r.status_code == 200:
                r.raw.decode_content = True
                return r.raw

        upload_server = safe_call(
                                self.api.photos.getMessagesUploadServer,
                                access_token=dist_token
                            )
        upload_url = upload_server['upload_url']

        remote_file = file_by_url(url_remote)

        post_fields = {'photo': ('smth.png', remote_file)}

        response = requests.post(upload_url, files=post_fields)
        file_data = json.loads(response.text)
        file_data['access_token'] = dist_token

        photo = safe_call(self.api.photos.saveMessagesPhoto, **file_data)[0]


        return photo

    def get_redirected_message(self, source_message, dist_token):
        message = 'Собеседник: \n{}'.format(source_message['body'])

        message_data = {
            'title': 'От собеседника',
            'message': message
        }

        if 'fwd_messages' in source_message:
            safe_call(
                self.api.messages.send,
                access_token=self.token,
                user_id=self.in_scope_id,
                title=self.ru_phrases['bot_title'],
                message=self.ru_phrases['user_fwd_msg'],
                forward_messages=(source_message['id'], )
            )

        sticker = None
        if 'attachments' in source_message:
            self.re_product_link = re.compile('.+vk\.com\/product(\d+)_(\d+)_([^\?]+).+')
            sticker = self.get_sticker_data(source_message['attachments'][0])
            if sticker is None:
                attachments = self.get_valid_attachments(source_message['id'])

                links = self.get_link_urls(attachments)
                if links != []:
                    message_data['message'] += ''.join(['\nСсылка: ' + link for link in links])

                message_data['attachment'] = self.attachments_to_attachment(attachments)

        if sticker is not None:
            key = self.get_max_photo_key(sticker)
            message_data['message'] = self.ru_phrases['companion_sticker']
            sticker_data = self.upload_remote_photo(sticker[key], dist_token)
            message_data['attachment'] = 'photo{owner_id}_{id}'.format(**sticker_data)

        return message_data
