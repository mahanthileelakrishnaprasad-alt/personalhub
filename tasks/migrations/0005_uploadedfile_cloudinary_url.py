from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0004_reminders_and_textnotes'),
    ]

    operations = [
        migrations.AddField(
            model_name='uploadedfile',
            name='cloudinary_url',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AlterField(
            model_name='uploadedfile',
            name='file',
            field=models.FileField(blank=True, upload_to='uploads/%Y/%m/'),
        ),
    ]