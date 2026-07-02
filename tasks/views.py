from rest_framework import status, generics
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.permissions import IsAuthenticated, AllowAny, IsAdminUser
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.authtoken.models import Token
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.utils import timezone
from django.db.models import Sum, Max, Count, Q
import csv
import io
from datetime import date, timedelta
import os, hmac, threading
from django.core import management
from django.views.decorators.csrf import csrf_exempt

from .models import (
    Task, TaskCategory, UploadedFile, FileFolder, NoteFolder,
    RoutineTask, RoutineLog, TransactionCategory, Transaction, TextNote, UserProfile,
)
from .serializers import (
    RegisterSerializer, UserSerializer, TaskSerializer, TaskCategorySerializer,
    UploadedFileSerializer, FileFolderSerializer, NoteFolderSerializer,
    RoutineTaskSerializer, RoutineLogSerializer, TransactionCategorySerializer,
    TransactionSerializer, TextNoteSerializer, UserProfileSerializer,
)

DB_QUOTA_BYTES = 1 * 1024 * 1024 * 1024  # 1 GB


def _is_approved(user):
    if user.is_superuser:
        return True
    profile = getattr(user, 'profile', None)
    if profile is None:
        return True
    return profile.is_approved


def approved_only(fn):
    """Decorator: 403 if user is not yet approved by superuser."""
    def wrapper(request, *args, **kwargs):
        if not _is_approved(request.user):
            return Response({'detail': 'Account pending approval.'}, status=403)
        return fn(request, *args, **kwargs)
    return wrapper


# ── Auth ──────────────────────────────────────────────────────────────────────

@api_view(['POST'])
@permission_classes([AllowAny])
def register(request):
    s = RegisterSerializer(data=request.data)
    if s.is_valid():
        s.save()
        return Response({'detail': 'Registration submitted. Waiting for admin approval.'}, status=201)
    return Response(s.errors, status=400)


@api_view(['POST'])
@permission_classes([AllowAny])
def login_view(request):
    username = request.data.get('username', '')
    password = request.data.get('password', '')
    user = authenticate(username=username, password=password)
    if user is None:
        return Response({'detail': 'Invalid credentials.'}, status=400)
    if not user.is_active:
        return Response({'detail': 'Account is deactivated.'}, status=403)
    token, _ = Token.objects.get_or_create(user=user)
    return Response({
        'token': token.key,
        'user': UserSerializer(user).data,
        'approved': _is_approved(user),
    })


@api_view(['POST'])
def logout_view(request):
    try:
        request.user.auth_token.delete()
    except Exception:
        pass
    return Response({'detail': 'Logged out.'})


@api_view(['GET'])
def me(request):
    return Response({
        'user': UserSerializer(request.user).data,
        'approved': _is_approved(request.user),
    })


@api_view(['PATCH'])
def update_profile(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    s = UserProfileSerializer(profile, data=request.data, partial=True)
    if s.is_valid():
        s.save()
        return Response(s.data)
    return Response(s.errors, status=400)


# ── Tasks ─────────────────────────────────────────────────────────────────────

@api_view(['GET', 'POST'])
@approved_only
def tasks_list(request):
    if request.method == 'GET':
        tasks = Task.objects.filter(user=request.user).select_related('category')
        cat = request.GET.get('category')
        if cat == 'none':
            tasks = tasks.filter(category__isnull=True)
        elif cat:
            tasks = tasks.filter(category_id=cat)
        return Response(TaskSerializer(tasks, many=True).data)
    s = TaskSerializer(data=request.data)
    if s.is_valid():
        # Assign next position so new task goes to bottom of active list
        max_pos = Task.objects.filter(user=request.user, completed=False).aggregate(m=Max('position'))['m'] or 0
        s.save(user=request.user, position=max_pos + 1)
        return Response(s.data, status=201)
    return Response(s.errors, status=400)


@api_view(['POST'])
@approved_only
def task_reorder(request):
    """Body: {ordered_ids: [id, id, ...]} — reassigns position 1..n."""
    ids = request.data.get('ordered_ids', [])
    tasks = Task.objects.filter(user=request.user, id__in=ids)
    id_to_task = {t.id: t for t in tasks}
    to_update = []
    for pos, tid in enumerate(ids, start=1):
        t = id_to_task.get(tid)
        if t and t.position != pos:
            t.position = pos
            to_update.append(t)
    if to_update:
        Task.objects.bulk_update(to_update, ['position'])
    return Response({'updated': len(to_update)})


@api_view(['GET', 'POST'])
@approved_only
def task_categories_list(request):
    if request.method == 'GET':
        cats = TaskCategory.objects.filter(user=request.user)
        return Response(TaskCategorySerializer(cats, many=True).data)
    s = TaskCategorySerializer(data=request.data)
    if s.is_valid():
        s.save(user=request.user)
        return Response(s.data, status=201)
    return Response(s.errors, status=400)


@api_view(['PATCH', 'DELETE'])
@approved_only
def task_category_detail(request, pk):
    try:
        cat = TaskCategory.objects.get(pk=pk, user=request.user)
    except TaskCategory.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=404)
    if request.method == 'PATCH':
        s = TaskCategorySerializer(cat, data=request.data, partial=True)
        if s.is_valid():
            s.save()
            return Response(s.data)
        return Response(s.errors, status=400)
    cat.delete()
    return Response(status=204)


