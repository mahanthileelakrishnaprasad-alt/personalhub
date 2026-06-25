from django.contrib import admin
from .models import UserProfile, Task, UploadedFile, RoutineTask, RoutineLog, TransactionCategory, Transaction, TextNote
admin.site.register([UserProfile, Task, UploadedFile, RoutineTask, RoutineLog, TransactionCategory, Transaction, TextNote])
