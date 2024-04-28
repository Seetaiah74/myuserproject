import logging
from django.http import JsonResponse
from django.core.exceptions import ObjectDoesNotExist
from rest_framework import status
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from .serializers import UserSerializer,UserLoginSerializer, MessageSerializer, ChatSerializer
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth import authenticate
from rest_framework.authtoken.models import Token
from .models import CustomUser, Chat, Message
from geopy.distance import geodesic
from datetime import date
import ast
from django.db.models import Max, Prefetch
from django.contrib.auth import get_user_model
from datetime import datetime
from google.cloud import storage
from django.conf import settings

User = get_user_model()

# Initialize storage client using configured credentials
storage_client = storage.Client(credentials=settings.GS_CREDENTIALS)

@api_view(['POST'])
def register_user(request):
    if request.method == 'POST':
        try:
            email = request.data.get('email')
            try:
                existing_user = CustomUser.objects.get(email=email)
                return Response({'message': 'User with this email already exists'},
                                status=status.HTTP_400_BAD_REQUEST)
            except ObjectDoesNotExist:
                pass

            serializer = UserSerializer(data=request.data)
            if serializer.is_valid():
                user = serializer.save()

                #Handle profile pic upload
                # if 'profile_pic' in request.FILES:
                #     user.profile_pic = request.FILES['profile_pic']
                #     user.save()

                 # Handle profile pic upload to GCS
                if 'profile_pic' in request.FILES:
                    image_file = request.FILES['profile_pic']
                    image_url = upload_image_to_gcs(image_file, user.id, storage_client)  # Upload to GCS
                    user.profile_pic = image_url  # Save GCS URL to the profile_pic field
                    user.save()

                return Response({'message': 'User registered successfully', 'result': serializer.data},
                                status=status.HTTP_201_CREATED)
            
            else:
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        
def upload_image_to_gcs(image_file, user_id, storage_client):
    # Instantiate a GCS client
    # client = storage.Client()

    # Define bucket name and file path
    bucket_name = 'media_files_bucket'
    file_path = f'profile_pics/user_{user_id}_{image_file.name}'  # Adjust as needed

    # Get the bucket
    bucket = storage_client.bucket(bucket_name)

    # Create a blob and upload the file
    blob = bucket.blob(file_path)
    blob.upload_from_file(image_file, content_type=image_file.content_type)

    # Generate public URL for the uploaded file
    image_url = f'https://storage.googleapis.com/{bucket_name}/{file_path}'

    return image_url