@api_view(['GET', 'PATCH', 'DELETE'])
@approved_only
def task_detail(request, pk):
    try:
        task = Task.objects.get(pk=pk, user=request.user)
    except Task.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=404)

    if request.method == 'GET':
        return Response(TaskSerializer(task).data)
    if request.method == 'PATCH':
        s = TaskSerializer(task, data=request.data, partial=True)
        if s.is_valid():
            # Re-arm reminder if reminder_at changed
            if 'reminder_at' in request.data:
                task.reminder_sent = False
            s.save()
            return Response(s.data)
        return Response(s.errors, status=400)
    task.delete()
    return Response(status=204)


@api_view(['POST'])
@approved_only
def task_complete(request, pk):
    try:
        task = Task.objects.get(pk=pk, user=request.user)
    except Task.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=404)
    task.completed = True
    task.completed_at = timezone.now()
    task.save()
    return Response(TaskSerializer(task).data)


@api_view(['POST'])
@approved_only
def task_restore(request, pk):
    try:
        task = Task.objects.get(pk=pk, user=request.user)
    except Task.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=404)
    task.completed = False
    task.completed_at = None
    task.save()
    return Response(TaskSerializer(task).data)


@api_view(['DELETE'])
@approved_only
def delete_all_treasure(request):
    Task.objects.filter(user=request.user, completed=True).delete()
    return Response(status=204)


# ── Files ─────────────────────────────────────────────────────────────────────

@api_view(['GET', 'POST'])
@parser_classes([MultiPartParser, FormParser, JSONParser])
@approved_only
def files_list(request):
    if request.method == 'GET':
        folder_id = request.GET.get('folder')
        if folder_id == 'none':
            files = UploadedFile.objects.filter(user=request.user, folder__isnull=True)
        elif folder_id:
            files = UploadedFile.objects.filter(user=request.user, folder_id=folder_id)
        else:
            files = UploadedFile.objects.filter(user=request.user)
        return Response(UploadedFileSerializer(files, many=True).data)

    uploaded = request.FILES.get('file')
    if not uploaded:
        return Response({'detail': 'No file provided.'}, status=400)

    ext = os.path.splitext(uploaded.name)[1].lower()
    if ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg']:
        ftype = 'image'
    elif ext == '.pdf':
        ftype = 'pdf'
    elif ext in ['.txt', '.md', '.csv']:
        ftype = 'text'
    else:
        ftype = 'other'

    # Upload to Cloudinary directly so we can set resource_type correctly.
    # Images → resource_type=image (supports transformations)
    # Everything else (PDF, text, zip…) → resource_type=raw (served as-is)
    from django.conf import settings as _settings
    cloudinary_active = bool(
        _settings.CLOUDINARY_STORAGE.get('CLOUD_NAME') and
        getattr(_settings, 'DEFAULT_FILE_STORAGE', '').startswith('cloudinary')
    )

    if cloudinary_active:
        import cloudinary.uploader as _cu
        # Images → resource_type='image', everything else → resource_type='raw'
        # Do NOT use 'auto' for PDFs — Cloudinary stores them as image type
        # which creates broken delivery URLs ending in .pdf under /image/upload/.
        resource_type = 'image' if ftype == 'image' else 'raw'
        try:
            result = _cu.upload(
                uploaded,
                folder='media/uploads',
                use_filename=True,
                unique_filename=True,
                resource_type=resource_type,
            )
        except Exception as upload_err:
            return Response({'detail': f'Cloudinary upload failed: {upload_err}'}, status=500)
        cloud_url = result.get('secure_url', '')
        f = UploadedFile.objects.create(
            user=request.user,
            name=uploaded.name,
            cloudinary_url=cloud_url,
            file_type=ftype,
            size=uploaded.size,
        )
    else:
        f = UploadedFile.objects.create(
            user=request.user,
            name=uploaded.name,
            file=uploaded,
            file_type=ftype,
            size=uploaded.size,
        )
    return Response(UploadedFileSerializer(f).data, status=201)


@api_view(['PATCH', 'DELETE'])
@approved_only
def file_delete(request, pk):
    try:
        f = UploadedFile.objects.get(pk=pk, user=request.user)
    except UploadedFile.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=404)
    if request.method == 'PATCH':
        f.folder_id = request.data.get('folder')
        f.save(update_fields=['folder'])
        return Response(UploadedFileSerializer(f).data)
    if f.file:
        try:
            f.file.delete(save=False)
        except Exception:
            pass
    f.delete()
    return Response(status=204)


