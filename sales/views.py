from django.shortcuts import render,redirect,HttpResponse,get_object_or_404
from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.contrib.auth.models import User,auth
from django.contrib.auth.decorators import login_required,user_passes_test
from django.http import JsonResponse,Http404
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
import pandas as pd
from django.db.models import Count, Sum, Q, Avg
from rest_framework.permissions import IsAuthenticated
import random
import os
import logging
from rest_framework.decorators import api_view
from rest_framework.decorators import api_view, permission_classes,authentication_classes
from rest_framework.permissions import AllowAny
from django.views.decorators.csrf import csrf_exempt
from rest_framework.response import Response
from rest_framework import status
from .serializers import LoginSerializer
import json
from django.core.serializers.json import DjangoJSONEncoder
from datetime import datetime,timedelta
from django.conf import settings
from django.utils import timezone
from .models import LeadFile, LeadAllocation, User,CallRecord,UserDetail,CallRecording
from django.db import models
# Create your views here. 
def admin_check(user):
    return user.is_superuser
def indexpage(request): 

    if request.method == 'POST':
        print("working")
        email = request.POST.get('email')
        password = request.POST.get('password')
        remember = request.POST.get('remember_me')

        # Authenticate by email
        try:
            user = User.objects.get(username=email)
        except User.DoesNotExist:
            messages.error(request, "Invalid email or password")
            return redirect('/')

        user = authenticate(request, username=user.username, password=password)


        if user is not None:
            if user.is_superuser:
                login(request, user)
                if not remember:
                    request.session.set_expiry(0)  # Session ends when browser closes
                return redirect('dashboard')
            else:
               
               login(request, user)
               return redirect('dashboard2')
              
                # or return render(request, 'login.html', {...})
        else:
            messages.error(request, "Invalid email or password")
            return redirect('/')

    return render(request,'index.html') 


