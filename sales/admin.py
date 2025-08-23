from django.contrib import admin
from .models import LeadFile, LeadAllocation, CallRecord,UserDetail,CallRecording


@admin.register(LeadFile)
class LeadFileAdmin(admin.ModelAdmin):
    list_display = ('original_filename', 'admin', 'status', 'total_numbers', 'allocated_numbers', 'created_at')
    list_filter = ('status',)
    search_fields = ('original_filename',)


@admin.register(LeadAllocation)
class LeadAllocationAdmin(admin.ModelAdmin):
    list_display = ('file', 'user', 'percentage', 'start_index', 'end_index', 'created_at', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('file__original_filename', 'user__username')


@admin.register(CallRecord)
class CallRecordAdmin(admin.ModelAdmin):
    list_display = ('phone_number', 'allocation', 'status', 'call_time', 'duration')
    list_filter = ('status',)
    search_fields = ('phone_number',)

admin.site.register(UserDetail)
admin.site.register(CallRecording)