@api_view(['GET', 'POST'])
@approved_only
def file_folders_list(request):
    if request.method == 'GET':
        return Response(FileFolderSerializer(FileFolder.objects.filter(user=request.user), many=True).data)
    s = FileFolderSerializer(data=request.data)
    if s.is_valid():
        s.save(user=request.user)
        return Response(s.data, status=201)
    return Response(s.errors, status=400)


@api_view(['PATCH', 'DELETE'])
@approved_only
def file_folder_detail(request, pk):
    try:
        folder = FileFolder.objects.get(pk=pk, user=request.user)
    except FileFolder.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=404)
    if request.method == 'PATCH':
        s = FileFolderSerializer(folder, data=request.data, partial=True)
        if s.is_valid():
            s.save()
            return Response(s.data)
        return Response(s.errors, status=400)
    folder.delete()
    return Response(status=204)


@api_view(['GET', 'POST'])
@approved_only
def note_folders_list(request):
    if request.method == 'GET':
        return Response(NoteFolderSerializer(NoteFolder.objects.filter(user=request.user), many=True).data)
    s = NoteFolderSerializer(data=request.data)
    if s.is_valid():
        s.save(user=request.user)
        return Response(s.data, status=201)
    return Response(s.errors, status=400)


@api_view(['PATCH', 'DELETE'])
@approved_only
def note_folder_detail(request, pk):
    try:
        folder = NoteFolder.objects.get(pk=pk, user=request.user)
    except NoteFolder.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=404)
    if request.method == 'PATCH':
        s = NoteFolderSerializer(folder, data=request.data, partial=True)
        if s.is_valid():
            s.save()
            return Response(s.data)
        return Response(s.errors, status=400)
    folder.delete()
    return Response(status=204)


@api_view(['GET'])
@approved_only
def transactions_history(request):
    from datetime import timedelta
    from django.utils import timezone as _tz
    cutoff = _tz.now() - timedelta(days=30)
    txns = Transaction.objects.filter(
        user=request.user, is_deleted=True, deleted_at__gte=cutoff
    ).select_related('category')
    return Response(TransactionSerializer(txns, many=True).data)


@api_view(['POST'])
@approved_only
def transaction_restore(request, pk):
    try:
        t = Transaction.objects.get(pk=pk, user=request.user, is_deleted=True)
    except Transaction.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=404)
    t.is_deleted = False
    t.deleted_at = None
    t.save(update_fields=['is_deleted', 'deleted_at'])
    return Response(TransactionSerializer(t).data)


@api_view(['DELETE'])
@approved_only
def transaction_permanent_delete(request, pk):
    try:
        t = Transaction.objects.get(pk=pk, user=request.user, is_deleted=True)
    except Transaction.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=404)
    t.delete()
    return Response(status=204)


@api_view(['POST'])
@approved_only
def routine_reorder(request):
    ids = request.data.get('ordered_ids', [])
    tasks = RoutineTask.objects.filter(user=request.user, id__in=ids)
    id_map = {t.id: t for t in tasks}
    to_update = []
    for pos, tid in enumerate(ids, start=1):
        t = id_map.get(tid)
        if t and t.position != pos:
            t.position = pos
            to_update.append(t)
    if to_update:
        RoutineTask.objects.bulk_update(to_update, ['position'])
    return Response({'updated': len(to_update)})


