"""Fail image/CI before an incompatible Kombu crashes every Redis worker."""
from types import SimpleNamespace

import redis
from kombu.transport.redis import Channel


def test_installed_redis_client_is_accepted_by_kombu_transport():
    # Exercise Kombu's real version gate without connecting to the shared Redis
    # server, creating queues or consuming/publishing any task.
    client = Channel._get_client(SimpleNamespace(global_keyprefix=''))
    assert client is redis.Redis
