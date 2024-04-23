from django.urls import path
from .views import register_user, user_login, user_logout, send_message, update_profile, retrieve_users_within_radius, get_chat_messages, get_user_chats, get_latest_messages


urlpatterns =[
    path('register/', register_user, name='register'),
    path('login/', user_login, name='login'),
    path('logout/', user_logout, name='logout'),
    path('send-message/<int:recipient_id>/', send_message, name='send_message'),
    path('update/', update_profile, name='update_profile'),
    path('getusers/', retrieve_users_within_radius, name='retrieve_users_within_radius'),
    path('chat-messages/<int:chat_id>/', get_chat_messages, name='chat-messages'),
    path('chat-latest-messages/<int:chat_id>/<str:last_timestamp>/', get_latest_messages, name='chat-latest-messages'),
    path('user-chats/', get_user_chats, name='user-chats'),
]