@csrf_exempt
def file_proxy(request, pk):
    """
    Proxy a Cloudinary-stored file through Django.
    Auth: Token in Authorization header OR ?token= query param.
    """
    from django.http import HttpResponse, StreamingHttpResponse

    # ── Step 1: resolve the user from token ──────────────────────────────────
    auth_user = None

    # Try Authorization header first (Token abc123)
    auth_header = request.META.get('HTTP_AUTHORIZATION', '')
    if auth_header.startswith('Token '):
        header_key = auth_header[6:].strip()
        try:
            auth_user = Token.objects.select_related('user').get(key=header_key).user
        except Token.DoesNotExist:
            pass

    # Fall back to ?token= query param (used by window.open)
    if auth_user is None:
        query_key = request.GET.get('token', '').strip()
        if query_key:
            try:
                auth_user = Token.objects.select_related('user').get(key=query_key).user
            except Token.DoesNotExist:
                return HttpResponse('Unauthorized: invalid token', status=401)

    # Also accept if DRF already authenticated the request
    if auth_user is None and hasattr(request, 'user') and request.user.is_authenticated:
        auth_user = request.user

    if auth_user is None:
        return HttpResponse('Unauthorized: no token provided', status=401)

    # ── Step 2: check account is approved ────────────────────────────────────
    if not auth_user.is_superuser:
        try:
            from .models import UserProfile as _UP
            prof = _UP.objects.get(user=auth_user)
            if not prof.is_approved:
                return HttpResponse('Forbidden: account not approved', status=403)
        except _UP.DoesNotExist:
            return HttpResponse('Forbidden: no profile', status=403)

    # ── Step 3: fetch the file record ───────────────────────────────────────
    try:
        f = UploadedFile.objects.get(pk=pk, user=auth_user)
    except UploadedFile.DoesNotExist:
        return HttpResponse('Not found', status=404)

    stored_url = getattr(f, 'cloudinary_url', '') or (f.file.url if f.file else None)
    if not stored_url:
        return HttpResponse('No file URL', status=404)

    import urllib.request as _urllib_req
    import urllib.error as _urllib_err

    MIME_MAP = {
        'image':  'image/jpeg',
        'pdf':    'application/pdf',
        'text':   'text/plain; charset=utf-8',
        'other':  'application/octet-stream',
    }
    content_type = MIME_MAP.get(f.file_type, 'application/octet-stream')

    disposition = 'inline'
    if request.GET.get('download') == '1':
        safe_name = f.name.replace(chr(34), '')
        disposition = f'attachment; filename="{safe_name}"'

    # Use Cloudinary's private_download_url to get a signed, time-limited URL.
    # This is the official way to access raw/restricted Cloudinary resources.
    import re as _re
    from django.conf import settings as _s
    try:
        import cloudinary
        import cloudinary.utils as _cu
        cfg = _s.CLOUDINARY_STORAGE
        cloudinary.config(
            cloud_name=cfg.get('CLOUD_NAME', ''),
            api_key=cfg.get('API_KEY', ''),
            api_secret=cfg.get('API_SECRET', ''),
        )
        # Extract public_id from URL — for raw files this INCLUDES the extension
        # URL pattern: https://res.cloudinary.com/{cloud}/{rtype}/upload/v{ver}/{public_id}
        m = _re.search(r'/upload/(?:v\d+/)?(.+)$', stored_url)
        if not m:
            raise ValueError(f'Cannot parse public_id from: {stored_url}')
        public_id_with_ext = m.group(1)  # e.g. media/uploads/file_abc123.pdf

        # Determine resource type from URL
        rt_match = _re.search(r'/(image|raw|video)/upload/', stored_url)
        rtype = rt_match.group(1) if rt_match else 'raw'

        # For PDFs stored as image type (old auto uploads), use raw
        if f.file_type == 'pdf' and rtype == 'image':
            rtype = 'raw'
            public_id_with_ext = public_id_with_ext  # keep .pdf extension

        # For raw resources, Cloudinary stores public_id WITH the extension.
        # e.g. public_id = "media/uploads/file_abc.pdf", format = ""
        # Using format="" and full public_id (with ext) is correct for raw type.
        if rtype == 'raw':
            # Raw: public_id includes extension, format must be empty string
            public_id = public_id_with_ext
            fmt = ''
        else:
            # Image: public_id without extension, format = extension
            if '.' in public_id_with_ext.split('/')[-1]:
                dot_idx = public_id_with_ext.rfind('.')
                public_id = public_id_with_ext[:dot_idx]
                fmt = public_id_with_ext[dot_idx+1:]
            else:
                public_id = public_id_with_ext
                fmt = ''

        signed_url = _cu.private_download_url(
            public_id,
            fmt,
            resource_type=rtype,
            type='upload',
        )
        fetch_url = signed_url
    except Exception as sign_err:
        # Fallback: use stored URL directly
        fetch_url = stored_url

    def try_fetch(url):
        req = _urllib_req.Request(url, headers={'User-Agent': 'PersonalHub/1.0'})
        return _urllib_req.urlopen(req, timeout=30)

    try:
        remote = try_fetch(fetch_url)
    except Exception as e:
        return HttpResponse(
            f'Could not fetch file.\nURL: {fetch_url}\nError: {e}',
            status=502, content_type='text/plain'
        )

    response = StreamingHttpResponse(remote, content_type=content_type)
    response['Content-Disposition'] = disposition
    response['Cache-Control'] = 'private, max-age=3600'
    response['X-Frame-Options'] = 'SAMEORIGIN'
    return response


# ── Text Notes ────────────────────────────────────────────────────────────────

@api_view(['GET', 'POST'])
@approved_only
def notes_list(request):
    if request.method == 'GET':
        folder_id = request.GET.get('folder')
        if folder_id == 'none':
            notes = TextNote.objects.filter(user=request.user, folder__isnull=True)
        elif folder_id:
            notes = TextNote.objects.filter(user=request.user, folder_id=folder_id)
        else:
            notes = TextNote.objects.filter(user=request.user)
        return Response(TextNoteSerializer(notes, many=True).data)
    s = TextNoteSerializer(data=request.data)
    if s.is_valid():
        s.save(user=request.user)
        return Response(s.data, status=201)
    return Response(s.errors, status=400)


@api_view(['PATCH', 'DELETE'])
@approved_only
def note_detail(request, pk):
    try:
        note = TextNote.objects.get(pk=pk, user=request.user)
    except TextNote.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=404)
    if request.method == 'PATCH':
        if list(request.data.keys()) == ['folder']:
            note.folder_id = request.data.get('folder')
            note.save(update_fields=['folder'])
            return Response(TextNoteSerializer(note).data)
        s = TextNoteSerializer(note, data=request.data, partial=True)
        if s.is_valid():
            s.save()
            return Response(s.data)
        return Response(s.errors, status=400)
    note.delete()
    return Response(status=204)


