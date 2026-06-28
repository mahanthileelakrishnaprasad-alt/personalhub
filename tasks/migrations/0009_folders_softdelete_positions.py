from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0008_task_position'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # FileFolder
        migrations.CreateModel(
            name='FileFolder',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=200)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='file_folders', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['name'], 'unique_together': {('user', 'name')}},
        ),
        # NoteFolder
        migrations.CreateModel(
            name='NoteFolder',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=200)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='note_folders', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['name'], 'unique_together': {('user', 'name')}},
        ),
        # folder FK on UploadedFile
        migrations.AddField(
            model_name='uploadedfile',
            name='folder',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='files', to='tasks.filefolder'),
        ),
        # folder FK on TextNote
        migrations.AddField(
            model_name='textnote',
            name='folder',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='notes', to='tasks.notefolder'),
        ),
        # Soft-delete on Transaction
        migrations.AddField(
            model_name='transaction',
            name='is_deleted',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='transaction',
            name='deleted_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        # position on RoutineTask
        migrations.AddField(
            model_name='routinetask',
            name='position',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AlterModelOptions(
            name='routinetask',
            options={'ordering': ['position', 'created_at']},
        ),
    ]