@login_required
def dashboard(request):
    # Basic counts
    print(CallRecord.objects.all().count())
    totallead=(LeadFile.objects.aggregate(total=Sum('total_numbers'))['total'] or 0 )- (CallRecord.objects.all().count())
    print(totallead)
    total_leads = LeadFile.objects.aggregate(total=Sum('total_numbers'))['total'] or 0
    allocated_leads = LeadFile.objects.aggregate(total=Sum('allocated_numbers'))['total'] or 0
    allocation_rate = round((allocated_leads / total_leads * 100) if total_leads > 0 else 0, 1)
    
    contacted_leads = CallRecord.objects.filter(status='contacted').count()
    contact_rate = round((contacted_leads / allocated_leads * 100) if allocated_leads > 0 else 0, 1)
    
    interested_leads = CallRecord.objects.filter(status='interested').count()
    conversion_rate = round((interested_leads / contacted_leads * 100) if contacted_leads > 0 else 0, 1)
    
    # Month-over-month improvement
    today = timezone.now()
    last_month_start = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
    current_month_start = today.replace(day=1)
    
    current_month_interested = CallRecord.objects.filter(
        status='interested',
        call_time__gte=current_month_start
    ).count()
    
    last_month_interested = CallRecord.objects.filter(
        status='interested',
        call_time__gte=last_month_start,
        call_time__lt=current_month_start
    ).count()
    
    if last_month_interested > 0:
        conversion_improvement = round(
            ((current_month_interested - last_month_interested) / last_month_interested * 100), 1
        )
    elif current_month_interested > 0:
        conversion_improvement = 100
    else:
        conversion_improvement = 0

    # Recent files
    recent_files = LeadFile.objects.order_by('-created_at')[:5]
    for file in recent_files:
        file.allocation_percentage = round((file.allocated_numbers / file.total_numbers * 100)
                                           if file.total_numbers > 0 else 0)

    # Recent allocations
    recent_allocations = LeadAllocation.objects.select_related('user', 'file').order_by('-created_at')[:5]
    for allocation in recent_allocations:
        allocated_count = allocation.get_allocated_count() if hasattr(allocation, 'get_allocated_count') \
                          else (allocation.end_index - allocation.start_index + 1)
        allocation.allocated_count = allocated_count
        allocation.percentage = round((allocated_count / allocation.file.total_numbers * 100)
                                      if allocation.file.total_numbers > 0 else 0, 1)

    # Lead status chart data
    status_counts = {
        'new': CallRecord.objects.filter(status='new').count(),
        'contacted': contacted_leads,
        'interested': interested_leads,
        'not_interested': CallRecord.objects.filter(status='not_interested').count(),
        'invalid': CallRecord.objects.filter(status='invalid').count(),
        'callback': CallRecord.objects.filter(status='callback').count(),
    }

    lead_status_labels = ['New', 'Contacted', 'Interested', 'Not Interested', 'Invalid', 'Callback']
    lead_status_values = [
        status_counts['new'],
        status_counts['contacted'],
        status_counts['interested'],
        status_counts['not_interested'],
        status_counts['invalid'],
        status_counts['callback']
    ]

    # Performance chart (last 12 months)
    months = []
    allocated_data = []
    contacted_data = []
    conversion_data = []

    for i in range(11, -1, -1):
        month_start = (today.replace(day=1) - timedelta(days=30*i)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        if month_start.month == 12:
            month_end = month_start.replace(year=month_start.year + 1, month=1) - timedelta(days=1)
        else:
            month_end = month_start.replace(month=month_start.month + 1) - timedelta(days=1)

        month_end = month_end.replace(hour=23, minute=59, second=59, microsecond=999999)
        months.append(month_start.strftime('%b %Y'))

        allocated = LeadAllocation.objects.filter(
            created_at__gte=month_start,
            created_at__lte=month_end
        ).aggregate(total=Sum('end_index') - Sum('start_index') + Count('id'))
        allocated_count = allocated['total'] or 0
        allocated_data.append(allocated_count)

        contacted = CallRecord.objects.filter(
            call_time__gte=month_start,
            call_time__lte=month_end,
            status='contacted'
        ).count()
        contacted_data.append(contacted)

        conversions = CallRecord.objects.filter(
            call_time__gte=month_start,
            call_time__lte=month_end,
            status='interested'
        ).count()
        conversion_data.append(conversions)

    # Team performance
    team_performance = []
    agents = User.objects.filter(is_active=True, allocations__isnull=False).distinct()
    for agent in agents:
        allocations = LeadAllocation.objects.filter(user=agent)
        total_allocated = sum(
            alloc.get_allocated_count() if hasattr(alloc, 'get_allocated_count')
            else (alloc.end_index - alloc.start_index + 1)
            for alloc in allocations
        )
        call_records = CallRecord.objects.filter(allocation__user=agent)
        contacted_count = call_records.filter(status='contacted').count()
        interested_count = call_records.filter(status='interested').count()

        contact_rate_agent = round((contacted_count / total_allocated * 100) if total_allocated > 0 else 0, 1)
        interested_rate_agent = round((interested_count / contacted_count * 100) if contacted_count > 0 else 0, 1)
        conversion_rate_agent = round((interested_count / total_allocated * 100) if total_allocated > 0 else 0, 1)

        team_performance.append({
            'user': agent,
            'total_leads': total_leads,
            'total_leads': total_allocated,
            'contacted_leads': contacted_count,
            'interested_leads': interested_count,
            'contact_rate': min(contact_rate_agent, 100),
            'interested_rate': min(interested_rate_agent, 100),
            'conversion_rate': min(conversion_rate_agent, 100)
        })

    team_performance.sort(key=lambda x: x['conversion_rate'], reverse=True)

    context = {
        'totallead':totallead,
        'total_leads': total_leads,
        'allocated_leads': allocated_leads,
        'allocation_rate': allocation_rate,
        'contacted_leads': contacted_leads,
        'contact_rate': contact_rate,
        'conversion_rate': conversion_rate,
        'conversion_improvement': conversion_improvement,
        'recent_files': recent_files,
        'recent_allocations': recent_allocations,
        'status_counts': status_counts,
        'team_performance': team_performance,
        'lead_status_labels': lead_status_labels,
        'lead_status_values': lead_status_values,
        'performance_months': months,
        'allocated_data': allocated_data,
        'contacted_data': contacted_data,
        'conversion_data': conversion_data,
    }

    return render(request, 'dashboard.html', context)

@login_required
def dashboard2(request):
    """
    Enhanced dashboard view with total calls tracking and optimized queries
    """
    # Get current date and calculate date ranges
    today = timezone.now().date()
    yesterday = today - timedelta(days=1)
    last_week = today - timedelta(days=7)
    last_month = today - timedelta(days=30)
    
    # Get user's data with optimized queries
    user_allocations = LeadAllocation.objects.filter(
        user=request.user, 
        is_active=True
    ).select_related('file')
    
    user_call_records = CallRecord.objects.filter(user=request.user)
    
    # Total calls made by user (new metric)
    total_calls_made = user_call_records.count()
    
    # Today's metrics
    today_calls = user_call_records.filter(call_time__date=today).count()
    yesterday_calls = user_call_records.filter(call_time__date=yesterday).count()
    
    # Calculate percentage change for calls
    calls_change = calculate_percentage_change(today_calls, yesterday_calls)
    
    # Lead metrics
    allocated_numbers = set()
    for allocation in user_allocations:
        if allocation.allocated_file:
            numbers = {line.strip() for line in allocation.allocated_file.split('\n') if line.strip()}
            allocated_numbers.update(numbers)
    
    contacted_numbers = set(user_call_records.values_list('phone_number', flat=True))
    new_leads = len(allocated_numbers - contacted_numbers)
    
    # Status breakdown with accurate counts
    status_data = user_call_records.values('status').annotate(
        count=Count('id')
    ).order_by('status')
    
    status_counts = {
        'contacted': 0,
        'interested': 0,
        'not_interested': 0,
        'callback': 0,
        'invalid': 0
    }
    
    total_contacted = 0
    for item in status_data:
        if item['status'] != 'new':
            total_contacted += item['count']
        if item['status'] in status_counts:
            status_counts[item['status']] = item['count']
    
    total_leads = sum(allocation.get_allocated_count() for allocation in user_allocations)
    
    # Weekly comparison metrics
    def get_weekly_comparison(status):
        this_week = user_call_records.filter(
            call_time__date__gte=today - timedelta(days=today.weekday()),
            status=status
        ).count()
        
        last_week = user_call_records.filter(
            call_time__date__gte=today - timedelta(days=today.weekday() + 7),
            call_time__date__lt=today - timedelta(days=today.weekday()),
            status=status
        ).count()
        
        return this_week, last_week, calculate_percentage_change(this_week, last_week)
    
    # Today's Callbacks Summary (NEW ADDITION)
    todays_callbacks_count = user_call_records.filter(
        callback_date__date=today,
        status='callback'
    ).count()
    
    yesterdays_callbacks_count = user_call_records.filter(
        callback_date__date=yesterday,
        status='callback'
    ).count()
    
    # Get today's callback records for display
    todays_callback_records = user_call_records.filter(
        callback_date__date=today,
        status='callback'
    ).order_by('-callback_date')
    
    todays_callbacks = {
        'total_callbacks': todays_callbacks_count,
        'change': calculate_percentage_change(todays_callbacks_count, yesterdays_callbacks_count),
        'pending_callbacks': status_counts['callback'],  # Total pending callbacks
        'completed_callbacks': todays_callbacks_count,  # Callbacks created today
        'callback_list': todays_callback_records[:10]  # Show last 10 callbacks
    }
    
    # Main dashboard metrics
    dashboard_metrics = {
        'total_calls_made': total_calls_made,  # Added total calls metric
        'today_calls': today_calls,
        'calls_change': calls_change,
        'new_leads': new_leads,
        'new_leads_change': get_weekly_comparison('new')[2],
        'interested_leads': status_counts['interested'],
        'interested_change': get_weekly_comparison('interested')[2],
        'total_leads': total_leads,
        'total_leads_change': 5  # Static for now
    }
    
    # Progress calculations
    progress_data = {
        'contacted_progress': safe_percentage(total_contacted, total_leads),
        'interested_progress': safe_percentage(status_counts['interested'], total_leads),
        'callback_progress': safe_percentage(status_counts['callback'], total_leads),
        'invalid_progress': safe_percentage(status_counts['invalid'], total_leads)
    }
    
    # Performance summary (enhanced)
    active_days = max(1, (today - (user_allocations.first().created_at.date() 
                      if user_allocations.exists() else today)).days)
    
    performance_summary = {
        'total_calls_made': total_calls_made,  # Duplicated for easy access
        'avg_calls_per_day': round(total_calls_made / active_days),
        'success_rate': safe_percentage(status_counts['interested'], total_contacted),
        'callback_pending': status_counts['callback']
    }
    
    # Prepare context (rest of your existing context preparation remains the same)
    context = {
        'dashboard_metrics': dashboard_metrics,
        'status_breakdown': status_counts,
        'progress_data': progress_data,
        'activity_timeline': build_activity_timeline(user_call_records.order_by('-call_time')[:10]),
        'weekly_data': json.dumps(generate_weekly_data(user_call_records, today), cls=DjangoJSONEncoder),
        'monthly_data': json.dumps(generate_monthly_data(user_call_records, today), cls=DjangoJSONEncoder),
        'assigned_files': get_assigned_files_data(user_allocations, user_call_records),
        'performance_summary': performance_summary,
        'todays_callbacks': todays_callbacks,  # NEW: Today's callback data
        'user_name': request.user.get_full_name() or request.user.username
    }
    
    return render(request, 'dashboard2.html', context)

# Helper functions
def calculate_percentage_change(current, previous):
    """Safely calculate percentage change between two values"""
    if previous > 0:
        return round(((current - previous) / previous) * 100)
    return 100 if current > 0 else 0

def safe_percentage(numerator, denominator):
    """Calculate percentage safely avoiding division by zero"""
    return round((numerator / denominator) * 100) if denominator > 0 else 0

def build_activity_timeline(records):
    """Build activity timeline from call records"""
    status_config = {
        'contacted': {'icon': 'ni-check-bold', 'color': 'from-green-600 to-lime-400'},
        'interested': {'icon': 'ni-favourite-28', 'color': 'from-blue-600 to-cyan-400'},
        'not_interested': {'icon': 'ni-fat-remove', 'color': 'from-red-600 to-rose-400'},
        'callback': {'icon': 'ni-time-alarm-02', 'color': 'from-yellow-600 to-orange-400'},
        'invalid': {'icon': 'ni-simple-remove', 'color': 'from-gray-600 to-gray-400'}
    }
    
    return [{
        'icon': status_config.get(record.status, {}).get('icon', 'ni-mobile-button'),
        'color': status_config.get(record.status, {}).get('color', 'from-purple-700 to-pink-500'),
        'title': f"{record.get_status_display()} - {record.phone_number}",
        'date': record.call_time.strftime('%d %b %H:%M'),
        'notes': (record.notes[:50] + '...') if record.notes and len(record.notes) > 50 else record.notes or ''
    } for record in records]

def generate_weekly_data(records, end_date):
    """Generate weekly chart data"""
    return generate_chart_data(records, 7, end_date, include_interested=True)

def generate_monthly_data(records, end_date):
    """Generate monthly chart data"""
    return generate_chart_data(records, 30, end_date)

def generate_chart_data(records, days, end_date, include_interested=False):
    """Generate chart data for given number of days"""
    chart_data = []
    for i in range(days):
        date = end_date - timedelta(days=(days-1-i))
        daily_data = {
            'date': date.strftime('%Y-%m-%d'),
            'day': date.strftime('%a'),
            'calls': records.filter(call_time__date=date).count()
        }
        if include_interested:
            daily_data['interested'] = records.filter(
                call_time__date=date, 
                status='interested'
            ).count()
            # Add callback data to weekly chart
            daily_data['callbacks'] = records.filter(
                call_time__date=date,
                status='callback'
            ).count()
        chart_data.append(daily_data)
    return chart_data

def get_assigned_files_data(allocations, call_records):
    """Generate assigned files data with progress"""
    files_data = []
    for allocation in allocations:
        total_assigned = allocation.get_allocated_count()
        total_called = call_records.filter(allocation=allocation).count()
        
        files_data.append({
            'filename': allocation.file.original_filename,
            'total_assigned': total_assigned,
            'total_called': total_called,
            'completion_rate': safe_percentage(total_called, total_assigned),
            'created_at': allocation.created_at
        })
    return files_data

@login_required
def usertask(request):
    """
    View to display user's allocated leads with call records - only showing 'new' status leads
    """
    # Get all allocations for the current user
    allocations = LeadAllocation.objects.filter(user=request.user, is_active=True).select_related('file')

    
    leads_data = []
    total_leads = 0
    total_contacted = 0
    total_interested = 0
    total_callbacks = 0
    
    for allocation in allocations:
        # Parse phone numbers from allocated_file
        if allocation.allocated_file:
            phone_numbers = [line.strip() for line in allocation.allocated_file.split('\n') if line.strip()]
        else:
            phone_numbers = []
        
        # Get existing call records for this allocation
        call_records = CallRecord.objects.filter(allocation=allocation)
        
        
       
        call_records_dict = {record.phone_number: record for record in call_records}
        
        # Process each phone number
        for phone in phone_numbers:
            call_record = call_records_dict.get(phone)
            
            if call_record:
                # Only show records with 'new' status
                if call_record.status == 'new':
                    lead_data = {
                        'allocation_id': allocation.id,
                        'phone_number': phone,
                        'status': call_record.status,
                        'call_time': call_record.call_time,
                        'duration': call_record.duration,
                        'notes': call_record.notes or '',
                        'callback_date': call_record.callback_date,
                        'updated_at': call_record.updated_at,
                        'call_record_id': call_record.id,
                    }
                    leads_data.append(lead_data)

                
                # Count all statistics (for stats bar)
                if call_record.status == 'contacted':
                    total_contacted += 1
                elif call_record.status == 'interested':
                    total_interested += 1
                elif call_record.status == 'callback':
                    total_callbacks += 1
         
                    
            else:
                # Show numbers without call records (they are 'new' by default)
                lead_data = {
                    'allocation_id': allocation.id,
                    'phone_number': phone,
                    'status': 'new',
                    'call_time': timezone.now(),
                    'duration': 0,
                    'notes': '',
                    'callback_date': None,
                    'updated_at': None,
                    'call_record_id': None,
                }
                leads_data.append(lead_data)
            
            total_leads += 1
    
    # Calculate contacted count (all statuses except 'new') - for all records, not just displayed ones
    all_call_records = CallRecord.objects.filter(allocation__user=request.user)
    total_contacted = all_call_records.exclude(status='new').count()
    total_interested = all_call_records.filter(status='interested').count()
    total_callbacks = all_call_records.filter(status='callback').count()
    
    context = {
        'leads_data': leads_data,
        'total_leads': total_leads,
        'total_contacted': total_contacted,
        'total_interested': total_interested,
        'total_callbacks': total_callbacks,
        'showing_new_only': True,  # Flag to indicate we're filtering
    }
    
    return render(request, 'usertask.html', context)

@login_required
@csrf_exempt
def update_call_record(request):
    """
    AJAX view to update or create call records
    """
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            
            allocation_id = data.get('allocation_id')
            phone_number = data.get('phone_number')
            status = data.get('status')
            call_time = data.get('call_time')
            duration = data.get('duration', 0)
            notes = data.get('notes', '')
            callback_date = data.get('callback_date')
            
            # Validate allocation belongs to user
            allocation = get_object_or_404(LeadAllocation, id=allocation_id, user=request.user)
            
            # Parse datetime strings
            if call_time:
                call_time = datetime.fromisoformat(call_time.replace('T', ' '))
            
            callback_date_parsed = None
            if callback_date and callback_date.strip():
                callback_date_parsed = datetime.fromisoformat(callback_date.replace('T', ' '))
            
            # Get or create call record
            call_record, created = CallRecord.objects.get_or_create(
                allocation=allocation,
                phone_number=phone_number,
                user=request.user,
                defaults={
                    'status': status,
                    'call_time': call_time or timezone.now(),
                    'duration': int(duration),
                    'notes': notes,
                    'callback_date': callback_date_parsed,
                }
            )
            
            if not created:
                # Update existing record
                call_record.status = status
                if call_time:
                    call_record.call_time = call_time
                call_record.duration = int(duration)
                call_record.notes = notes
                call_record.callback_date = callback_date_parsed
                call_record.save()
            
            return JsonResponse({
                'success': True,
                'message': 'Call record updated successfully',
                'created': created
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': str(e)
            }, status=400)
    
    return JsonResponse({'success': False, 'message': 'Invalid request method'}, status=405)

@login_required
@csrf_exempt
def delete_call_record(request):
    """
    AJAX view to delete call records
    """
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            phone_number = data.get('phone_number')
            allocation_id = data.get('allocation_id')
            
            # Validate allocation belongs to user
            allocation = get_object_or_404(LeadAllocation, id=allocation_id, user=request.user)
            
            # Find and delete call record
            call_record = CallRecord.objects.filter(
                allocation=allocation,
                phone_number=phone_number
            ).first()
            
            if call_record:
                call_record.delete()
                return JsonResponse({
                    'success': True,
                    'message': 'Call record deleted successfully'
                })
            else:
                return JsonResponse({
                    'success': False,
                    'message': 'Call record not found'
                }, status=404)
                
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': str(e)
            }, status=400)
    
    return JsonResponse({'success': False, 'message': 'Invalid request method'}, status=405)