# ── Daily Routine ─────────────────────────────────────────────────────────────

def _ensure_today_logs(user):
    today = date.today()
    today_bit = 1 << today.weekday()  # Mon=0..Sun=6
    active_routines = RoutineTask.objects.filter(user=user, is_active=True)

    for rt in active_routines:
        if rt.active_days & today_bit:
            # Should run today — ensure log exists
            RoutineLog.objects.get_or_create(routine_task=rt, date=today, defaults={'user': user})
        else:
            # Should NOT run today — delete any stale log (e.g. created before active_days was set)
            RoutineLog.objects.filter(routine_task=rt, date=today).delete()


@api_view(['GET', 'POST'])
@approved_only
def routine_tasks_list(request):
    if request.method == 'GET':
        tasks = RoutineTask.objects.filter(user=request.user)
        return Response(RoutineTaskSerializer(tasks, many=True).data)
    s = RoutineTaskSerializer(data=request.data)
    if s.is_valid():
        max_pos = RoutineTask.objects.filter(user=request.user).aggregate(m=Max('position'))['m'] or 0
        rt = s.save(user=request.user, position=max_pos + 1)
        today_bit = 1 << date.today().weekday()
        if rt.active_days & today_bit:
            RoutineLog.objects.get_or_create(routine_task=rt, date=date.today(), defaults={'user': request.user})
        return Response(RoutineTaskSerializer(rt).data, status=201)
    return Response(s.errors, status=400)


@api_view(['PATCH', 'DELETE'])
@approved_only
def routine_task_detail(request, pk):
    try:
        rt = RoutineTask.objects.get(pk=pk, user=request.user)
    except RoutineTask.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=404)
    if request.method == 'PATCH':
        s = RoutineTaskSerializer(rt, data=request.data, partial=True)
        if s.is_valid():
            s.save()
            if 'reminder_time' in request.data:
                RoutineLog.objects.filter(routine_task=rt, date=date.today()).update(reminder_sent=False)
            return Response(s.data)
        return Response(s.errors, status=400)
    rt.delete()
    return Response(status=204)


@api_view(['GET'])
@approved_only
def routine_today(request):
    """Returns today's logs + progress stats. Ensures logs exist."""
    _ensure_today_logs(request.user)
    today = date.today()

    today_logs = RoutineLog.objects.filter(user=request.user, date=today).select_related('routine_task').order_by('routine_task__position', 'routine_task__created_at')
    total_today = today_logs.count()
    done_today = today_logs.filter(completed=True).count()
    today_pct = int((done_today / total_today * 100) if total_today else 0)

    week_start = today - timedelta(days=today.weekday())
    week_logs = RoutineLog.objects.filter(user=request.user, date__gte=week_start, date__lte=today)
    total_week = week_logs.count()
    done_week = week_logs.filter(completed=True).count()
    week_pct = int((done_week / total_week * 100) if total_week else 0)

    month_start = today.replace(day=1)
    month_logs = RoutineLog.objects.filter(user=request.user, date__gte=month_start, date__lte=today)
    total_month = month_logs.count()
    done_month = month_logs.filter(completed=True).count()
    month_pct = int((done_month / total_month * 100) if total_month else 0)

    return Response({
        'logs': RoutineLogSerializer(today_logs, many=True).data,
        'today_pct': today_pct,
        'week_pct': week_pct,
        'month_pct': month_pct,
        'done_today': done_today,
        'total_today': total_today,
    })


@api_view(['POST'])
@approved_only
def routine_log_toggle(request, pk):
    try:
        log = RoutineLog.objects.get(pk=pk, user=request.user)
    except RoutineLog.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=404)
    log.completed = not log.completed
    log.completed_at = timezone.now() if log.completed else None
    log.save()
    return Response(RoutineLogSerializer(log).data)


@api_view(['GET'])
@approved_only
def routine_history(request):
    """Returns past logs grouped by date (last 30 days, excluding today)."""
    today = date.today()
    thirty_ago = today - timedelta(days=30)
    logs = (RoutineLog.objects
            .filter(user=request.user, date__gte=thirty_ago, date__lt=today)
            .select_related('routine_task')
            .order_by('-date', 'routine_task__title'))

    # Group by date
    from collections import OrderedDict
    grouped = OrderedDict()
    for log in logs:
        d = str(log.date)
        if d not in grouped:
            grouped[d] = {'date': d, 'logs': [], 'done': 0, 'total': 0}
        grouped[d]['logs'].append(RoutineLogSerializer(log).data)
        grouped[d]['total'] += 1
        if log.completed:
            grouped[d]['done'] += 1

    for g in grouped.values():
        g['pct'] = int(g['done'] / g['total'] * 100) if g['total'] else 0

    return Response(list(grouped.values()))


@api_view(['DELETE'])
@approved_only
def routine_delete_history(request):
    RoutineLog.objects.filter(user=request.user).exclude(date=date.today()).delete()
    return Response(status=204)


