from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/chat/(?P<receiver_id>\w+)/$', consumers.ChatConsumer.as_asgi()),  # Without chat_id
    re_path(r'ws/chat/(?P<chat_id>\w+)/(?P<receiver_id>\w+)/$', consumers.ChatConsumer.as_asgi()),  # With chat_id
]