@user_passes_test(admin_check, login_url='/')
def leadfiles(request):
 
 return render(request,'leadfile.html')

@login_required
def followsup(request):
    # Get filter parameters from request
    status_filter = request.GET.get('status', '')
    date_filter = request.GET.get('date', '')
    
    # Start with all call records for the current user
    call_records = CallRecord.objects.filter(user=request.user)
    call_records = call_records.filter(status__in=['interested', 'contacted','callback'])
    
    # Apply status filter if provided
    if status_filter:
        call_records = call_records.filter(status=status_filter)
    
    # Apply date filter if provided
    if date_filter:
        try:
            filter_date = timezone.datetime.strptime(date_filter, '%Y-%m-%d').date()
            call_records = call_records.filter(
                models.Q(call_time__date=filter_date) | 
                models.Q(callback_date__date=filter_date)
            )
        except ValueError:
            pass
    
    # Order by callback date (earliest first) then by call time (newest first)
    call_records = call_records.order_by('callback_date', '-call_time')
    filtered_status_choices = [
        choice for choice in CallRecord.STATUS_CHOICES 
        if choice[0] in ['interested', 'contacted','callback']
    ]
    
    context = {
        'call_records': call_records,
        'status_choices': filtered_status_choices,
        'selected_status': status_filter,
        'selected_date': date_filter,
    }
    return render(request, 'followup.html', context)