# ── Transactions ──────────────────────────────────────────────────────────────

@api_view(['GET', 'POST'])
@approved_only
def categories_list(request):
    if request.method == 'GET':
        cats = TransactionCategory.objects.filter(user=request.user)
        return Response(TransactionCategorySerializer(cats, many=True).data)
    s = TransactionCategorySerializer(data=request.data)
    if s.is_valid():
        s.save(user=request.user)
        return Response(s.data, status=201)
    return Response(s.errors, status=400)


@api_view(['PATCH', 'DELETE'])
@approved_only
def category_detail(request, pk):
    try:
        cat = TransactionCategory.objects.get(pk=pk, user=request.user)
    except TransactionCategory.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=404)
    if request.method == 'PATCH':
        s = TransactionCategorySerializer(cat, data=request.data, partial=True)
        if s.is_valid():
            s.save()
            return Response(s.data)
        return Response(s.errors, status=400)
    cat.delete()  # transactions become Uncategorized (SET_NULL)
    return Response(status=204)


@api_view(['GET', 'POST'])
@approved_only
def transactions_list(request):
    if request.method == 'GET':
        txns = Transaction.objects.filter(user=request.user, is_deleted=False)
        cat_filter = request.GET.get('category', '')
        if cat_filter == 'none':
            txns = txns.filter(category__isnull=True)
        elif cat_filter:
            txns = txns.filter(category__pk=cat_filter)

        total_income = txns.filter(transaction_type='income').aggregate(s=Sum('amount'))['s'] or 0
        total_expense = txns.filter(transaction_type='expense').aggregate(s=Sum('amount'))['s'] or 0
        return Response({
            'transactions': TransactionSerializer(txns, many=True).data,
            'total_income': float(total_income),
            'total_expense': float(total_expense),
            'balance': float(total_income - total_expense),
        })

    s = TransactionSerializer(data=request.data)
    if s.is_valid():
        s.save(user=request.user)
        return Response(s.data, status=201)
    return Response(s.errors, status=400)


@api_view(['PATCH', 'DELETE'])
@approved_only
def transaction_detail(request, pk):
    try:
        t = Transaction.objects.get(pk=pk, user=request.user)
    except Transaction.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=404)
    if request.method == 'PATCH':
        s = TransactionSerializer(t, data=request.data, partial=True)
        if s.is_valid():
            s.save()
            return Response(s.data)
        return Response(s.errors, status=400)
    from django.utils import timezone as _tz
    t.is_deleted = True
    t.deleted_at = _tz.now()
    t.save(update_fields=['is_deleted', 'deleted_at'])
    return Response(status=204)


@api_view(['DELETE'])
@approved_only
def transactions_delete_all(request):
    from django.utils import timezone as _tz
    Transaction.objects.filter(user=request.user, is_deleted=False).update(
        is_deleted=True, deleted_at=_tz.now()
    )
    return Response(status=204)


@api_view(['GET'])
@approved_only
def transactions_history(request):
    from datetime import timedelta
    from django.utils import timezone as _tz
    cutoff = _tz.now() - timedelta(days=30)
    txns = Transaction.objects.filter(
        user=request.user, is_deleted=True, deleted_at__gte=cutoff
    ).select_related('category')
    return Response(TransactionSerializer(txns, many=True).data)


@api_view(['POST'])
@approved_only
def transaction_restore(request, pk):
    try:
        t = Transaction.objects.get(pk=pk, user=request.user, is_deleted=True)
    except Transaction.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=404)
    t.is_deleted = False
    t.deleted_at = None
    t.save(update_fields=['is_deleted', 'deleted_at'])
    return Response(TransactionSerializer(t).data)


@api_view(['DELETE'])
@approved_only
def transaction_permanent_delete(request, pk):
    try:
        t = Transaction.objects.get(pk=pk, user=request.user, is_deleted=True)
    except Transaction.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=404)
    t.delete()
    return Response(status=204)


# ── Superuser: Users page ─────────────────────────────────────────────────────

def _estimate_user_bytes(user):
    total = 0
    for t in Task.objects.filter(user=user).only('title', 'note'):
        total += len(t.title or '') + len(t.note or '') + 64
    for f in UploadedFile.objects.filter(user=user).only('name', 'size'):
        total += (f.size or 0) + len(f.name or '') + 64
    for rt in RoutineTask.objects.filter(user=user).only('title'):
        total += len(rt.title or '') + 48
    total += RoutineLog.objects.filter(user=user).count() * 48
    for tx in Transaction.objects.filter(user=user).only('title', 'note'):
        total += len(tx.title or '') + len(tx.note or '') + 80
    for n in TextNote.objects.filter(user=user).only('heading', 'body'):
        total += len(n.heading or '') + len(n.body or '') + 64
    return total


def _format_bytes(n):
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / (1024 * 1024):.2f} MB"


