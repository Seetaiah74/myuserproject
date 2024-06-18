import json

from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from django.db import close_old_connections

from .models import Message, Chat

User = get_user_model()


class ChatConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        self.chat_id = self.scope['url_route']['kwargs']['chat_id']
        self.receiver_id = self.scope['url_route']['kwargs']['receiver_id']
        self.room_group_name = f'chat_{self.chat_id}'

        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        token = self.scope['query_string'].decode('utf-8').split('=')[1]
        user = await self.authenticate_with_token(token)

        if user is not None and user.is_authenticated:
            close_old_connections()

            self.scope['user'] = user
            await self.accept()
        else:
            await self.close

    
    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        data = json.loads(text_data)

        chat = await database_sync_to_async(Chat.objects.get)(id=self.chat_id)

        sender_id = self.scope['user'].id
        receiver_id = self.receiver_id

        content = data['message']
        message = Message(chat=chat, sender_id=sender_id, recipient_id=receiver_id, content=content)
        await database_sync_to_async(message.save)()

        username = self.scope['user'].username

        formatted_message = f'{username}: {content}'

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'chat_message',
                'message': formatted_message,
            }
        )

        recipient = await database_sync_to_async(User.objects.get)(id=receiver_id)
        if recipient.fcm_token:
            await self.send_fcm_notification(recipient.fcm_token, formatted_message)


    async def chat_message(self, event):
        message = event['message']

        await self.send(text_data=json.dumps({
            'message': message,
        }))

    async def authenticate_with_token(self, token):
        try:
            user = await self.get_user_by_token(token)
            return user
        except User.DoesNotExist:
            return None
        
    
    async def get_user_by_token(self, token):
        try:
            return await database_sync_to_async(User.objects.get)(
                auth_token=token)
        except User.DoesNotExist:
            return None

    