@login_required
def update_call_record2(request):
    if request.method == 'POST':
        record_id = request.POST.get('record_id')
        status = request.POST.get('status')
        callback_date = request.POST.get('callback_date')
        calltime = request.POST.get('calltime')
        notes = request.POST.get('notes', '')
        
        try:
            record = CallRecord.objects.get(id=record_id, user=request.user)
            record.status = status
            record.notes = notes
            
            if callback_date:
                record.callback_date = timezone.make_aware(
                    timezone.datetime.strptime(callback_date, '%Y-%m-%dT%H:%M')   )
            else:
                record.callback_date = None
                 
            if calltime:
                record.call_time = timezone.make_aware(
                    timezone.datetime.strptime(calltime, '%Y-%m-%dT%H:%M')
                )
                
            record.save()
            messages.success(request, 'Call record updated successfully!')
        except CallRecord.DoesNotExist:
            messages.error(request, 'Call record not found or you do not have permission to edit it.')
        
        return redirect('followsup')
    
    return redirect('followsup')

@login_required
def delete_call_record2(request):
    if request.method == 'POST':
        record_id = request.POST.get('record_id')
        
        try:
            record = CallRecord.objects.get(id=record_id, user=request.user)
            record.delete()
            messages.success(request, 'Call record deleted successfully!')
        except CallRecord.DoesNotExist:
            messages.error(request, 'Call record not found or you do not have permission to delete it.')
        
        return redirect('followsup')
    
    return redirect('followsup')
