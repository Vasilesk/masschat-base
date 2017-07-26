CREATE TABLE scopes (
    id serial PRIMARY KEY,
    token text,
    c_token text,
    title text,
    link text
);

CREATE TABLE states (
    id serial PRIMARY KEY,
    title text
);

CREATE TABLE users (
    id serial PRIMARY KEY,
    scope_id integer REFERENCES scopes (id) ON DELETE CASCADE,
    in_scope_id integer,
    state_id integer REFERENCES states (id) ON DELETE CASCADE,
    UNIQUE (scope_id, in_scope_id)
);

CREATE TABLE searches (
    id serial PRIMARY KEY,
    user_id integer REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE chats (
    id serial PRIMARY KEY
);

CREATE TABLE chat_users (
    chat_id integer REFERENCES chats (id) ON DELETE CASCADE,
    user_id integer REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE active_chats (
    chat_id integer REFERENCES chats (id) ON DELETE CASCADE
);
