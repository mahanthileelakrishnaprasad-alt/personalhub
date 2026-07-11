"""
Sends due email reminders for Tasks and RoutineTasks.
Run every 30 minutes via cron.

Debug: call /api/cron/send-reminders/?key=SECRET&debug=1 to see what would fire.
"""
import urllib.request
import urllib.error
import json
import os
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import date, timedelta, datetime, time as dtime
from tasks.models import Task, RoutineTask, RoutineLog, UserProfile
from django.db import models

BREVO_API_KEY = os.environ.get('BREVO_API_KEY', '')
FROM_EMAIL    = os.environ.get('FROM_EMAIL', 'mahanthileelakrishnaprasad@gmail.com')


def get_ist_now():
    """Return current datetime in IST (UTC+5:30) using stdlib only — no pytz needed."""
    # Try zoneinfo first (Python 3.9+)
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo('Asia/Kolkata'))
    except ImportError:
        pass
    # Try pytz
    try:
        import pytz
        return datetime.now(pytz.timezone('Asia/Kolkata'))
    except ImportError:
        pass
    # Manual fallback: UTC + 5:30
    from datetime import timezone as _tz
    utc_now = datetime.now(_tz.utc)
    ist_offset = timedelta(hours=5, minutes=30)
    return utc_now + ist_offset


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
        headers={
            'api-key': BREVO_API_KEY,
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        },
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise Exception(f"Brevo {e.code}: {e.read().decode('utf-8')}")


class Command(BaseCommand):
    help = "Send due email reminders. Run every 30 min via cron."

    def add_arguments(self, parser):
        parser.add_argument('--debug', action='store_true',
                            help='Print what would fire without actually sending')
        parser.add_argument('--force-time', type=str, default='',
                            help='Override current IST time e.g. 17:00 for testing')

    def handle(self, *args, **options):
        debug = options.get('debug', False)
        force_time = options.get('force_time', '')

        if not BREVO_API_KEY and not debug:
            self.stdout.write(self.style.WARNING("BREVO_API_KEY not set — skipping."))
            return

        now_utc  = timezone.now()
        today    = date.today()
        sent_count = 0

        # ── One-off task reminders ────────────────────────────────────────
        due_tasks = Task.objects.filter(
            completed=False,
            reminder_sent=False,
            reminder_at__isnull=False,
            reminder_at__lte=now_utc,
        ).select_related('user')

        for task in due_tasks:
            email = self._email_for(task.user)
            if debug:
                self.stdout.write(f"[DEBUG] Task reminder: '{task.title}' → {email or 'NO EMAIL'}")
                task.reminder_sent = True
                task.save(update_fields=['reminder_sent'])
                continue
            if not email:
                task.reminder_sent = True
                task.save(update_fields=['reminder_sent'])
                continue
            try:
                _send_via_brevo(
                    to_email=email,
                    subject=f"⏰ Reminder: {task.title}",
                    body=(f'Your task "{task.title}" is due now.'
                          + (f'\n\nNote: {task.note}' if task.note else '')
                          + '\n\n— PersonalHub'),
                )
                task.reminder_sent = True
                task.save(update_fields=['reminder_sent'])
                sent_count += 1
                self.stdout.write(f"Sent task reminder: '{task.title}' → {email}")
            except Exception as e:
                self.stderr.write(f"Task reminder failed {task.pk}: {e}")

        # ── Daily routine reminders ───────────────────────────────────────
        # Get current IST time
        now_ist = get_ist_now()

        # Allow manual override for testing
        if force_time:
            h, m = force_time.split(':')
            now_ist_time = dtime(int(h), int(m))
        else:
            now_ist_time = now_ist.time().replace(second=0, microsecond=0)

        # ±20 min window
        base = datetime.combine(today, now_ist_time)
        t_start = (base - timedelta(minutes=20)).time()
        t_end   = (base + timedelta(minutes=20)).time()

        self.stdout.write(
            f"Routine window (IST): {t_start.strftime('%H:%M')} – {t_end.strftime('%H:%M')} "
            f"(now IST: {now_ist_time.strftime('%H:%M')})"
        )

        # Handle midnight wraparound (e.g. window 23:45 – 00:15)
        if t_start <= t_end:
            due_routines = RoutineTask.objects.filter(
                is_active=True,
                reminder_time__isnull=False,
                reminder_time__gte=t_start,
                reminder_time__lte=t_end,
            ).select_related('user')
        else:
            due_routines = RoutineTask.objects.filter(
                is_active=True,
                reminder_time__isnull=False,
            ).filter(
                models.Q(reminder_time__gte=t_start) |
                models.Q(reminder_time__lte=t_end)
            ).select_related('user')

        self.stdout.write(f"Routines in window: {due_routines.count()}")

        for routine in due_routines:
            # Check active day
            today_bit = 1 << today.weekday()  # Mon=0..Sun=6
            if not (routine.active_days & today_bit):
                self.stdout.write(f"  Skip '{routine.title}' — not active today")
                continue

            # Get or create today's log
            log, created = RoutineLog.objects.get_or_create(
                routine_task=routine,
                date=today,
                defaults={'user': routine.user, 'reminder_sent': False},
            )

            if log.completed:
                self.stdout.write(f"  Skip '{routine.title}' — already completed")
                continue
            if log.reminder_sent:
                self.stdout.write(f"  Skip '{routine.title}' — reminder already sent today")
                continue

            email = self._email_for(routine.user)

            if debug:
                self.stdout.write(
                    f"[DEBUG] Routine reminder: '{routine.title}' "
                    f"(set: {routine.reminder_time}) → {email or 'NO EMAIL'}"
                )
                log.reminder_sent = True
                log.save(update_fields=['reminder_sent'])
                continue

            if not email:
                self.stdout.write(f"  Skip '{routine.title}' — no reminder email set")
                log.reminder_sent = True
                log.save(update_fields=['reminder_sent'])
                continue

            try:
                _send_via_brevo(
                    to_email=email,
                    subject=f"⏰ Daily routine: {routine.title}",
                    body=(f'Time for your daily routine: "{routine.title}".\n\n'
                          f'Open PersonalHub to tick it off.\n\n— PersonalHub'),
                )
                log.reminder_sent = True
                log.save(update_fields=['reminder_sent'])
                sent_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f"Sent routine reminder: '{routine.title}' → {email}")
                )
            except Exception as e:
                self.stderr.write(f"Routine reminder failed {routine.pk}: {e}")

        self.stdout.write(self.style.SUCCESS(f"Done. {sent_count} reminder(s) sent."))

    def _email_for(self, user):
        try:
            p = UserProfile.objects.get(user=user)
            return p.reminder_email if p.reminder_email else ''
        except UserProfile.DoesNotExist:
            return ''