from rest_framework import serializers
from .models import CallRecording, UserDetail
class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)


class CallRecordingSerializer(serializers.ModelSerializer):
    class Meta:
        model = CallRecording
        fields = ['id', 'filename', 'original_filename', 'file_size', 'upload_time', 
                 'recorded_time', 'duration', 'phone_number', 'call_type', 'is_processed']
        read_only_fields = ['id', 'upload_time', 'is_processed']

class UserRecordingUploadSerializer(serializers.Serializer):
    recording = serializers.FileField()
    filename = serializers.CharField(max_length=255)
    file_size = serializers.IntegerField()
    upload_time = serializers.DateTimeField(required=False)
    recorded_time = serializers.DateTimeField(required=False)
    phone_number = serializers.CharField(max_length=20, required=False)
    call_type = serializers.CharField(max_length=10, required=False)


  
