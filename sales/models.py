from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone

class UserDetail(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="detail")
    phone = models.CharField(max_length=12)
    recording_path = models.CharField(max_length=255)
    mobile_name = models.CharField(max_length=50)

    def __str__(self):
        return f"{self.user.username} - {self.phone}"

class CallRecording(models.Model):
    user = models.ForeignKey(UserDetail, on_delete=models.CASCADE, related_name='recordings')
    filename = models.CharField(max_length=255)
    original_filename = models.CharField(max_length=255)
    file_path = models.CharField(max_length=500)
    file_size = models.BigIntegerField()
    upload_time = models.DateTimeField(auto_now_add=True)
    recorded_time = models.DateTimeField(null=True, blank=True)
    duration = models.DurationField(null=True, blank=True)
    phone_number = models.CharField(max_length=20, null=True, blank=True)
    call_type = models.CharField(max_length=10, choices=[
        ('incoming', 'Incoming'),
        ('outgoing', 'Outgoing'),
        ('missed', 'Missed')
    ], null=True, blank=True)
    is_processed = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['-upload_time']
    
    def __str__(self):
        return f"{self.user.username} - {self.filename}"
class LeadFile(models.Model):
    STATUS_CHOICES = [
        ('uploaded', 'Uploaded'),
        ('processing', 'Processing'),
        ('ready', 'Ready for Allocation'),
        ('allocated', 'Fully Allocated'),
        ('error', 'Error')
    ]

    admin = models.ForeignKey(User, on_delete=models.CASCADE)
    file = models.FileField(upload_to='lead_files')
    original_filename = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='uploaded')
    total_numbers = models.PositiveIntegerField(default=0)
    allocated_numbers = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True, null=True)

    def get_available_numbers_count(self):
        return max(0, self.total_numbers - self.allocated_numbers)

    def get_next_start_index(self):
        """Return the next unallocated start index (0-based)."""
        last_allocation = self.allocations.order_by('-end_index').first()
        print(last_allocation)
        return (last_allocation.end_index + 1) if last_allocation else 0

    def mark_as_fully_allocated(self):
        if self.allocated_numbers >= self.total_numbers:
            self.status = 'allocated'
            self.save()

    def __str__(self):
        return f"{self.original_filename} ({self.total_numbers} leads)"


class LeadAllocation(models.Model):
    file = models.ForeignKey(LeadFile, on_delete=models.CASCADE, related_name='allocations')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='allocations')
    allocated_file = models.TextField(null=True,blank=True)
    percentage = models.PositiveIntegerField(validators=[MinValueValidator(1), MaxValueValidator(100)])
    start_index = models.PositiveIntegerField()
    end_index = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=models.Q(end_index__gte=models.F('start_index')),
                name='end_index_gte_start_index'
            )
        ]

    def get_allocated_count(self):
        return self.end_index - self.start_index + 1

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        if is_new:
            self.file.allocated_numbers += self.get_allocated_count()
            self.file.save()
            self.file.mark_as_fully_allocated()

    def __str__(self):
        return f"{self.user.username} - {self.percentage}% of {self.file.original_filename}"


class CallRecord(models.Model):
    STATUS_CHOICES = [
        ('new', 'New'),
        ('contacted', 'Contacted'),
        ('interested', 'Interested'),
        ('not_interested', 'Not Interested'),
        ('invalid', 'Invalid'),
        ('callback', 'Callback Requested')
    ]

    allocation = models.ForeignKey(LeadAllocation, on_delete=models.CASCADE, related_name='call_records')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    phone_number = models.CharField(max_length=20)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='new')
    call_time = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, null=True)
    duration = models.PositiveIntegerField(default=0)  # in seconds
    updated_at = models.DateTimeField(auto_now=True)
    callback_date = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.phone_number} - {self.get_status_display()}"