@csrf_exempt
@require_http_methods(["POST"])
def upload_lead_file(request):
    if 'file' not in request.FILES:
        return JsonResponse({'error': 'No file uploaded'}, status=400)
    
    uploaded_file = request.FILES['file']
    original_filename = uploaded_file.name

    # Validate file extension
    allowed_extensions = ['.xlsx', '.csv', '.xls']
    if not any(original_filename.lower().endswith(ext) for ext in allowed_extensions):
        return JsonResponse({'error': 'Invalid file type'}, status=400)

    try:
        # Read file content once to reuse it later
        file_content = uploaded_file.read()

        # Save temp file for processing
        temp_path = default_storage.save(f'tmp/{original_filename}', ContentFile(file_content))

        # Process file to count numbers
        if original_filename.lower().endswith('.csv'):
            df = pd.read_csv(default_storage.path(temp_path))
        else:
            df = pd.read_excel(default_storage.path(temp_path))

        phone_numbers = df.iloc[:, 0].dropna().unique()
        total_numbers = len(phone_numbers)

        

        # Create lead file record
        lead_file = LeadFile(
            admin=request.user,
            file=uploaded_file,
            original_filename=original_filename,
            total_numbers=total_numbers,
            status='ready',
            processed_at=timezone.now()
        )
       
        lead_file.save()

        # Delete temp file
        default_storage.delete(temp_path)

        return JsonResponse({
            'success': True,
            'file': {
                'id': lead_file.id,
                'name': lead_file.original_filename,
                'total_numbers': lead_file.total_numbers,
                'status': lead_file.status,
                'created_at': lead_file.created_at.strftime('%Y-%m-%d %H:%M:%S')
            }
        })

    except Exception as e:
        return JsonResponse({'error': f'Error processing or saving file: {str(e)}'}, status=500)

def normalize_number(num):
    # Remove spaces, dashes, parentheses
    num = ''.join(filter(str.isdigit, str(num)))
    # Strip leading '0' if any
    if num.startswith('0'):
        num = num[1:]
    # Ensure starts with '91'
    if not num.startswith('91') and len(num) == 10:
        num = '91' + num
    return num

