from rest_framework import serializers
from django.contrib.auth.models import User
from .models import (
    UserProfile, Task, TaskCategory, UploadedFile, FileFolder, NoteFolder,
    RoutineTask, RoutineLog, TransactionCategory, Transaction, TextNote,
)


class UserProfileSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    email = serializers.CharField(source='user.email', read_only=True)

    class Meta:
        model = UserProfile
        fields = ['id', 'is_approved', 'reminder_email', 'requested_at', 'approved_at',
                  'avatar_url', 'bio', 'theme', 'username', 'email']
        read_only_fields = ['id', 'is_approved', 'requested_at', 'approved_at', 'username', 'email']


class UserSerializer(serializers.ModelSerializer):
    profile = UserProfileSerializer(read_only=True)

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'is_superuser', 'is_active',
                  'date_joined', 'profile']


class RegisterSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(write_only=True, min_length=8)
    password2 = serializers.CharField(write_only=True)

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("Username already taken.")
        return value

    def validate(self, data):
        if data['password'] != data['password2']:
            raise serializers.ValidationError({"password2": "Passwords do not match."})
        return data

    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data['username'],
            password=validated_data['password'],
        )
        UserProfile.objects.create(user=user, is_approved=False)
        return user


class TaskCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = TaskCategory
        fields = ['id', 'name']


class TaskSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True, default=None)

    class Meta:
        model = Task
        fields = ['id', 'title', 'note', 'completed', 'created_at',
                  'completed_at', 'reminder_at', 'reminder_sent', 'category', 'category_name',
                  'position', 'due_date', 'parent', 'is_recurring', 'recur_days']
        read_only_fields = ['id', 'created_at', 'completed_at', 'reminder_sent', 'category_name']

    def validate_reminder_at(self, value):
        # Make naive datetimes timezone-aware (fixes the known bug from old code)
        from django.utils import timezone
        if value is not None and timezone.is_naive(value):
            value = timezone.make_aware(value)
        return value


class FileFolderSerializer(serializers.ModelSerializer):
    file_count = serializers.SerializerMethodField()
    class Meta:
        model = FileFolder
        fields = ['id', 'name', 'created_at', 'file_count']
    def get_file_count(self, obj):
        return obj.files.count()


class NoteFolderSerializer(serializers.ModelSerializer):
    note_count = serializers.SerializerMethodField()
    class Meta:
        model = NoteFolder
        fields = ['id', 'name', 'created_at', 'note_count']
    def get_note_count(self, obj):
        return obj.notes.count()


class UploadedFileSerializer(serializers.ModelSerializer):
    size_display = serializers.CharField(read_only=True)
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = UploadedFile
        fields = ['id', 'name', 'file', 'file_type', 'size', 'size_display',
                  'uploaded_at', 'file_url']
        read_only_fields = ['id', 'uploaded_at', 'size', 'file_type', 'size_display']
        extra_kwargs = {'file': {'write_only': True}}

    def get_file_url(self, obj):
        # 1. New uploads: cloudinary_url field has the direct URL
        if getattr(obj, 'cloudinary_url', ''):
            return obj.cloudinary_url
        # 2. Old uploads via django-cloudinary-storage
        if obj.file:
            try:
                url = obj.file.url
                if url.startswith('http'):
                    return url
                # Local storage fallback: strip double media/ prefix
                from django.conf import settings
                name = obj.file.name or ''
                if name.startswith('media/'):
                    name = name[len('media/'):]
                return settings.MEDIA_URL + name
            except Exception:
                return None
        return None


class RoutineTaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = RoutineTask
        fields = ['id', 'title', 'is_active', 'reminder_time', 'created_at', 'active_days', 'position']
        read_only_fields = ['id', 'created_at']


class RoutineLogSerializer(serializers.ModelSerializer):
    routine_task_title = serializers.CharField(source='routine_task.title', read_only=True)

    class Meta:
        model = RoutineLog
        fields = ['id', 'routine_task', 'routine_task_title', 'date',
                  'completed', 'completed_at', 'reminder_sent']
        read_only_fields = ['id', 'date', 'completed_at', 'reminder_sent']


class TransactionCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = TransactionCategory
        fields = ['id', 'name', 'created_at']
        read_only_fields = ['id', 'created_at']


class TransactionSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True, default=None)

    class Meta:
        model = Transaction
        fields = ['id', 'title', 'amount', 'transaction_type', 'note',
                  'category', 'category_name', 'created_at']
        read_only_fields = ['id', 'created_at']


class TextNoteSerializer(serializers.ModelSerializer):
    folder_name = serializers.CharField(source='folder.name', read_only=True, default=None)
    class Meta:
        model = TextNote
        fields = ['id', 'heading', 'body', 'created_at', 'updated_at', 'folder', 'folder_name']
        read_only_fields = ['id', 'created_at', 'updated_at', 'folder_name']