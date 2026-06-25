from django.db import models
from django.contrib.auth.models import User


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    is_approved = models.BooleanField(default=False)
    requested_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    reminder_email = models.EmailField(blank=True, default='')

    def __str__(self):
        return f"{self.user.username} ({'approved' if self.is_approved else 'pending'})"


class Task(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='tasks')
    title = models.CharField(max_length=300)
    note = models.TextField(blank=True, default='')
    completed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    reminder_at = models.DateTimeField(null=True, blank=True)
    reminder_sent = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title


class UploadedFile(models.Model):
    FILE_TYPES = [
        ('image', 'Image'),
        ('pdf', 'PDF'),
        ('text', 'Text'),
        ('other', 'Other'),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='files')
    name = models.CharField(max_length=255)
    file = models.FileField(upload_to='uploads/%Y/%m/')
    file_type = models.CharField(max_length=10, choices=FILE_TYPES, default='other')
    size = models.PositiveIntegerField(default=0)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return self.name

    def size_display(self):
        if self.size < 1024:
            return f"{self.size} B"
        elif self.size < 1024 * 1024:
            return f"{self.size // 1024} KB"
        return f"{self.size // (1024*1024)} MB"


class RoutineTask(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='routine_tasks')
    title = models.CharField(max_length=300)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    reminder_time = models.TimeField(null=True, blank=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return self.title


class RoutineLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='routine_logs')
    routine_task = models.ForeignKey(RoutineTask, on_delete=models.CASCADE, related_name='logs')
    date = models.DateField()
    completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    reminder_sent = models.BooleanField(default=False)

    class Meta:
        unique_together = ('routine_task', 'date')
        ordering = ['-date']

    def __str__(self):
        return f"{self.routine_task.title} - {self.date}"


class TransactionCategory(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='transaction_categories')
    name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        unique_together = ('user', 'name')

    def __str__(self):
        return self.name


class Transaction(models.Model):
    TYPE_CHOICES = [
        ('income', 'Income'),
        ('expense', 'Expense'),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='transactions')
    category = models.ForeignKey(
        TransactionCategory, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='transactions'
    )
    title = models.CharField(max_length=300)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    transaction_type = models.CharField(max_length=10, choices=TYPE_CHOICES, default='expense')
    note = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} - {self.amount}"


class TextNote(models.Model):
    """A plain text note created/edited directly in the app (not an uploaded
    file), shown alongside uploaded files on the Files page."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='text_notes')
    heading = models.CharField(max_length=255)
    body = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return self.heading
