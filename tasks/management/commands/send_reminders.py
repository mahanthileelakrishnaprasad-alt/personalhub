"""
Sends due email reminders for Tasks and RoutineTasks via Brevo API.
Designed to run every 30 minutes via cron — uses a ±20 min window
so no reminder is missed even if cron fires slightly late.

Usage:
    python manage.py send_reminders
"""
import urllib.request
import urllib.error
import json
import os
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import date, timedelta
from tasks.models import Task, RoutineTask, RoutineLog, UserProfile
from django.db import models

BREVO_API_KEY = os.environ.get('BREVO_API_KEY', '')
FROM_EMAIL    = os.environ.get('FROM_EMAIL', 'mahanthileelakrishnaprasad@gmail.com')


def _send_via_brevo(to_email, subject, body):
    payload = json.dumps({
        'sender': {'name': 'PersonalHub', 'email': FROM_EMAIL},
        'to': [{'email': to_email}],
        'subject': subject,
        'textContent': body,
    }).encode('utf-8')
    req = urllib.request.Request(
        'https://api.brevo.com/v3/smtp/email',
        data=payload,
        headers={'api-key': BREVO_API_KEY, 'Content-Type': 'application/json', 'Accept': 'application/json'},
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise Exception(f"Brevo {e.code}: {e.read().decode('utf-8')}")


class Command(BaseCommand):
    help = "Send due email reminders. Run every 30 min via cron."

    def handle(self, *args, **options):
        if not BREVO_API_KEY:
            self.stdout.write(self.style.WARNING("BREVO_API_KEY not set — skipping."))
            return

        now = timezone.now()
        today = date.today()
        sent_count = 0

        # ── One-off task reminders ────────────────────────────────────────
        due_tasks = Task.objects.filter(
            completed=False,
            reminder_sent=False,
            reminder_at__isnull=False,
            reminder_at__lte=now,
        ).select_related('user')

        for task in due_tasks:
            email = self._email_for(task.user)
            if not email:
                task.reminder_sent = True
                task.save(update_fields=['reminder_sent'])
                continue
            try:
                _send_via_brevo(
                    to_email=email,
                    subject=f"⏰ Reminder: {task.title}",
                    body=f'Your task "{task.title}" is due now.'
                         + (f'\n\nNote: {task.note}' if task.note else '')
                         + '\n\n— PersonalHub',
                )
                task.reminder_sent = True
                task.save(update_fields=['reminder_sent'])
                sent_count += 1
                self.stdout.write(f"Sent task reminder: '{task.title}' → {email}")
            except Exception as e:
                self.stderr.write(f"Task reminder failed {task.pk}: {e}")

        # ── Daily routine reminders ───────────────────────────────────────
        # Use ±20 min window so a cron running every 30 min never misses.
        # Store reminder_time as HH:MM in TIME field — compare against
        # current LOCAL time in IST (UTC+5:30).
        # timezone.now() is UTC — convert to IST before comparing.
        from datetime import datetime as _dt
        import pytz
        try:
            IST = pytz.timezone('Asia/Kolkata')
            now_ist = now.astimezone(IST)
        except Exception:
            now_ist = now  # fallback if pytz not available

        window_start = (now_ist - timedelta(minutes=20)).time().replace(second=0, microsecond=0)
        window_end   = (now_ist + timedelta(minutes=20)).time().replace(second=0, microsecond=0)

        self.stdout.write(f"Routine reminder window: {window_start} – {window_end} IST")

        # Handle midnight wraparound
        if window_start <= window_end:
            due_routines = RoutineTask.objects.filter(
                is_active=True,
                reminder_time__isnull=False,
                reminder_time__gte=window_start,
                reminder_time__lte=window_end,
            ).select_related('user')
        else:
            due_routines = RoutineTask.objects.filter(
                is_active=True,
                reminder_time__isnull=False,
            ).filter(
                models.Q(reminder_time__gte=window_start) |
                models.Q(reminder_time__lte=window_end)
            ).select_related('user')

        for routine in due_routines:
            today_bit = 1 << today.weekday()
            if not (routine.active_days & today_bit):
                continue
            log, _ = RoutineLog.objects.get_or_create(
                routine_task=routine, date=today, defaults={'user': routine.user}
            )
            if log.completed or log.reminder_sent:
                continue
            email = self._email_for(routine.user)
            if not email:
                log.reminder_sent = True
                log.save(update_fields=['reminder_sent'])
                continue
            try:
                _send_via_brevo(
                    to_email=email,
                    subject=f"⏰ Daily routine reminder: {routine.title}",
                    body=f'Time for your daily routine: "{routine.title}".\n\n'
                         f"Open PersonalHub to tick it off.\n\n— PersonalHub",
                )
                log.reminder_sent = True
                log.save(update_fields=['reminder_sent'])
                sent_count += 1
                self.stdout.write(f"Sent routine reminder: '{routine.title}' → {email}")
            except Exception as e:
                self.stderr.write(f"Routine reminder failed {routine.pk}: {e}")

        self.stdout.write(self.style.SUCCESS(f"Done. {sent_count} reminder(s) sent."))

    def _email_for(self, user):
        try:
            p = user.profile
            return p.reminder_email if p and p.reminder_email else ''
        except Exception:
            return ''