@api_view(['POST'])
def user_login(request):
    if request.method == 'POST':
        serializer = UserLoginSerializer(data=request.data)
        
        if serializer.is_valid():
            email = serializer.validated_data.get('email')
            password = serializer.validated_data.get('password')
            
            authenticated_user = authenticate(request, email=email, password=password)
            
            if authenticated_user:
                token, _ = Token.objects.get_or_create(user=authenticated_user)
                user_serializer = UserSerializer(authenticated_user)
                return Response({'message': 'User login successful', 'token': token.key,'result': user_serializer.data}, status=status.HTTP_200_OK)
            else:
                return Response({'message': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)
        
        return Response({'message': 'Invalid Credentials'}, status=status.HTTP_400_BAD_REQUEST)
    

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def user_logout(request):
    if request.method == 'POST':
        try:
            #Delete the user's token to logout
            request.user.auth_token.delete()
            return Response({'message': 'Successfully logged out'}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def send_message(request, recipient_id):
    try:
        recipient = CustomUser.objects.get(id=recipient_id)
        sender = request.user
        content = request.data.get('content')

        #Check if a chat already exists between the sender and recipient
        chat = Chat.objects.filter(participants=sender).filter(participants=recipient).first()

        if not chat:
            # If no chat exists, create a new one
            chat = Chat.objects.create()
            chat.participants.add(sender, recipient)

        #chat, created = Chat.objects.get_or_create()
        #chat.participants.add(sender, recipient)

        message = Message(chat=chat, sender=sender, recipient=recipient, content=content)
        message.save()

        serializer = MessageSerializer(message)

        return Response(serializer.data, status=status.HTTP_201_CREATED)
    except CustomUser.DoesNotExist:
        return Response({'error': 'Recipient not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        

# @api_view(['POST'])
# @permission_classes([IsAuthenticated])
# def update_profile(request):
#     if request.method == 'POST':
#         user = request.user
#         data = request.data.copy()  # Make a copy to avoid modifying the original data
        
#         # Update the user's profile using the serializer
#         serializer = UserSerializer(user, data=data, partial=True)
#         if serializer.is_valid():
#             serializer.update(user, data)  # Using the custom update method
            
#              # Handle profile pic update to GCS
#             if 'profile_pic' in request.FILES:
#                 image_file = request.FILES['profile_pic']
#                 image_url = upload_image_to_gcs(image_file, user.id, storage_client)  # Upload to GCS
#                 user.profile_pic = image_url  # Save GCS URL to the profile_pic field
#                 user.save()
            
#             return Response({'message': 'Profile updated successfully', 'result': serializer.data}, status=status.HTTP_200_OK)
#         else:
#             return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
    
logger = logging.getLogger(__name__)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def update_profile(request):
    user = request.user
    data = request.data.copy()  # Make a copy to avoid modifying the original data

    try:
        # Check if a new profile picture is provided
        new_profile_pic = request.FILES.get('profile_pic')
        if new_profile_pic:
            # Define the file path for GCS with user-specific prefix
            file_path = f'profile_pics/user_{user.id}_{new_profile_pic.name}'

            # Get the GCS client from settings
            # storage_client = settings.storage_client
            storage_client = storage.Client(credentials=settings.GS_CREDENTIALS)
            if not storage_client:
                raise Exception('GCS storage client is not configured.')

            # Define the GCS bucket name
            bucket_name = 'media_files_bucket'

            # Get the GCS bucket
            bucket = storage_client.bucket(bucket_name)

            # Create a blob with the specified file path
            blob = bucket.blob(file_path)

            # Upload the file to GCS
            blob.upload_from_file(new_profile_pic, content_type=new_profile_pic.content_type)
            logger.info(f'Uploaded new profile picture to GCS: {file_path}')

            # Generate the public URL for the uploaded file
            image_url = f'https://storage.googleapis.com/{bucket_name}/{file_path}'

            # Update the profile_pic field in user data to the GCS URL
            #data['profile_pic'] = image_url
            user.profile_pic = image_url

        # Update the user's profile using the serializer
        serializer = UserSerializer(user, data=data, partial=True)
        if serializer.is_valid():
            serializer.save()  # Save the updated data
            return Response({'message': 'Profile updated successfully', 'result': serializer.data}, status=status.HTTP_200_OK)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    except Exception as e:
        logger.error(f'Error updating profile: {str(e)}')
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def retrieve_users_within_radius(request):
        
    user = request.user
    latitude = user.latitude
    longitude = user.longitude

    # Print the values to check if they are None
    #print("Latitude:", latitude)
    #print("Longitude:", longitude)
    
    # Get radius_km from request data
    radius_km = float(request.GET.get('radius'))
    
    if radius_km is None:
        return Response({'error': 'Radius must be provided.'}, status=status.HTTP_400_BAD_REQUEST)



      # Check if latitude, longitude, and radius_km are provided
    if not latitude or not longitude or not radius_km:
        return Response({'error': "latitude, longitude, and radius must be provided."},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    try:
        # Convert latitude, longitude, and radius_km to float
        latitude = float(latitude)
        longitude = float(longitude)
        radius_km = float(radius_km)
    except ValueError:
        return Response({'error': "Latitude, longitude, and radius must be valid numbers."},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # Get users within the specified radius
    users_within_radius = get_users_within_radius(latitude, longitude, radius_km)

    # Get interests of the authenticated user
    user_interests = ast.literal_eval(user.interests)

    # Get all users from the database
    all_users = CustomUser.objects.exclude(id=user.id)

    # Serialize user data
    user_alldata = []
    for user in all_users:
        # Check if the other user has a token (i.e., is logged in)
        has_token = Token.objects.filter(user=user).exists()

        # Calculate age from birthday
        age = calculate_age(user.birthday)

        # Get interests of the other user and parse the string into a list
        other_user_interests_str = user.interests
        other_user_interests = ast.literal_eval(other_user_interests_str)

        # Calculate interest match percentage
        match_percentage = calculate_interest_match(user_interests, other_user_interests)

        user_alldata.append({
            'id': user.id,
            'profile_pic': user.profile_pic.url if user.profile_pic else None,
            'username': user.username,
            'age': age,
            'has_token': has_token,
            'match_percentage': match_percentage,  # Interest match percentage
            # Add other user details as needed
        })
    
    # Sort user data based on match percentage (highest percentage first)
    user_alldata_sorted = sorted(user_alldata, key=lambda x: x['match_percentage'], reverse=True)
    

    # Serialize user data
    user_data = []
    for user in users_within_radius:
        if user != request.user:

            # Check if the user has a token (i.e., is logged in)
            has_token = Token.objects.filter(user=user).exists()

            # Calculate age from birthday
            age = calculate_age(user.birthday)

            # Get interests of the other user and parse the string into a list
            other_user_interests_str = user.interests
            other_user_interests = ast.literal_eval(other_user_interests_str)

            # Calculate interest match percentage
            match_percentage = calculate_interest_match(user_interests, other_user_interests)


            user_data.append({
                'id': user.id,
                'profile_pic': user.profile_pic.url if user.profile_pic else None,
                'username': user.username,
                'age': age,
                'has_token': has_token,
                'match_percentage': match_percentage,  # Interest match percentage
                # Add other user details as needed
            })

             # Sort user data based on match percentage (highest percentage first)
    user_data_sorted = sorted(user_data, key=lambda x: x['match_percentage'], reverse=True)


    return Response({'radius users': user_data_sorted, 'all users': user_alldata_sorted}, status=status.HTTP_200_OK)

def calculate_interest_match(user_interests, other_user_interests):
    # Convert user interests to a set for faster lookup
    user_interests_set = set(user_interests)
    
    # Count the number of matching interests
    matching_interests_count = sum(1 for interest in other_user_interests if interest in user_interests_set)
    
    # Calculate match percentage
    total_interests_count = len(user_interests)
    match_percentage = (matching_interests_count / total_interests_count) * 100 if total_interests_count > 0 else 0
    
    return match_percentage

def calculate_age(birthday):
    if birthday:
        today = date.today()
        age = today.year - birthday.year - ((today.month, today.day) < (birthday.month, birthday.day))
        return age
    else:
        return None

def get_users_within_radius(latitude, longitude, radius_km):
    # Query all users
    all_users = CustomUser.objects.all()

    # List to store users within the radius
    users_within_radius = []

    # Create a reference point for the given latitude and longitude
    reference_point = (latitude, longitude)

    # Iterate over all users
    for user in all_users:
        # Calculate the distance between the user's location and the reference point
        user_location = (user.latitude, user.longitude)
        distance = geodesic(reference_point, user_location).kilometers

        # Check if the distance is within the specified radius
        if distance <= radius_km:
            users_within_radius.append(user)

    return users_within_radius


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_chat_messages(request, chat_id):
    try:
        chat = Chat.objects.get(id=chat_id)
        messages = Message.objects.filter(chat=chat).order_by('timestamp')

        serializer = MessageSerializer(messages, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    except Chat.DoesNotExist:
        return Response({'error': 'Chat not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_latest_messages(request, chat_id, last_timestamp):
    try:
        chat = Chat.objects.get(id=chat_id)
        #Manually parse the ISO 8601 formatted string
        last_timestamp_datetime = datetime.strptime(last_timestamp, "%Y-%m-%dT%H:%M:%S.%fZ")

        #Get messages newer than the provided timestamp
        messages = Message.objects.filter(chat=chat, timestamp__gt=last_timestamp_datetime).order_by('timestamp')

        serializer = MessageSerializer(messages, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    except Chat.DoesNotExist:
        return Response({'error': 'Chat not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_user_chats(request):
    try:
        user = request.user
        chats = Chat.objects.filter(participants=user)

        
        chat_details = []
        for chat in chats:
            other_participant = chat.participants.exclude(id=user.id).first()
            last_message = chat.message_set.aggregate(last_message_time=Max('timestamp'), last_message=Max('content'))

            chat_data = {
                'id': chat.id,
                'participants': [{
                    'id': other_participant.id,
                    'username': other_participant.username,
                    'profile_pic': other_participant.profile_pic.url if other_participant.profile_pic else None
                }],
                'last_message': last_message['last_message'],
                'last_message_time': last_message['last_message_time'],
                'created_at': chat.created_at
            }

            chat_details.append(chat_data)

        return Response({'total_chat_ids': len(chats), 'chat_details': chat_details}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        