# ── GLOBAL SEARCH ─────────────────────────────────────────────────────────────
@api_view(['GET'])
@approved_only
def global_search(request):
    q = request.GET.get('q', '').strip()
    if not q or len(q) < 2:
        return Response({'tasks': [], 'notes': [], 'files': [], 'transactions': []})
    tasks = Task.objects.filter(user=request.user, completed=False).filter(
        Q(title__icontains=q) | Q(note__icontains=q)
    )[:8]
    notes = TextNote.objects.filter(user=request.user).filter(
        Q(heading__icontains=q) | Q(body__icontains=q)
    )[:8]
    files = UploadedFile.objects.filter(user=request.user, name__icontains=q)[:8]
    transactions = Transaction.objects.filter(user=request.user, is_deleted=False).filter(
        Q(title__icontains=q) | Q(note__icontains=q)
    )[:8]
    return Response({
        'tasks': TaskSerializer(tasks, many=True).data,
        'notes': TextNoteSerializer(notes, many=True).data,
        'files': UploadedFileSerializer(files, many=True).data,
        'transactions': TransactionSerializer(transactions, many=True).data,
    })


# ── ROUTINE STREAKS ────────────────────────────────────────────────────────────
@api_view(['GET'])
@approved_only
def routine_streaks(request):
    from datetime import timedelta
    today = date.today()
    tasks = RoutineTask.objects.filter(user=request.user, is_active=True)
    result = []
    for rt in tasks:
        all_logs = list(RoutineLog.objects.filter(routine_task=rt, completed=True).order_by('-date'))
        current = 0; best = 0
        if all_logs:
            streak = 1; prev = all_logs[0].date
            for log in all_logs[1:]:
                if (prev - log.date).days == 1:
                    streak += 1; prev = log.date
                else:
                    break
            current = streak
            s = 1; b = 1; sorted_asc = sorted(all_logs, key=lambda x: x.date)
            for i in range(1, len(sorted_asc)):
                if (sorted_asc[i].date - sorted_asc[i-1].date).days == 1:
                    s += 1; b = max(b, s)
                else:
                    s = 1
            best = max(b, s)
        result.append({'id': rt.id, 'title': rt.title, 'current_streak': current, 'best_streak': best})
    return Response(result)


# ── MONEY CHARTS ──────────────────────────────────────────────────────────────
@api_view(['GET'])
@approved_only
def transaction_charts(request):
    from datetime import timedelta
    from collections import defaultdict
    today = date.today()
    start = today - timedelta(days=29)
    txns = Transaction.objects.filter(
        user=request.user, is_deleted=False,
        created_at__date__gte=start,
    ).values('created_at__date', 'transaction_type', 'amount')
    daily = defaultdict(lambda: {'income': 0.0, 'expense': 0.0})
    for t in txns:
        d = str(t['created_at__date'])
        daily[d][t['transaction_type']] += float(t['amount'])
    chart_data = []
    for i in range(30):
        d = str(start + timedelta(days=i))
        chart_data.append({'date': d, 'income': daily[d]['income'], 'expense': daily[d]['expense']})
    cat_data = list(Transaction.objects.filter(
        user=request.user, is_deleted=False, transaction_type='expense',
        created_at__year=today.year, created_at__month=today.month
    ).values('category__name').annotate(total=Sum('amount')).order_by('-total'))
    return Response({'daily': chart_data, 'by_category': cat_data})


# ── EXPORT DATA ───────────────────────────────────────────────────────────────
@api_view(['GET'])
@approved_only
def export_tasks(request):
    tasks = Task.objects.filter(user=request.user)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(['ID','Title','Note','Completed','Category','Due Date','Created'])
    for t in tasks:
        w.writerow([t.id, t.title, t.note, t.completed,
                    t.category.name if t.category else '', t.due_date or '', t.created_at.date()])
    from django.http import HttpResponse
    resp = HttpResponse(buf.getvalue(), content_type='text/csv')
    resp['Content-Disposition'] = 'attachment; filename="tasks.csv"'
    return resp


@api_view(['GET'])
@approved_only
def export_transactions(request):
    txns = Transaction.objects.filter(user=request.user, is_deleted=False)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(['ID','Title','Amount','Type','Category','Note','Date'])
    for t in txns:
        w.writerow([t.id, t.title, t.amount, t.transaction_type,
                    t.category.name if t.category else '', t.note, t.created_at.date()])
    from django.http import HttpResponse
    resp = HttpResponse(buf.getvalue(), content_type='text/csv')
    resp['Content-Disposition'] = 'attachment; filename="transactions.csv"'
    return resp


@api_view(['GET'])
@approved_only
def export_notes(request):
    notes = TextNote.objects.filter(user=request.user)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(['ID','Heading','Body','Folder','Updated'])
    for n in notes:
        w.writerow([n.id, n.heading, n.body,
                    n.folder.name if n.folder else '', n.updated_at.date()])
    from django.http import HttpResponse
    resp = HttpResponse(buf.getvalue(), content_type='text/csv')
    resp['Content-Disposition'] = 'attachment; filename="notes.csv"'
    return resp