@csrf_exempt
@require_http_methods(["POST"])
def allocate_leads(request):
    try:
        data = json.loads(request.body)
        file_id = data.get('file_id')
        allocations = data.get('allocations', [])
        print("this is the file allocation:",allocations)

        if not file_id or not allocations:
            return JsonResponse({'error': 'Missing required data'}, status=400)

        lead_file = LeadFile.objects.get(id=file_id)

        # Validate total percentage
        total_percentage = sum(alloc['percentage'] for alloc in allocations)
        if total_percentage != 100:
            return JsonResponse({'error': 'Total percentage must equal 100%'}, status=400)

        file_path = lead_file.file.path
        if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
            return JsonResponse({'error': 'Uploaded file is empty or missing'}, status=400)

        try:
            if lead_file.original_filename.lower().endswith('.csv'):
                df = pd.read_csv(file_path)
                if df.empty or df.shape[1] == 0:
                    df = pd.read_csv(file_path, header=None)
            else:
                df = pd.read_excel(file_path)
                if df.empty or df.shape[1] == 0:
                    return JsonResponse({'error': 'Excel file is empty or has no columns'}, status=400)
        except Exception as e:
            return JsonResponse({'error': f'Error reading file: {str(e)}'}, status=500)

        phone_numbers = df.iloc[:, 0].dropna().astype(str).apply(normalize_number).unique()
        total_numbers = len(phone_numbers)

        # Exclude already allocated indices
        allocated_indices = set()
        for allocation in lead_file.allocations.all():
            allocated_indices.update(range(allocation.start_index, allocation.end_index + 1))

        available_numbers = [num for i, num in enumerate(phone_numbers) if i not in allocated_indices]
        available_total = len(available_numbers)

        if available_total == 0:
            return JsonResponse({'error': 'No phone numbers left to allocate'}, status=400)

        results = []
        start_index = 0

        for alloc in allocations:
            user = User.objects.get(id=alloc['user_id'])
            percentage = alloc['percentage']
            count = round((percentage / 100) * available_total)
            count = min(count, available_total - start_index)
            if count <= 0:
                continue

            end_index = start_index + count
            allocated_numbers = available_numbers[start_index:end_index]

            # Join as plain text to store in TextField
            text_output = '\n'.join(allocated_numbers)

            allocation = LeadAllocation.objects.create(
                file=lead_file,
                user=user,
                percentage=percentage,
                start_index=start_index,
                end_index=end_index - 1,
                allocated_file=text_output
            )
           

            results.append({
                'user_id': user.id,
                'username': user.username,
                'allocated_count': count,
                'start_index': start_index,
                'end_index': end_index - 1,
                'contacts_preview': allocated_numbers[:5]  # show first 5 as preview
            })

            start_index = end_index

        # Update file status if fully allocated
        lead_file.refresh_from_db()
        if lead_file.allocated_numbers >= lead_file.total_numbers:
            lead_file.status = 'allocated'
            lead_file.save()

        return JsonResponse({
            'success': True,
            'allocations': results,
            'remaining': available_total - start_index
        })

    except LeadFile.DoesNotExist:
        return JsonResponse({'error': 'Lead file not found'}, status=404)
    except User.DoesNotExist:
        return JsonResponse({'error': 'User not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@require_http_methods(["GET"])
def get_lead_files(request):
    files = LeadFile.objects.all().order_by('-created_at')
    
    files_data = []
    for file in files:
        files_data.append({
            'id': file.id,
            'name': file.original_filename,
            'status': file.status,
            'total_numbers': file.total_numbers,
            'allocated_numbers': file.allocated_numbers,
            'available_numbers': file.get_available_numbers_count(),
            'created_at': file.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'admin': file.admin.username
        })
    
    return JsonResponse({'files': files_data})


@require_http_methods(["GET"])
def get_users(request):
    users = User.objects.filter(is_active=True).exclude(id=request.user.id)
    
    users_data = []
    for user in users:
        users_data.append({
            'id': user.id,
            'username': user.username,
            'first_name': user.first_name,
            'last_name': user.last_name
        })
    
    return JsonResponse({'users': users_data})

@csrf_exempt
@require_http_methods(["POST"])
def delete_file(request, file_id):
    try:
        lead_file = LeadFile.objects.get(id=file_id)
        
        # Delete the physical file
        lead_file.file.delete()
        
        # Delete the record
        lead_file.delete()
        
        return JsonResponse({'success': True})
        
    except LeadFile.DoesNotExist:
        return JsonResponse({'error': 'File not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
    

def archieve(request):
    status_filter = request.GET.get('status', '')
    date_filter = request.GET.get('date', '')

    # Start with all call records for the current user
    call_records = CallRecord.objects.filter(user=request.user)

    # Apply status filter - show only 'invalid' and 'not_interested'
    call_records = call_records.filter(status__in=['invalid', 'not_interested'])

    # Apply date filter if provided
    if date_filter:
        try:
            filter_date = timezone.datetime.strptime(date_filter, '%Y-%m-%d').date()
            call_records = call_records.filter(
                models.Q(call_time__date=filter_date) | 
                models.Q(callback_date__date=filter_date)
            )
        except ValueError:
            pass

    # Order by callback date (earliest first) then by call time (newest first)
    call_records = call_records.order_by('callback_date', '-call_time')

    # Limit status choices to only 'invalid' and 'not_interested'
    filtered_status_choices = [
        choice for choice in CallRecord.STATUS_CHOICES 
        if choice[0] in ['invalid', 'not_interested']
    ]

    context = {
        'call_records': call_records,
        'status_choices': filtered_status_choices,
        'selected_status': status_filter,
        'selected_date': date_filter,
    }

    return render(request, 'arche.html', context)



def logouts(request):
      auth.logout(request)
      return redirect('/')

from django.contrib.auth import authenticate, login, logout
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
import os

# LOGOUT API

# LOGIN API
@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
@authentication_classes([])
def login_api(request):
    username = request.data.get("username")
    password = request.data.get("password")

    if not username or not password:
        return Response({"error": "Username and password are required"}, status=status.HTTP_400_BAD_REQUEST)

    user = authenticate(request, username=username, password=password)
    if user is not None:
        login(request, user)
        detail = getattr(user, "detail", None)

        return Response({
            "message": "Login successful",
            "is_superuser": user.is_superuser,
            "username": user.username,
            "recording_path": detail.recording_path if detail else "",
            "mobile_name": detail.mobile_name if detail else ""
        }, status=status.HTTP_200_OK)

    return Response({"error": "Invalid username or password"}, status=status.HTTP_401_UNAUTHORIZED)


# LOGOUT API
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def logout_api(request):
    logout(request)
    return Response({"message": "Logged out successfully"}, status=status.HTTP_200_OK)


logger = logging.getLogger(__name__)

@csrf_exempt
@require_http_methods(["POST"])
def upload_recording(request):
    """
    Flutter will send recordings here via multipart form data.
    Stored inside MEDIA_ROOT/recordings/<username>/
    """
    logger.info(f"Request method: {request.method}")
    logger.info(f"Request content type: {request.content_type}")
    logger.info(f"Request META: {request.META.get('CONTENT_TYPE', 'Not set')}")
    logger.info(f"Request POST keys: {list(request.POST.keys())}")
    logger.info(f"Request FILES keys: {list(request.FILES.keys())}")
    
    try:
        # Extract username from POST data
        username = request.POST.get("username")
        
        # Extract file from FILES
        file = request.FILES.get("file")
        
        logger.info(f"Extracted username: '{username}'")
        logger.info(f"Extracted file: {file}")
        
        if file:
            logger.info(f"File name: {file.name}")
            logger.info(f"File size: {file.size}")
            logger.info(f"File content type: {file.content_type}")
        
        # Validate required fields
        if not username:
            error_msg = "Username is required"
            logger.error(f"ERROR: {error_msg}")
            return JsonResponse({
                "error": error_msg,
                "received_post_keys": list(request.POST.keys()),
                "received_files_keys": list(request.FILES.keys()),
                "content_type": request.content_type,
            }, status=400)
        
        if not file:
            error_msg = "File is required"
            logger.error(f"ERROR: {error_msg}")
            return JsonResponse({
                "error": error_msg,
                "received_post_keys": list(request.POST.keys()),
                "received_files_keys": list(request.FILES.keys()),
                "content_type": request.content_type,
            }, status=400)

        # Validate file size (optional - set a reasonable limit)
        max_file_size = 100 * 1024 * 1024  # 100MB
        if file.size > max_file_size:
            error_msg = f"File too large. Maximum size is {max_file_size // (1024*1024)}MB"
            logger.error(f"ERROR: {error_msg}")
            return JsonResponse({"error": error_msg}, status=400)

        # Validate file extension
        allowed_extensions = ['.m4a', '.mp3', '.wav', '.amr', '.3gp', '.aac', '.ogg']
        file_extension = os.path.splitext(file.name.lower())[1]
        
        if file_extension not in allowed_extensions:
            error_msg = f"Invalid file type. Allowed types: {', '.join(allowed_extensions)}"
            logger.error(f"ERROR: {error_msg}")
            return JsonResponse({"error": error_msg}, status=400)

        # Create user directory
        user_dir = os.path.join(settings.MEDIA_ROOT, "recordings", username)
        try:
            os.makedirs(user_dir, exist_ok=True)
            logger.info(f"Created/verified directory: {user_dir}")
        except OSError as e:
            logger.error(f"Error creating directory {user_dir}: {e}")
            return JsonResponse({"error": "Failed to create upload directory"}, status=500)

        # Generate safe filename to avoid conflicts
        base_name, ext = os.path.splitext(file.name)
        safe_filename = file.name
        counter = 1
        
        file_path = os.path.join(user_dir, safe_filename)
        
        # Handle duplicate filenames
        while os.path.exists(file_path):
            safe_filename = f"{base_name}_{counter}{ext}"
            file_path = os.path.join(user_dir, safe_filename)
            counter += 1
        
        logger.info(f"Saving file to: {file_path}")

        # Save file in chunks to handle large files
        try:
            with open(file_path, "wb") as dest:
                for chunk in file.chunks():
                    dest.write(chunk)
            
            # Verify file was written correctly
            saved_size = os.path.getsize(file_path)
            if saved_size != file.size:
                logger.error(f"File size mismatch. Expected: {file.size}, Actual: {saved_size}")
                os.remove(file_path)  # Clean up partial file
                return JsonResponse({"error": "File upload incomplete"}, status=500)
            
        except IOError as e:
            logger.error(f"Error saving file: {e}")
            # Clean up partial file if it exists
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except:
                    pass
            return JsonResponse({"error": "Failed to save file"}, status=500)

        logger.info(f"File saved successfully: {file_path}")
        
        response_data = {
            "message": "File uploaded successfully", 
            "file_path": file_path,
            "username": username,
            "file_name": safe_filename,
            "original_name": file.name,
            "file_size": file.size,
            "saved_size": saved_size,
            "content_type": file.content_type
        }
        
        logger.info(f"Upload successful: {response_data}")
        return JsonResponse(response_data)
        
    except Exception as e:
        logger.error(f"Unexpected exception during upload: {str(e)}", exc_info=True)
        return JsonResponse({
            "error": f"Upload failed: {str(e)}"
        }, status=500)


# Optional: Add a view to list uploaded files for a user
@csrf_exempt
def list_user_recordings(request, username):
    """
    List all recordings for a specific user
    """
    try:
        user_dir = os.path.join(settings.MEDIA_ROOT, "recordings", username)
        
        if not os.path.exists(user_dir):
            return JsonResponse({
                "message": f"No recordings found for user: {username}",
                "files": []
            })
        
        files = []
        for filename in os.listdir(user_dir):
            file_path = os.path.join(user_dir, filename)
            if os.path.isfile(file_path):
                try:
                    stat = os.stat(file_path)
                    files.append({
                        "name": filename,
                        "size": stat.st_size,
                        "created": stat.st_ctime,
                        "modified": stat.st_mtime
                    })
                except OSError:
                    continue
        
        return JsonResponse({
            "username": username,
            "files": files,
            "count": len(files)
        })
        
    except Exception as e:
        logger.error(f"Error listing recordings for {username}: {e}")
        return JsonResponse({"error": str(e)}, status=500)


# Optional: Add a view to get upload statistics
@csrf_exempt
def upload_stats(request):
    """
    Get general upload statistics
    """
    try:
        recordings_dir = os.path.join(settings.MEDIA_ROOT, "recordings")
        
        if not os.path.exists(recordings_dir):
            return JsonResponse({
                "total_users": 0,
                "total_files": 0,
                "total_size": 0
            })
        
        total_users = 0
        total_files = 0
        total_size = 0
        
        for user_dir in os.listdir(recordings_dir):
            user_path = os.path.join(recordings_dir, user_dir)
            if os.path.isdir(user_path):
                total_users += 1
                
                for filename in os.listdir(user_path):
                    file_path = os.path.join(user_path, filename)
                    if os.path.isfile(file_path):
                        try:
                            total_files += 1
                            total_size += os.path.getsize(file_path)
                        except OSError:
                            continue
        
        return JsonResponse({
            "total_users": total_users,
            "total_files": total_files,
            "total_size": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2)
        })
        
    except Exception as e:
        logger.error(f"Error getting upload stats: {e}")
        return JsonResponse({"error": str(e)}, status=500)
    





@login_required
def recordings_dashboard(request):
    # Base directory where recordings are stored
      # Base directory where recordings are stored
    recordings_base_dir = os.path.join(settings.MEDIA_ROOT, 'recordings')
    
    # Get date filter from request
    date_filter = request.GET.get('date_filter', 'all')
    custom_date = request.GET.get('custom_date', '')
    
    # Calculate date range based on filter
    now = datetime.now()
    start_date = None
    end_date = None
    
    if date_filter == 'today':
        start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = now.replace(hour=23, minute=59, second=59, microsecond=999999)
    elif date_filter == 'yesterday':
        yesterday = now - timedelta(days=1)
        start_date = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = yesterday.replace(hour=23, minute=59, second=59, microsecond=999999)
    elif date_filter == 'this_week':
        start_date = now - timedelta(days=now.weekday())
        start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = now.replace(hour=23, minute=59, second=59, microsecond=999999)
    elif date_filter == 'last_week':
        start_date = now - timedelta(days=now.weekday() + 7)
        start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = start_date + timedelta(days=6)
        end_date = end_date.replace(hour=23, minute=59, second=59, microsecond=999999)
    elif date_filter == 'this_month':
        start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end_date = now.replace(hour=23, minute=59, second=59, microsecond=999999)
    elif date_filter == 'last_month':
        first_day_this_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        start_date = (first_day_this_month - timedelta(days=1)).replace(day=1)
        end_date = first_day_this_month - timedelta(days=1)
        end_date = end_date.replace(hour=23, minute=59, second=59, microsecond=999999)
    elif date_filter == 'custom' and custom_date:
        try:
            custom_date_obj = datetime.strptime(custom_date, '%Y-%m-%d')
            start_date = custom_date_obj.replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = custom_date_obj.replace(hour=23, minute=59, second=59, microsecond=999999)
        except ValueError:
            pass
    
    # Get all user directories with their recordings
    users_data = []
    
    try:
        user_dirs = [d for d in os.listdir(recordings_base_dir) 
                    if os.path.isdir(os.path.join(recordings_base_dir, d))]
    except FileNotFoundError:
        user_dirs = []
    
    # Get recordings for each user
    total_recordings = 0
    for username in user_dirs:
        user_dir_path = os.path.join(recordings_base_dir, username)
        user_recordings = []
        
        if os.path.exists(user_dir_path):
            for file in os.listdir(user_dir_path):
                file_path = os.path.join(user_dir_path, file)
                if os.path.isfile(file_path):
                    # Get file stats
                    stat = os.stat(file_path)
                    modified_date = datetime.fromtimestamp(stat.st_mtime)
                    
                    # Apply date filter if specified
                    if start_date and end_date:
                        if not (start_date <= modified_date <= end_date):
                            continue
                    
                    user_recordings.append({
                        'name': file,
                        'size': round(stat.st_size / (1024 * 1024), 2),  # Size in MB
                        'modified': stat.st_mtime,
                        'modified_date': modified_date,
                        'url': os.path.join(settings.MEDIA_URL, 'recordings', username, file)
                    })
        
        # Sort recordings by modification time (newest first)
        user_recordings.sort(key=lambda x: x['modified'], reverse=True)
        
        users_data.append({
            'username': username,
            'recordings': user_recordings,
            'count': len(user_recordings)
        })
        
        total_recordings += len(user_recordings)
    
    # Sort users by username
    users_data.sort(key=lambda x: x['username'])
    
    # Format dates for display
    if start_date and end_date:
        if start_date.date() == end_date.date():
            date_display = start_date.strftime("%B %d, %Y")
        else:
            date_display = f"{start_date.strftime('%B %d, %Y')} to {end_date.strftime('%B %d, %Y')}"
    else:
        date_display = "All Dates"
    
    context = {
        'users_data': users_data,
        'total_recordings': total_recordings,
        'date_filter': date_filter,
        'custom_date': custom_date,
        'date_display': date_display,
        'today': now.strftime('%Y-%m-%d'),
    }
    return render(request, 'recordings.html', context)