# ── SUBTASKS ──────────────────────────────────────────────────────────────────
@api_view(['GET', 'POST'])
@approved_only
def subtasks_list(request, pk):
    try:
        parent = Task.objects.get(pk=pk, user=request.user)
    except Task.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=404)
    if request.method == 'GET':
        return Response(TaskSerializer(parent.subtasks.all(), many=True).data)
    s = TaskSerializer(data=request.data)
    if s.is_valid():
        max_pos = parent.subtasks.aggregate(m=Max('position'))['m'] or 0
        s.save(user=request.user, parent=parent, position=max_pos+1)
        return Response(s.data, status=201)
    return Response(s.errors, status=400)


# ── PROFILE AVATAR ──────────────────────────────────────────────────────────
@api_view(['POST'])
@approved_only
@parser_classes([MultiPartParser, FormParser])
def upload_avatar(request):
    uploaded = request.FILES.get('avatar')
    if not uploaded:
        return Response({'detail': 'No file.'}, status=400)
    from django.conf import settings as _s
    cfg = _s.CLOUDINARY_STORAGE
    if cfg.get('CLOUD_NAME'):
        import cloudinary.uploader as _cu
        try:
            result = _cu.upload(uploaded, folder='avatars', resource_type='image',
                                transformation=[{'width': 200, 'height': 200, 'crop': 'fill'}])
            url = result.get('secure_url', '')
        except Exception as e:
            return Response({'detail': str(e)}, status=500)
    else:
        url = ''
    profile = request.user.profile
    profile.avatar_url = url
    profile.save(update_fields=['avatar_url'])
    return Response({'avatar_url': url})


# ── ACCOUNT STATS ─────────────────────────────────────────────────────────────
@api_view(['GET'])
@approved_only
def account_stats(request):
    user = request.user
    return Response({
        'tasks_done': Task.objects.filter(user=user, completed=True).count(),
        'tasks_active': Task.objects.filter(user=user, completed=False).count(),
        'habits_completed': RoutineLog.objects.filter(user=user, completed=True).count(),
        'notes': TextNote.objects.filter(user=user).count(),
        'files': UploadedFile.objects.filter(user=user).count(),
        'transactions': Transaction.objects.filter(user=user, is_deleted=False).count(),
    })


@api_view(['GET', 'POST'])
def admin_users(request):
    if not request.user.is_superuser:
        return Response({'detail': 'Forbidden.'}, status=403)

    if request.method == 'POST':
        action = request.data.get('action')
        pk = request.data.get('pk')
        try:
            target = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return Response({'detail': 'User not found.'}, status=404)

        if target.is_superuser and action in ('reject', 'deactivate'):
            return Response({'detail': "Can't deactivate/reject a superuser."}, status=400)

        if action == 'approve':
            profile, _ = UserProfile.objects.get_or_create(user=target)
            profile.is_approved = True
            profile.approved_at = timezone.now()
            profile.save()
            target.is_active = True
            target.save()
        elif action == 'reject':
            target.delete()
            return Response({'detail': 'User rejected and removed.'})
        elif action == 'deactivate':
            target.is_active = False
            target.save()
        elif action == 'activate':
            target.is_active = True
            target.save()
            profile, _ = UserProfile.objects.get_or_create(user=target)
            if not profile.is_approved:
                profile.is_approved = True
                profile.approved_at = timezone.now()
                profile.save()
        return Response({'detail': 'Done.'})

    all_users = User.objects.all().order_by('-date_joined').select_related('profile')
    users_data = []
    total_bytes = 0
    for u in all_users:
        b = _estimate_user_bytes(u)
        total_bytes += b
        ud = UserSerializer(u).data
        ud['storage'] = {
            'bytes': b,
            'display': _format_bytes(b),
            'pct_of_quota': round((b / DB_QUOTA_BYTES) * 100, 3),
        }
        users_data.append(ud)

    return Response({
        'users': users_data,
        'total_usage_display': _format_bytes(total_bytes),
        'total_usage_pct': round((total_bytes / DB_QUOTA_BYTES) * 100, 2),
        'quota_display': _format_bytes(DB_QUOTA_BYTES),
    })


# ── Cron webhook ──────────────────────────────────────────────────────────────

CRON_SECRET = os.environ.get('CRON_SECRET', '')


def _run_reminders():
    try:
        management.call_command('send_reminders')
    except Exception as e:
        import logging
        logging.getLogger(__name__).error('send_reminders failed: %s', e)


@csrf_exempt
@api_view(['GET', 'POST'])
@permission_classes([AllowAny])
def cron_send_reminders(request):
    secret = CRON_SECRET
    if not secret:
        return Response({'error': 'Forbidden'}, status=403)
    provided = request.GET.get('key', '') or request.headers.get('X-Cron-Key', '')
    if not hmac.compare_digest(provided, secret):
        return Response({'error': 'Forbidden'}, status=403)
    t = threading.Thread(target=_run_reminders, daemon=True)
    t.start()
    return Response({'ok': True, 'msg': 'Reminder job started in background'})